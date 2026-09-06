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
            '--no-sandbox'
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

        const page = await browser.newPage();
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36');
        await page.setExtraHTTPHeaders({
            'Accept-Language': 'en-US,en;q=0.9'
        });
        
        // 2. Add proxy authentication if configured
        if (process.env.PROXY_USERNAME && process.env.PROXY_PASSWORD) {
            await page.authenticate({
                username: process.env.PROXY_USERNAME,
                password: process.env.PROXY_PASSWORD
            });
        }

        page.setDefaultTimeout(60000); // Increased timeout to 60s for slow loads
        page.on('console', msg => console.error('Browser Console:', msg.text()));
        
        return { browser, page };
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
            await page?.waitForTimeout(5000);
            await browser.close();
        }
    }

    async handleError(error, page) {
        console.error(`Error in ${this.name}:`, error);
        if (page) {
            await this.takeScreenshot(page, `error-${Date.now()}`);
        }
        return [];
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
    async searchFlights(from, to, departDate, returnDate = null) {
        throw new Error('Method must be implemented');
    }

    async getOffers() {
        throw new Error('Method must be implemented');
    }
}

module.exports = BaseProvider;
