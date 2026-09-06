// Six further providers were required here — MakeMyTrip, Cleartrip, EaseMyTrip,
// Yatra, Goibibo and HappyFares. Five of those files were never written, so
// `require` threw MODULE_NOT_FOUND before the class body was ever reached: this
// module could not load, and neither could `src/server.js`, `src/mcp/tools.js`
// or `src/mcp/server.js`, which is what `npm start` runs. Only
// GoogleFlightsProvider was ever put in `this.providers`, so nothing is lost by
// requiring only it. The sixth, MakeMyTripProvider.js, existed but was imported
// by nothing and never returned a flight; it was deleted on 2026-09-03 after its
// failure was measured — see §44 of ../../../AUDIT-FIXES.md. Google Flights is
// the only source. The live path is `src/mcp/stdio_server.js`, which imports the
// provider directly and does not come through here.
const GoogleFlightsProvider = require('./providers/GoogleFlightsProvider');

class FlightAggregator {
    constructor() {
        // One provider. The plural name and the parallel `Promise.all` below are
        // the shape a second source would slot into, not evidence of one.
        this.providers = [
            new GoogleFlightsProvider()
        ];
    }

    async searchAllProviders(from, to, departDate, returnDate = null) {
        const results = [];
        const searchPromises = this.providers.map(async provider => {
            try {
                console.log(`Searching flights on ${provider.name}...`);
                const flights = await provider.searchFlights(from, to, departDate, returnDate);
                console.log(`Getting offers from ${provider.name}...`);
                const offers = await provider.getOffers();
                
                console.log(`Processing ${flights.length} flights from ${provider.name}`);
                for (const flight of flights) {
                    const priceDetails = provider.calculateBestPrice(flight.basePrice, offers);
                    results.push({
                        provider: provider.name,
                        flight,
                        priceDetails,
                        offers: offers.length > 0 ? offers : null
                    });
                }
            } catch (error) {
                console.error(`Error with provider ${provider.name}:`, error);
            }
        });

        // Run all provider searches in parallel
        await Promise.all(searchPromises);

        // Sort results by best price
        return results.sort((a, b) => a.priceDetails.bestPrice - b.priceDetails.bestPrice);
    }
}

module.exports = FlightAggregator;
