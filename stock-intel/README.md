# Stock Intel

> **Cut through the noise.**  
> Kenyan NSE stock screener, portfolio tracker & Ndindi-style scoring engine.

---

## Logo

Place your `logo.png` file in `frontend/public/logo.png`.  
It will automatically appear in the app header and browser tab.  
If the file is missing the app falls back to a 📈 icon — nothing breaks.

---

## Quick Start

### 1. Backend (Hugging Face Spaces — free)

```bash
cd backend/
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### 2. Frontend (Vercel / local)

```bash
cd frontend/
npm install

# Set your backend URL:
cp .env.example .env.local
# Edit .env.local → VITE_API_BASE=http://localhost:8000

npm run dev
# App: http://localhost:5173
```

---

## Deploy to Production

See **INTEGRATION_GUIDE.md** for full step-by-step instructions covering:
- Deploying backend to Hugging Face Spaces (Docker)
- Deploying frontend to Vercel
- Connecting them via environment variable
- Troubleshooting common issues

---

## Folder Structure

```
stock-intel/
│
├── INTEGRATION_GUIDE.md        ← Full deployment guide
├── README.md                   ← This file
│
├── backend/                    ← Python FastAPI (→ Hugging Face Spaces)
│   ├── Dockerfile              ← For HF Spaces Docker deployment
│   ├── app.py                  ← FastAPI entry point + all endpoints
│   ├── requirements.txt
│   ├── data/
│   │   ├── portfolio_trades.csv
│   │   ├── prices_history.csv
│   │   ├── fundamentals.csv
│   │   └── config.json         ← Scoring weights, settings
│   ├── services/
│   │   ├── data_loader.py      ← Yahoo Finance + CSV cache
│   │   ├── scoring.py          ← Ndindi D/M/L/BP scoring engine
│   │   ├── portfolio.py        ← FIFO trade management + P/L
│   │   └── analytics.py        ← Equity curve, projections
│   └── utils/
│       └── helpers.py
│
└── frontend/                   ← React/Vite SPA (→ Vercel)
    ├── index.html
    ├── vite.config.js
    ├── package.json
    ├── .env.example            ← Copy to .env.local, set API URL
    └── src/
        ├── main.jsx
        └── App.jsx             ← Full SPA: all screens + components
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stocks?timing=best_pick` | All NSE stocks with scores |
| GET | `/api/stock/{ticker}` | Single stock detail + fundamentals |
| GET | `/api/portfolio` | Holdings + P/L summary |
| POST | `/api/trades` | Log a BUY or SELL trade |
| GET | `/api/analytics` | Equity curve + projections |

---

## Links

- More BI services: https://dericbi.vercel.app
