'''
Stock universes: which companies, and which sector each belongs to.

IVAN_* is Ivan's original selection. Its prices are cached in the
repository (finance/Cache), so everything built on it works offline.

WIDE_* is a larger, balanced universe - five large US companies in each of
six sectors - for studies where eight stocks are too few for TGAP's concepts
to have room to move. Its prices are downloaded once from Yahoo Finance
(needs the 'yfinance' library and internet) and then cached.
'''

IVAN_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "JPM", "XOM", "JNJ"]

IVAN_SECTORS = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "GOOGL": "Technology",
    "AMZN": "Consumer",
    "NVDA": "Technology",
    "JPM": "Financials",
    "XOM": "Energy",
    "JNJ": "Healthcare",
}

WIDE_SECTORS = {
    # Technology
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology",
    "NVDA": "Technology", "ORCL": "Technology",
    # Financials
    "JPM": "Financials", "BAC": "Financials", "GS": "Financials",
    "MS": "Financials", "WFC": "Financials",
    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
    "SLB": "Energy", "EOG": "Energy",
    # Healthcare
    "JNJ": "Healthcare", "PFE": "Healthcare", "MRK": "Healthcare",
    "ABBV": "Healthcare", "UNH": "Healthcare",
    # Consumer
    "AMZN": "Consumer", "WMT": "Consumer", "PG": "Consumer",
    "KO": "Consumer", "MCD": "Consumer",
    # Industrials
    "CAT": "Industrials", "BA": "Industrials", "GE": "Industrials",
    "HON": "Industrials", "UPS": "Industrials",
}

WIDE_TICKERS = list(WIDE_SECTORS)
