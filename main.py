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
