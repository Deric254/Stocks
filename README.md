# 📈 Stock Intel — NSE Kenya Intelligence Platform

Smart stock analysis for the Nairobi Securities Exchange.

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

### 🛠️ Troubleshooting

**"Failed to build wheel" / cargo / rustc errors during `pip install`:** You're on Python 3.14 or newer. It was released very recently and several required libraries (`pydantic-core`, sometimes `pandas`/`numpy`) don't have prebuilt installer packages ("wheels") for it yet, so `pip` tries to compile them from source — which needs a Rust compiler most machines don't have, and fails with a long, confusing error. **Fix:** install Python 3.11 or 3.12 from python.org (you can have multiple versions installed side by side — this won't remove your existing Python), check "Add python.exe to PATH" during install, then re-run `START.bat`. It checks your Python version automatically now and will tell you clearly if this is the issue, before ever reaching `pip`.

**Screen looks frozen at "Checking backend dependencies...":** It's usually not frozen — `pip` downloading pandas/numpy for the first time can take 1-3 minutes with the terminal looking idle. Wait it out; if it's genuinely stuck past ~5 minutes, check your internet connection.

### 🔑 Backend Environment Variables
| Variable | Required? | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | Recommended for production | Comma-separated list of frontend URLs allowed to call the API (e.g. `https://stockintel.vercel.app`). Defaults to local dev ports only — **set this on your hosted backend or the deployed frontend will be blocked by CORS.** |
| `FRED_API_KEY` | Optional | Free key from [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html). Enables global macro indicators (rates, inflation, GDP, PMI) on the Macro Intelligence page. Without it, that section shows a clear "not configured" message instead of failing. |

### 🚀 Releases & Auto-Update
Every push to `main` triggers `.github/workflows/release.yml`, which:
1. Bumps the version in `VERSION` (patch by default — trigger manually via the Actions tab for a minor/major bump)
2. Builds a **single self-contained executable** for Windows, Linux, and macOS (frontend + backend bundled together — no separate Python/Node install needed to run it)
3. Publishes a GitHub Release with all three executables attached

**For client systems that want to auto-update:** poll `GET /api/version/check` (requires the `GITHUB_REPO` env var set to `owner/repo` on your server). It returns `update_available: true/false` and a direct download URL per platform — this uses GitHub's own release API, not a custom version server, so it's free and needs nothing extra hosted.

```bash
curl http://localhost:8000/api/version/check
# {"current_version": "1.0.3", "latest_version": "1.0.4", "update_available": true,
#  "assets": [{"name": "stockintel-windows.exe", "download_url": "...", "size_bytes": 45000000}, ...]}
```

### 🩺 Verifying a Deploy
After deploying (or before trusting this locally with real capital decisions), hit:
```
GET /api/system-status
```
This reports real operational status per layer — not a pulse check. It tells you whether FRED is configured, whether local price data is loaded, and how much recommendation history exists for adaptive weighting. Check this first if something looks off.

### 🧪 Running Tests
```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v
```
32 tests covering every API endpoint, data-integrity guards (your `portfolio_trades.csv` is snapshotted and restored around every test run), and dedicated tests for the Layer 12→10 adaptive weighting logic — the highest-stakes piece of code in this repo, since it changes what drives a Buy/Sell recommendation based on historical performance. Run this after any backend change, before deploying.

**Not covered by these tests:** live calls to FRED, World Bank, or stooq (Layers 1–4). Those are tested against mocked responses only. The first real deploy should manually check `/api/intelligence/global`, `/api/intelligence/country`, and `/api/intelligence/sector` against live network access before trusting their output.

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
│   │   ├── technical.py        ← Technical indicators (RSI/MACD/ADX/ATR)
│   │   ├── valuation.py        ← DCF / DDM intrinsic value models
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
