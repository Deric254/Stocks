# Stock Intel — Cut through the noise.

NSE stock screener, portfolio tracker & Ndindi-style scoring engine.

## Run

Double-click `START.bat` — installs everything and opens the browser.

Or manually:

```
# Terminal 1
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000

# Terminal 2
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Logo

Place your `logo.png` in `frontend/public/logo.png`

## Links

More BI services: https://dericbi.vercel.app
