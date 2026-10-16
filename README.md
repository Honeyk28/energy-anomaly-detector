# ⚡ AI Energy Consumption Anomaly Detector

A full-stack machine learning web application for monitoring, detecting, and diagnosing smart meter energy consumption anomalies across residential households (Area X: MH01–MH20).

Powered by **Python, Flask, SQLite, and scikit-learn**, combining **Isolation Forest** and **Rolling Median + Robust Median Absolute Deviation (MAD)**.

---

## 🚀 Features

- **Area-Wide Anomaly Detection**: Analyze aggregate grid usage over 660+ days with dynamic time windows.
- **Dual Unsupervised ML Models**:
  - **Isolation Forest**: Multi-feature anomaly isolation based on consumption, rolling deviations, and weekly seasonality.
  - **Rolling Median + Robust MAD**: Non-parametric time-series baseline resistant to outliers.
- **Household Drilldown**: Pinpoint individual meters (MH01 to MH20) driving grid anomalies on any selected date, with 24-hour diurnal profiling.
- **Model Explainability & Methodology**: Transparent feature explanations, confusion matrix proxy metrics, and scoring breakdowns.
- **Role-Based Access Control**: Secure login sessions with admin and viewer privileges, password updates, and user action audit logging.

---

## 🛠️ Quick Start

### 1. Clone & Setup Environment
```bash
git clone https://github.com/Honeyk28/energy-anomaly-detector.git
cd energy-anomaly-detector
```

### 2. Install Dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Seed the Database
Populate SQLite with user accounts and 16,491 smart meter records:
```bash
python3 seed.py
```

### 4. Start the Application
```bash
python3 app.py
```
> **Note**: Opens by default on **http://localhost:5001** (or port 5000 if macOS AirPlay Receiver is disabled).

---

## 🔐 Default Credentials

| Username | Role | Default Password |
| :--- | :--- | :--- |
| `member1` | Admin | `Team@2026#1` |
| `member2` | Admin | `Team@2026#2` |
| `member3` | Admin | `Team@2026#3` |
| `demo` | Viewer | `Demo@2026` |

---

## 📁 Repository Structure

```
energy-anomaly-detector/
├── app.py                 # Flask web server, auth routes, and REST endpoints
├── engine.py              # ML anomaly detection models & feature engineering
├── db.py                  # Database initialization, user management, audit logs
├── seed.py                # Database population script from CSV dataset
├── requirements.txt       # Python dependencies
├── .env.example           # Environment template (SECRET_KEY, PORT)
├── data/
│   └── SM_Cleaned_Data_MH_Aggregated.csv  # Cleaned smart meter readings
├── static/
│   ├── style.css          # Responsive styling & color system
│   └── app.js             # Client controller & inline responsive SVG visualizations
├── templates/
│   ├── login.html         # Login interface
│   └── app.html           # Unified analytics dashboard
└── tests/
    └── smoke_test.py      # End-to-end integration and API tests
```

---

## 🧪 Testing

Run smoke and integration tests:
```bash
python3 -m unittest tests/smoke_test.py
```
