"""
helpers.py — Shared utility functions.
"""

from datetime import datetime, date


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def format_currency(value: float, currency: str = "KES") -> str:
    return f"{currency} {value:,.2f}"


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division, returns default on zero denominator."""
    return numerator / denominator if denominator != 0 else default


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
