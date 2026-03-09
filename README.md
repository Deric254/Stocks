# 📈 Stock Intel — NSE Kenya Intelligence Platform

Smart stock analysis + Gold trading signals for the Nairobi Securities Exchange.

---

## 🖥️ Run Locally (Your PC)

### First time setup
```
cd backend
pip install -r requirements.txt
```

### Start backend (Terminal 1)
```
cd backend
python app.py
```
Backend runs at: http://localhost:8000

### Start frontend (Terminal 2)
```
cd frontend
npm install      ← first time only
npm run dev
```
Open: **http://localhost:5173**

---

## 🌐 Deploy Online (Free — Share with Others)

### Step 1 — Put code on GitHub
1. Create account at github.com
2. Create new repository called `StockIntel` (public)
3. Upload all files (drag & drop the folder, or use GitHub Desktop)

### Step 2 — Deploy Backend on Render (Free)
1. Go to **render.com** → Sign up with GitHub
2. Click **New +** → **Web Service**
3. Connect your GitHub repo
4. Fill in:
   - **Root Directory:** `backend`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Click **Create Web Service**
6. Wait ~3 minutes. You'll get a URL like: `https://stockintel-api-xxxx.onrender.com`
7. **Copy that URL** — you need it in Step 3

### Step 3 — Deploy Frontend on Vercel (Free)
1. Go to **vercel.com** → Sign up with GitHub
2. Click **New Project** → Import your GitHub repo
3. Fill in:
   - **Root Directory:** `frontend`
   - **Framework:** Vite
4. Under **Environment Variables**, add:
   - Name: `VITE_API_URL`
   - Value: `https://stockintel-api-xxxx.onrender.com` ← your Render URL from Step 2
5. Click **Deploy**
6. You get a URL like: `https://stockintel.vercel.app`
7. **Share that URL** with people!

### ⚠️ Important Notes for Hosted Version
- **First load takes 30-60 seconds** — Render free tier sleeps after 15 min inactivity. It wakes up when someone visits.
- **Prices may show as stubs** — NSE scraping works best locally. On hosted version, use the **Data Status** page to manually enter current prices.
- **Gold API** — Make sure `TWELVE_KEY` in `backend/services/gold.py` has your real Twelve Data API key.

---

## 🔑 API Keys (Optional but Recommended)

### Twelve Data (Gold live prices)
1. Go to **twelvedata.com** → Free signup
2. Get your API key (800 requests/day free)
3. Open `backend/services/gold.py`
4. Replace: `TWELVE_KEY = "demo"` with your key

---

## 📁 Project Structure
```
StockIntel/
├── backend/
│   ├── app.py                  ← FastAPI server
│   ├── requirements.txt        ← Python packages
│   ├── services/
│   │   ├── nse_scraper.py      ← NSE price fetcher
│   │   ├── data_loader.py      ← Data management
│   │   ├── gold.py             ← Gold trading module
│   │   ├── scoring.py          ← 60-point scoring model
│   │   ├── portfolio.py        ← Portfolio tracker
│   │   └── analytics.py        ← Analytics engine
│   └── data/                   ← Cache files (auto-created)
└── frontend/
    ├── src/App.jsx             ← Full React app
    ├── .env                    ← Local environment (localhost)
    └── .env.example            ← Template for hosting
```

---

## 🏦 Scoring Model (60 points)
| Category | Points | What it measures |
|---|---|---|
| Profitability | 10 | ROE, net margin |
| Dividend | 10 | Yield, consistency |
| Growth | 10 | Revenue + earnings trend |
| Value | 10 | P/E, P/B ratios |
| Asset Safety | 10 | Asset coverage |
| Debt Safety | 10 | D/E ratio, interest coverage |

**Score guide:** 50–60 Strong Buy ✅ | 40–49 Buy | 30–39 Hold | 20–29 Weak | <20 Avoid ❌
