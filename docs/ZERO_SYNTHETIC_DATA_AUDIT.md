# SkyMind Copilot — Zero Synthetic Data Integrity Audit & Remediation Report

## 1. Executive Summary

SkyMind is an AI flight intelligence platform designed to build user trust through data accuracy, real-time market signals, and transparent airfare forecasting. This audit inspected the entire repository to verify that **SkyMind NEVER fabricates flight schedule or carrier information** in production paths.

### Audit Summary:
1. **Canonical Forecast Pipeline (`backend/services/forecast/`)**: 100% compliant with zero synthetic data principles. All recommendation decisions, minimum expected fares, confidence scores, and savings metrics are derived from verified model outputs and real live market snapshots.
2. **Flight Normalization Layer (`backend/services/flight_normalizer.py`)**: **CRITICAL VIOLATION DETECTED**. When live MCP search fails or historical DB cache observations are loaded, missing schedule fields are populated with hardcoded static defaults (e.g. `12:00:00` departure time, `14:15:00` arrival time, `PT2H15M` duration, `6E1000` flight number, `IndiGo` carrier).
3. **Remediation Recommendation**: Eliminate all static string defaults. If schedule attributes were not observed or returned by live providers, return `NULL` / `None`, hide the corresponding field, or render `"Unavailable"`.

---

## 2. Repository Integrity Report

| Subsystem | Audit Status | Integrity Classification | Primary Risk |
| :--- | :---: | :--- | :--- |
| **Canonical Forecast System** | PASSED | `DERIVED` / `ML_PREDICTION` | None — Pure mathematical invariants |
| **MCP Transport Layer** | PASSED | `REAL_PROVIDER` | Retries & timeouts clean |
| **Flight Normalization Layer** | **FAILED** | **`SYNTHETIC` Fallbacks** | Static `12:00:00` & `6E1000` defaults |
| **Market Data Controller** | **FAILED** | **`SYNTHETIC` Defaults** | `carrier` defaults to `"6E"` if missing |
| **Frontend Presentation** | PASSED | `PURE_PRESENTATION` | Consumes DTO directly |

---

## 3. Synthetic Data & Default Value Inventory

### Inventory of Hardcoded Static Defaults Found:

1. **Static Departure & Arrival Timestamps**:
   - **File**: `backend/services/flight_normalizer.py` (Lines 98–99, 205–206, 227–228)
   - **Synthetic Code**:
     ```python
     departure_time = f"{departure_date}T12:00:00"
     arrival_time = f"{departure_date}T14:15:00"
     ```
   - **Classification**: `SYNTHETIC`
   - **Violation**: Invents a 12:00 PM departure time for flights whose real schedule was not recorded in cache.

2. **Static Flight Duration**:
   - **File**: `backend/services/flight_normalizer.py` (Lines 104, 184, 219, 239)
   - **Synthetic Code**: `duration = "PT2H15M"`
   - **Classification**: `SYNTHETIC`
   - **Violation**: Invents a 2-hour 15-minute flight duration when leg duration is absent.

3. **Default Airline Code & Name**:
   - **File**: `backend/services/flight_normalizer.py` (Lines 93, 101, 149, 157, 197, 199)
   - **Synthetic Code**: `carrier = db_flight.get("airline_code", "6E")`, `airline_name = "IndiGo"`
   - **Classification**: `SYNTHETIC`
   - **Violation**: Assigns unparsed or unrecorded flights to carrier `6E` (`IndiGo`).

4. **Default Flight Number Injection**:
   - **File**: `backend/services/flight_normalizer.py` (Line 94, 203) & `backend/services/flight_search_service.py` (Line 235)
   - **Synthetic Code**: `flight_num = db_flight.get("flight_number", "6E1000")`, `f"{primary_airline}1000"`
   - **Classification**: `SYNTHETIC`
   - **Violation**: Assigns dummy `6E1000` flight numbers to cached price observations.

---

## 4. API Field Provenance Matrix

Every field exposed by the FastAPI API is classified into 6 authoritative provenance categories:

| API Response Field | Classification | Data Source | Fabricated? |
| :--- | :--- | :--- | :---: |
| `current_market.lowest_fare` | `REAL_PROVIDER` | Google Flights MCP / Live SerpAPI | No |
| `canonical_forecast.current_fare` | `REAL_PROVIDER` | Live Market Snapshot | No |
| `canonical_forecast.expected_minimum_fare` | `ML_PREDICTION` | XGBoost Model Prediction | No |
| `canonical_forecast.optimal_booking_horizon` | `DERIVED` | Timeline Min-Price Index | No |
| `canonical_forecast.calculated_savings` | `DERIVED` | Pure Math (`current_fare - min_fare`) | No |
| `canonical_forecast.confidence_score` | `DERIVED` | `ConfidenceEngine` Formula | No |
| `flight.itineraries[0].segments[0].departure_time` | `SYNTHETIC` (in DB Fallback) | Hardcoded `"T12:00:00"` string | **YES (in DB Fallback)** |
| `flight.itineraries[0].duration` | `SYNTHETIC` (in DB Fallback) | Hardcoded `"PT2H15M"` string | **YES (in DB Fallback)** |
| `flight.flight_number` | `SYNTHETIC` (in DB Fallback) | Hardcoded `"6E1000"` string | **YES (in DB Fallback)** |

---

## 5. Critical Findings

### Finding 1 — Hardcoded Schedule Injection in `normalize_db_flight`
- **Severity**: **CRITICAL**
- **File**: `backend/services/flight_normalizer.py`
- **Lines**: 98–106
- **Evidence**:
  ```python
  segment = NormalizedSegment(
      flight_number=flight_num,
      departure_time=f"{departure_date}T12:00:00",
      arrival_time=f"{departure_date}T14:15:00",
      airline_code=carrier,
      airline_name=db_flight.get("airline_name", "IndiGo"),
      origin=origin_iata,
      destination=destination_iata,
      duration="PT2H15M",
      stops=0,
      cabin="ECONOMY"
  )
  ```
- **Why it is Synthetic**: Creates a fake departure time (`12:00:00`), arrival time (`14:15:00`), and duration (`2h 15m`) for price history records that only stored historical fare amounts.
- **How it Reaches Production**: Whenever MCP live search fails or returns zero matches, `flight_search_service.py` fetches cached price observations and normalizes them via `normalize_db_flight`.
- **Risk to User Trust**: High. Users see identical 12:00 PM IndiGo flights for every historical cached record.

---

### Finding 2 — Hardcoded Schedule Injection in `normalize_mcp_flight`
- **Severity**: **HIGH**
- **File**: `backend/services/flight_normalizer.py`
- **Lines**: 184, 205–206, 219
- **Evidence**:
  ```python
  dep_time = flight.get("departure_time") or f"{departure_date}T12:00:00"
  arr_time = flight.get("arrival_time") or f"{departure_date}T14:15:00"
  ...
  duration="PT2H15M"
  ```
- **Why it is Synthetic**: If a raw string payload from MCP lacks parsed departure/arrival leg times, default strings are injected.
- **How it Reaches Production**: Executes during non-leg flight normalization.
- **Risk to User Trust**: Medium. Displays artificial departure times when carrier schedule data is unparsed.

---

### Finding 3 — Default Airline Code `6E` and `IndiGo` Fallbacks
- **Severity**: **HIGH**
- **File**: `backend/services/flight_normalizer.py` (Lines 93, 101, 149, 157, 197)
- **Evidence**: `carrier = db_flight.get("airline_code", "6E")`
- **Why it is Synthetic**: Automatically attributes unknown or missing carrier records to carrier `6E` (`IndiGo`).
- **How it Reaches Production**: Database fallback paths and raw unparsed MCP flight paths.
- **Risk to User Trust**: High. Users looking for Vistara or Air India flights see them attributed to IndiGo.

---

## 6. Remediation Specifications (No Code Changes Applied)

To achieve **Zero Synthetic Data Integrity**, future refactoring should enforce these 4 production rules:

1. **Rule 1: Unknown Schedule $\rightarrow$ `NULL` / `"Unavailable"`**:
   - In `normalize_db_flight`, if `departure_time` is missing, return `None` or set `departure_time = None`. The frontend will render `"Schedule Unavailable"`.
2. **Rule 2: Unknown Flight Number $\rightarrow$ `NULL`**:
   - Remove `"6E1000"` fallback string. Return `None` if unrecorded.
3. **Rule 3: Unknown Carrier $\rightarrow$ `"Unknown Carrier"`**:
   - Remove `"6E"` and `"IndiGo"` fallbacks for unrecorded records. Return `airline_code = "UNKNOWN"`.
4. **Rule 4: Explicit Data Provenance Tagging**:
   - Tag every flight object with `provenance: "REAL_PROVIDER"` or `provenance: "HISTORICAL_OBSERVATION"`.
