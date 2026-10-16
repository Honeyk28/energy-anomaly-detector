# ⚡ AI Energy Consumption Anomaly Detector

A production-ready full-stack machine learning application for monitoring, detecting, and diagnosing smart meter energy consumption anomalies across residential households in **Area X**.

Area X is defined as a **constructed analytical study group** of 38 residential smart meters (MH-prefixed meters from the CEEW Mathura/Bareilly dataset), rather than a physical neighborhood or specific electrical feeder.

---

## 📊 Dataset Specifications

- **Source**: Council on Energy, Environment and Water (CEEW) Smart Meter Dataset (Harvard Dataverse, doi:10.7910/DVN/GOCHJH, CC0).
- **Scope**: 38 smart meters (`MH01` to `MH47`).
- **Temporal Range**: May 1, 2019 to February 20, 2021 (**662 calendar days**).
- **Resolution**: **Daily aggregate energy consumption** in kilowatt-hours (`t_kWh`). The dataset does not provide hourly or intra-day interval data.
- **Records**: 16,491 total rows.
- **Zero & Missing Readings**: 
  - **143 zero readings** are treated as non-reporting days or power outages (excluded from baseline calculations and area sums).
  - Out of 25,156 theoretical meter-days (38 meters × 662 days), 8,808 are unrecorded or zero (an effective non-reporting rate of **35.0%**).
  - Missing entries are treated as missing (`NaN`), never as zero consumption.
- **Minimum Coverage Threshold**: Any date with fewer than **15 comparable houses** reporting valid data and baseline values is classified as **low coverage** and excluded from anomaly detection (**45 low-coverage days** in the default centered baseline).

---

## 🧠 Anomaly Detection Methodology

The system applies two unsupervised statistical and machine learning algorithms to detect high-consumption spikes. Both algorithms are strictly unsupervised; no fabricated ground-truth labels are introduced.

### 1. Dual Baseline Strategies
To compute expected consumption for each household from its own history:
- **Centered 29-Day Median** (Retrospective):
  - Uses a window of 14 days prior and 14 days following the target date (`[d-14, d+14]`, excluding day `d`).
  - Requires at least 5 valid observations.
  - Suited for retrospective auditing and seasonal normalization.
- **Trailing 28-Day Median** (Prospective / Real-Time):
  - Uses 28 days strictly prior to the target date (`[d-28, d-1]`).
  - Avoids future-data leakage; suitable for operational monitoring.
  - Requires at least 5 valid observations.

### 2. Area Aggregation
For each date, total actual consumption and total expected consumption are calculated by summing **only across the exact same comparable households** (meters with both valid readings and valid expected baselines on that date). This ensures that meter reporting dropouts never trigger false area anomalies.

### 3. Isolation Forest
- **Features**: 
  1. **Relative Consumption Increase**: `(Actual - Expected) / Expected`
  2. **Absolute Consumption Increase**: `Actual - Expected` (kWh)
- **Contamination Parameter**: Default is `0.02` (2.0%).
- **Decision Logic**: Only flags an anomaly when the observation is an isolated outlier (`pred == -1`) **and** actual area consumption strictly exceeds expected consumption (`increase > 0`).
- **Anomaly Score**: A continuous normalized ranking score from `0.0` (most normal) to `1.0` (most anomalous) derived from the Isolation Forest decision function. It represents a relative outlier rank, not a probability.

### 4. Robust Z-Score (Median Absolute Deviation - MAD)
- **Formula**:
  $$z = \frac{r - \text{median}(r)}{1.4826 \times \text{MAD}}$$
  where $r$ is the relative consumption increase, and $\text{MAD} = \text{median}(|r - \text{median}(r)|)$.
- **Threshold**: Default threshold is $z \ge 3.5$.
- **Zero-Denominator Handling**: If $\text{MAD} = 0$ (zero spread in reference observations), points with $r > \text{median}(r)$ are explicitly treated as extreme outliers with score `1.0`, rather than silently replacing the scale with an arbitrary substitute.
- **Decision Logic**: Flags only positive deviations exceeding the threshold.

---

## 🔍 Household Attribution & Reconciliation

For each flagged anomaly date:
1. **Household Excess**: Calculated as $\text{Actual}_m - \text{Expected}_m$ for each reporting house $m$.
2. **Ranking**: Households are ranked in descending order of positive excess.
3. **Contribution Share**: Computed as:
   $$\text{Share}_m = \frac{\text{Excess}_m}{\sum_{k, \text{Excess}_k > 0} \text{Excess}_k} \times 100\%$$
4. **Reconciliation**:
   - Total positive excess across households exceeds net area increase whenever some households consume below baseline (negative deviations).
   - The distinction is reported explicitly: $\text{Net Area Increase} = \sum \text{Positive Excess} + \sum \text{Negative Deviations}$.
   - Individual household excess values are never artificially altered to force a round sum.

---

## 📈 Model Verification Results (Default Configuration)

Running against the complete dataset with default settings (Centered 29-day baseline, IF contamination 2.0%, MAD threshold 3.5):

- **Calendar Days Scanned**: 662 days
- **Low-Coverage Excluded Days**: 45 days
- **Evaluated Days**: 617 days
- **Isolation Forest Detections (4 days)**:
  1. `2019-09-11`: Actual 496.7 kWh, Expected 389.7 kWh (+107.08 kWh / +27.5%, Score 0.96, 32 comparable houses)
  2. `2020-05-24`: Actual 307.4 kWh, Expected 233.3 kWh (+74.12 kWh / +31.8%, Score 0.88, 22 comparable houses)
  3. `2019-06-05`: Actual 594.6 kWh, Expected 500.9 kWh (+93.73 kWh / +18.7%, Score 0.81, 33 comparable houses)
  4. `2020-05-25`: Actual 263.3 kWh, Expected 201.4 kWh (+61.87 kWh / +30.7%, Score 0.80, 21 comparable houses)
- **Robust Z-Score MAD Detections (2 days)**:
  1. `2020-05-24`: Actual 307.4 kWh, Expected 233.3 kWh (+74.12 kWh / +31.8%, Score 0.57)
  2. `2020-05-25`: Actual 263.3 kWh, Expected 201.4 kWh (+61.87 kWh / +30.7%, Score 0.54)
- **Model Agreement**: Both models independently flag `2020-05-24` and `2020-05-25`.
- **Primary Single-Day Anomaly (`2019-09-11`) Top Contributors**:
  - `MH10`: Actual 59.8 kWh, Expected 35.4 kWh (+24.40 kWh excess, 21.5% share)
  - `MH24`: Actual 31.6 kWh, Expected 18.0 kWh (+13.65 kWh excess, 12.0% share)
  - `MH02`: Actual 41.1 kWh, Expected 29.0 kWh (+12.11 kWh excess, 10.6% share)
  - *Reconciliation*: Positive excess sum = 113.76 kWh; Negative deviations sum = -6.68 kWh (across 6 houses); Net area increase = 107.08 kWh.

---

## ⚠️ Important Limitations

1. **Constructed Study Group**: Area X is an analytical aggregation of 38 residential meters, not a physical distribution transformer or distribution feeder.
2. **No Ground Truth Labels**: Because utility confirmation is unavailable, supervised metrics (precision, recall, F1, confusion matrices) cannot be verified. Evaluation is measured via model consensus, coverage tracking, and attribution consistency.
3. **Statistical Anomaly vs Cause**: High consumption flags reflect statistically unusual deviations from baseline patterns. They do **not** prove electricity theft, meter tampering, or equipment failure.

---

## 🛠️ Quick Start

### 1. Setup Environment
```bash
# Clone the repository
git clone https://github.com/Honeyk28/energy-anomaly-detector.git
cd energy-anomaly-detector

# Create environment configuration from template
cp .env.example .env
```
Edit `.env` to define your own secure administrator and viewer credentials before seeding.

### 2. Install Dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Seed Database
```bash
python3 seed.py
```
This populates SQLite with the 38-meter readings (16,491 rows) and sets up the user accounts using PBKDF2:SHA256 password hashing.

### 4. Start the Web Server
```bash
python3 app.py
```
Access the dashboard at **http://localhost:5001** (or port 5000 if macOS AirPlay Receiver is disabled).

---

## 🔐 Authentication & Roles

The system enforces role-based access control (RBAC):
- **Admin**: Full access to Overview, Anomaly Detection, Household Attribution, Method Notes, and Access Management (create users, toggle user status, reset passwords, audit sign-in logs).
- **Viewer**: Read-only access to analytical views and drilldowns. Restricted from administrative and user-management endpoints.
- **Account Security**:
  - Passwords hashed using `pbkdf2:sha256`.
  - Rate limiting / lockout: 5 failed sign-in attempts within 60 seconds triggers a temporary lockout.
  - Disabled accounts are terminated immediately on both API routes and web interfaces.
  - Initial seed credentials are read from environment variables (`ADMIN_PASSWORD`, `DEMO_PASSWORD`) and excluded from version control.

---

## 🧪 Testing

Execute the automated test suite covering authentication, baseline mechanics, data sanitization, coverage cutoffs, attribution math, and ML models:
```bash
python3 -m unittest tests/smoke_test.py
```
