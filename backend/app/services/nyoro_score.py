def compute_nyoro_score(stock):
    """
    Compute Nyoro score based on:
    - P/E ratio < 15
    - Dividend yield >= 2%
    - Price < 90% of 52-week avg
    - Sector in utilities/infrastructure/industrial
    - Price dropped >=10% last 3 months
    """
    score = 0
    pe_ratio = stock.get("pe_ratio", 0)
    dividend_yield = stock.get("dividend_yield", 0)
    price = stock.get("price", 0)
    avg_52_week = stock.get("avg_52_week", price)
    sector = stock.get("sector", "").lower()
    price_drop_3m = stock.get("price_drop_3m", 0)

    if pe_ratio < 15:
        score += 1
    if dividend_yield >= 0.02:
        score += 1
    if price < 0.9 * avg_52_week:
        score += 1
    if sector in ["utilities", "infrastructure", "industrial"]:
        score += 1
    if price_drop_3m >= 0.1:
        score += 1

    return score