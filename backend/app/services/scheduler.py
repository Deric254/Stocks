from apscheduler.schedulers.background import BackgroundScheduler
from app.routes.stocks import DEFAULT_STOCKS
from app.services.stock_fetcher import fetch_and_update_stock


def start_scheduler():
    scheduler = BackgroundScheduler()

    def update_all():
        for stock in DEFAULT_STOCKS:
            fetch_and_update_stock(
                ticker=stock["ticker"],
                name=stock["name"],
                market=stock["market"],
                sector=stock["sector"]
            )

    scheduler.add_job(update_all, "interval", minutes=30)
    scheduler.start()