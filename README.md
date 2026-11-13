# Rathinam Report - Backend (Report-BE)

FastAPI & PostgreSQL backend engine powering the Rathinam Campus Operations Report system.

## 🚀 Overview
Provides analytical endpoints, matrix computation, real-time variance calculations, audit flags, master data management, and operational data entry.
Includes reverse-proxy / subpath rewriting middleware supporting `rguedu.in/Report/api`.

## 🛠️ Tech Stack
- **Framework:** FastAPI
- **Server:** Uvicorn
- **Database:** PostgreSQL (psycopg2)
- **Environment Management:** python-dotenv

## 📦 Getting Started

### 1. Database Setup
Create the database and execute the schema:
```bash
# Create database
createdb -U postgres food_operations

# Load schema and seed data
psql -U postgres -d food_operations -f schema.sql
```

### 2. Environment Variables
Copy `.env.example` to `.env` and update credentials if needed:
```bash
cp .env.example .env
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Server
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
or run `start.bat`.

## 📡 API Endpoints
- `GET /api/health` / `GET /Report/api/health` - Server health check
- `POST /api/auth/login` - User authentication
- `GET /api/overview` - Dashboard analytical KPI summaries
- `GET /api/matrix` - Dynamic multi-period operational matrix
- `POST /api/batch-entry` - Bulk expense line item save
- `GET /api/periods` & `POST /api/periods` - Monthly billing cycle lifecycle
- `GET /api/mom-variance` - Month-over-month variance analysis
- `GET /api/audit-flags` - Automated cost anomaly flags
- `GET /api/master/*` - Master data categories and cost heads

