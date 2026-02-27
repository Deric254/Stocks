from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import stocks, portfolio, analytics

app = FastAPI(title="DericBI Stock Vantage API")

# CORS for frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(stocks.router, prefix="/stocks", tags=["Stocks"])
app.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])

@app.get("/")
async def root():
    return {"message": "DericBI Stock Vantage API is running"}

from app.models.db_models import init_db
from app.services.scheduler import start_scheduler

init_db()
start_scheduler()