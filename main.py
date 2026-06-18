Build a Python crypto opportunity hunter.
‎
‎Requirements:
‎
‎- Use Gemini API
‎- Use Binance public API
‎- Scan top gainers
‎- Scan top losers
‎- Scan 24h volume changes
‎- Save opportunities in SQLite
‎
‎For each opportunity:
‎
‎Generate:
‎- Why moving
‎- Bull case
‎- Bear case
‎- Entry zone
‎- Target 1
‎- Target 2
‎- Stop loss
‎
‎Output Binance Square formatted post.
‎
‎Environment variables:
‎
‎GEMINI_API_KEY=AQ.Ab8RN6IwEOiOngVE28L6QIHkT1hQ6VHiGRuWMxFuVWyOGidoVA
‎BINANCE_API_KEY=
‎BINANCE_API_SECRET=9b8ff8e72b6d4c6ab467876d8951104f
‎
‎Project structure:
‎
‎main.py
‎scanner.py
‎analysis.py
‎post_generator.py
‎database.py
‎config.py
‎requirements.txt
‎
‎Run every 5 minutes.
‎
‎Store all generated posts in database.
‎
import requests
import sqlite3
from datetime import datetime

DB_NAME = "opportunities.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        change_percent REAL,
        volume REAL,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def get_top_gainers():
    url = "https://api.binance.com/api/v3/ticker/24hr"

    response = requests.get(url, timeout=10)
    data = response.json()

    usdt_pairs = [
        item for item in data
        if item["symbol"].endswith("USDT")
    ]

    gainers = sorted(
        usdt_pairs,
        key=lambda x: float(x["priceChangePercent"]),
        reverse=True
    )

    return gainers[:10]


def save_coin(symbol, change_percent, volume):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO opportunities
    (symbol, change_percent, volume, created_at)
    VALUES (?, ?, ?, ?)
    """, (
        symbol,
        change_percent,
        volume,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()


def main():
    print("Scanning Binance...")

    coins = get_top_gainers()

    for coin in coins:
        symbol = coin["symbol"]
        change = float(coin["priceChangePercent"])
        volume = float(coin["quoteVolume"])

        print(
            f"{symbol} | "
            f"{change:.2f}% | "
            f"Volume: {volume:,.0f}"
        )

        save_coin(symbol, change, volume)

    print("Done.")


if __name__ == "__main__":
    init_db()
    main()
