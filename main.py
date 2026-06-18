import requests
import sqlite3
from datetime import datetime
import os

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
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        usdt_pairs = [item for item in data if item["symbol"].endswith("USDT")]
        gainers = sorted(usdt_pairs, key=lambda x: float(x["priceChangePercent"]), reverse=True)
        return gainers[:10]
    except Exception as e:
        print(f"Error: {e}")
        return []

def save_coin(symbol, change_percent, volume):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO opportunities (symbol, change_percent, volume, created_at)
    VALUES (?, ?, ?, ?)
    """, (symbol, change_percent, volume, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def main():
    print("Scanning Binance...")
    coins = get_top_gainers()
    for coin in coins:
        symbol = coin["symbol"]
        change = float(coin["priceChangePercent"])
        volume = float(coin["quoteVolume"])
        print(f"{symbol} | {change:.2f}% | Volume: {volume:,.0f}")
        save_coin(symbol, change, volume)
    print("Done.")

if __name__ == "__main__":
    init_db()
    main()
    
