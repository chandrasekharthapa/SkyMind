const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

class BaseProvider {
    constructor() {
        if (this.constructor === BaseProvider) {
            throw new Error('Abstract class cannot be instantiated');
        }
        this.debug = process.env.DEBUG === 'true';
    }

    async initBrowser() {
        const args = [
            '--start-maximized',
            '--disable-notifications',
            '--no-sandbox',
            // Containers give /dev/shm 64 MB, which Chrome's renderer outgrows
            // on a page this heavy and then stalls or crashes; write to /tmp.
            '--disable-dev-shm-usage',
            // No GPU in a container or on a CI runner; don't probe for one.
            '--disable-gpu'
        ];

        // 1. Add proxy server if configured
        if (process.env.PROXY_SERVER) {
            args.push(`--proxy-server=${process.env.PROXY_SERVER}`);
        }

        const isHeadless = process.env.PUPPETEER_HEADLESS === 'false' ? false : 'new';
        const launchOptions = {
            headless: isHeadless,
            defaultViewport: { width: 1280, height: 800 },
            args: args
        };

        // The Chrome binary used to be the hardcoded absolute path
        // 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', which made
        // every provider unlaunchable anywhere but one Windows machine — on Linux
        // or macOS, and in CI or a container, puppeteer.launch() threw ENOENT and
        // the scrape failed before it began. Honour PUPPETEER_EXECUTABLE_PATH when
        // it is set, and otherwise omit the key entirely so Puppeteer uses the
        // Chromium that `npm install` downloaded. Omitting is deliberate: passing
        // executablePath: undefined is not equivalent on every Puppeteer version.
        const chromePath = (process.env.PUPPETEER_EXECUTABLE_PATH || '').trim();
        if (chromePath) {
            launchOptions.executablePath = chromePath;
        }

        const browser = await puppeteer.launch(launchOptions);
        let page;
        try {
            page = await browser.newPage();
            await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36');
            // en-IN, not en-US. Google infers the pricing locale from the
            // Accept-Language header as well as the IP, and a US locale on a
            // US-hosted runner produced USD fares that the ingest currency screen
            // refused wholesale. This pairs with the explicit curr=INR&gl=IN&hl=en-IN
            // on the search URL in GoogleFlightsProvider.
            await page.setExtraHTTPHeaders({
                'Accept-Language': 'en-IN,en-GB;q=0.9,en;q=0.8'
            });

            // 2. Add proxy authentication if configured
            if (process.env.PROXY_USERNAME && process.env.PROXY_PASSWORD) {
                await page.authenticate({
                    username: process.env.PROXY_USERNAME,
                    password: process.env.PROXY_PASSWORD
                });
            }

            // Images, fonts and media are most of the bytes on a Google Flights
            // page and none of the data: every field is read from card innerText.
            // Downloading and decoding them is what made a scrape outlast the
            // 90 s MCP_TIMEOUT on Render's fractional-CPU instance (a ~9 s scrape
            // on a GitHub runner took >90 s there). Stylesheets are deliberately
            // still loaded: innerText follows rendered layout, and the parser
            // splits cards on the line breaks that layout produces.
            await page.setRequestInterception(true);
            page.on('request', (request) => {
                const type = request.resourceType();
                if (type === 'image' || type === 'font' || type === 'media') {
                    request.abort().catch(() => {});
                } else {
                    request.continue().catch(() => {});
                }
            });

            page.setDefaultTimeout(60000); // Increased timeout to 60s for slow loads
            page.on('console', (msg) => {
                const text = msg.text();
                // Every image, font and media request aborted above is reported
                // by the page as a failed load. Those are ours, not errors.
                if (text.startsWith('Failed to load resource: net::ERR_FAILED')) return;
                console.error('Browser Console:', text);
            });
            return { browser, page };
        } catch (error) {
            await browser.close().catch((closeError) => {
                console.error('Failed to close browser after initialization error:', closeError);
            });
            throw error;
        }
    }

    async takeScreenshot(page, name) {
        try {
            await page.screenshot({
                path: `${this.name.toLowerCase()}-${name}.png`,
                fullPage: true
            });
        } catch (error) {
            console.error(`Failed to take screenshot ${name}:`, error);
        }
    }

    async closeBrowser(browser, page) {
        if (!this.debug && browser) {
            console.error('Closing browser...');
            // There was a fixed 5-second wait here before close(). It ran in the
            // providers' `finally`, so it delayed every result by 5 s — about half
            // of each scrape on CI — and bought nothing: extraction has finished
            // and the result is already in hand when this runs. Debug mode, which
            // keeps the browser open for inspection, skips this method entirely.
            await browser.close();
        }
    }

    async handleError(error, page) {
        console.error(`Error in ${this.name}:`, error);
        if (page) {
            await this.takeScreenshot(page, `error-${Date.now()}`);
        }
        // Preserve the distinction between an authentic zero-result search and
        // a failed crawl. The stdio boundary turns this sentinel into an MCP
        // tool error; only a genuinely successful empty scrape returns [].
        return { error: error instanceof Error ? error.message : String(error) };
    }

    calculateBestPrice(basePrice, offers) {
        let bestPrice = basePrice;
        let appliedOffer = null;

        for (const offer of offers) {
            let discountAmount = 0;
            
            if (!offer || !offer.discountType || !offer.discountValue) {
                continue;
            }
            
            const discountValue = parseFloat(offer.discountValue);
            if (isNaN(discountValue)) {
                continue;
            }
            
            if (offer.discountType.toLowerCase().includes('percent')) {
                discountAmount = basePrice * (discountValue / 100);
            } else if (offer.discountType.toLowerCase().includes('flat')) {
                discountAmount = discountValue;
            }
            
            const priceAfterDiscount = basePrice - discountAmount;
            
            if (priceAfterDiscount < bestPrice) {
                bestPrice = priceAfterDiscount;
                appliedOffer = offer;
            }
        }

        return {
            originalPrice: basePrice,
            bestPrice: bestPrice,
            appliedOffer: appliedOffer,
            savings: basePrice - bestPrice
        };
    }

    // Abstract methods that must be implemented by child classes
    async searchFlights(
        from,
        to,
        departDate,
        returnDate = null,
        passengers = { adults: 1, children: 0, infants: 0 },
        cabinClass = 'economy'
    ) {
        throw new Error('Method must be implemented');
    }

    async getOffers() {
        throw new Error('Method must be implemented');
    }
}

module.exports = BaseProvider;
