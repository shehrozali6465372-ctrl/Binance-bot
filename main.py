import requests
import json
import random
import os

def get_live_coin_data(coin_id):
    defaults = {"bitcoin": (64433.0, -1.88), "ethereum": (1726.95, -3.45), "binancecoin": (580.0, -0.5), "solana": (145.0, +4.2), "dogecoin": (0.135, -3.1)}
    return defaults.get(coin_id, (64433.0, -1.88))

def main():
    coins = [{"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin"}, {"id": "binancecoin", "symbol": "BNB", "name": "BNB"}]
    selected_coin = random.choice(coins)
    
    live_price, live_change = get_live_coin_data(selected_coin['id'])
    
    # Key ko environment variable se uthayein
    gemini_key = os.environ.get("GEMINI_KEY")
    # Dono tareeqon se key pass kar rahe hain (Header + URL Param)
    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
    
    prompt = f"Write a short, viral crypto post about {selected_coin['name']} at ${live_price:,}. Keep it professional."
    
    gemini_res = requests.post(gemini_url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={"Content-Type": "application/json"})
    
    if gemini_res.status_code == 200:
        res_json = gemini_res.json()
        post_content = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        # Binance Posting Logic
        binance_url = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"
        binance_payload = {"contentType": 1, "bodyTextOnly": post_content}
        binance_headers = {"X-Square-OpenAPI-Key": os.environ.get("BINANCE_SQUARE_KEY"), "Content-Type": "application/json"}
        
        response = requests.post(binance_url, json=binance_payload, headers=binance_headers)
        print(f"Post Response: {response.json()}")
    else:
        print(f"❌ Error {gemini_res.status_code}: {gemini_res.text}")

if __name__ == "__main__":
    main()
    
