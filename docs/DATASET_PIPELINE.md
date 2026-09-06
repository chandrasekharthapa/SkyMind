# SkyMind Copilot — Dataset Pipeline Reference

## 1. Data Collection & History Pipeline

- **Data Provider Service**: `backend/services/historical_data_service.py` provides flight price history dataset access.
- **Days Until Departure Invariant**: Guaranteed calendar date calculation:
  $$\text{days\_until\_dep} = (\text{departure\_date} - \text{recorded\_at}).\text{days}$$
- **Price History Format**: Serialized CSV / JSON history datasets containing route origin, destination, departure date, recording timestamp, observed fare, and lead time.
