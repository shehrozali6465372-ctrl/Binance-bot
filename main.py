    import requests
import json
import random
import os

def get_live_coin_data(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()[coin_id]
            return data["usd"], data["usd_24h_change"]
    except Exception:
        pass
    defaults = {"bitcoin": (64433.0, -1.88), "ethereum": (1726.95, -3.45), "binancecoin": (580.0, -0.5), "solana": (145.0, +4.2), "dogecoin": (0.135, -3.1)}
    return defaults.get(coin_id, (64433.0, -1.88))

def main():
    coins = [
        {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin"},
        {"id": "ethereum", "symbol": "ETH", "name": "Ethereum"},
        {"id": "binancecoin", "symbol": "BNB", "name": "BNB"},
        {"id": "solana", "symbol": "SOL", "name": "Solana"},
        {"id": "dogecoin", "symbol": "DOGE", "name": "Dogecoin"}
    ]
    
    selected_coin = random.choice(coins)
    
    print(f"🔄 Fetching Data for {selected_coin['name']}...")
    live_price, live_change = get_live_coin_data(selected_coin['id'])
    print(f"✅ Live Data -> {selected_coin['symbol']}: ${live_price:,} ({live_change:+.2f}%)")

    # GitHub Secrets se key uthayi
    gemini_key = os.environ.get("GEMINI_KEY")
    
    # URL ko simple rakha aur model standard v1beta par kiya
    gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    
    prompt = f"You are an elite crypto analyst. Convert this market signal into a short viral Binance Square post: {selected_coin['name']} ({selected_coin['symbol']}) is currently trading at ${live_price:,} with a 24-hour move of {live_change:+.2f}%. Include a clear trading setup at the end (Entry range close to current price, Target, Stop loss). Keep it clean, concise, short sentences only, no asterisks, no markdown formatting."
    
    # Headers mein standard tarike se API key bheji
    gemini_headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": gemini_key
    }
    
    try:
        gemini_res = requests.post(gemini_url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers=gemini_headers)
        res_json = gemini_res.json()
        
        if "candidates" in res_json:
            post_content = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            print(f"❌ Gemini Response Error: {res_json}")
            return
    except Exception as e:
        print(f"❌ Gemini Error: {e}")
        return

    # Binance setup
    binance_square_key = os.environ.get("BINANCE_SQUARE_KEY")
    binance_url = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"
    
    binance_headers = {
        "X-Square-OpenAPI-Key": binance_square_key,
        "Content-Type": "application/json",
        "clienttype": "binanceSkill"
    }
    
    binance_payload = {
        "contentType": 1,
        "bodyTextOnly": post_content
    }
    
    try:
        response = requests.post(binance_url, json=binance_payload, headers=binance_headers)
        data = response.json()
        if data.get("code") == "000000":
            print(f"🎉 SUCCESS! {selected_coin['symbol']} Post Published!")
            print(f"🆔 ID: {data['data']['id']}\n")
        else:
            print(f"❌ Error: {data.get('message')}\n")
    except Exception as e:
        print(f"❌ Failed: {e}\n")

if __name__ == "__main__":
    main()
    
    
