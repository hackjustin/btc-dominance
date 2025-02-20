import os
import requests
import psycopg2
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection settings
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),            
    "port": os.getenv("DB_PORT")
}

# API URLs
COINGECKO_URL = "https://api.coingecko.com/api/v3/global"
COINGECKO_MARKET_URL = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=btc&order=market_cap_desc&per_page=25&page=1&sparkline=false"

# Alert thresholds
BTC_DOMINANCE_HIGH = 55.0  # Alert if BTC Dominance goes above this
BTC_DOMINANCE_LOW = 45.0   # Alert if BTC Dominance goes below this
ALT_STRENGTH_CHANGE_THRESHOLD = 0.02  # Alert if ALT/BTC strength changes by this much
ACCUMULATION_VOLUME_SPIKE = 1.5  # 1.5x average volume signals accumulation

# Telegram settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# Connect to PostgreSQL
def connect_db():
    return psycopg2.connect(**DB_CONFIG)

# Create table if not exists
def setup_database():
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS btc_dominance (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    btc_dominance FLOAT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS alt_btc_strength (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    alt_id TEXT,
                    alt_btc FLOAT,
                    volume FLOAT
                )
            ''')
            conn.commit()

# Fetch BTC Dominance from CoinGecko
def fetch_btc_dominance():
    response = requests.get(COINGECKO_URL)
    if response.status_code == 200:
        data = response.json()
        btc_dominance = data["data"]["market_cap_percentage"]["btc"]
        return btc_dominance
    return None

# Fetch ALT/BTC strength from CoinGecko
def fetch_alt_btc_strength():
    response = requests.get(COINGECKO_MARKET_URL)
    if response.status_code == 200:
        data = response.json()
        return {coin["id"]: {"btc": coin["current_price"], "volume": coin["total_volume"]} for coin in data}
    return None

# Store BTC Dominance in DB
def store_btc_dominance(btc_dominance):
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO btc_dominance (btc_dominance) VALUES (%s)", (btc_dominance,))
            conn.commit()

# Store ALT/BTC strength in DB
def store_alt_btc_strength(alt_data):
    with connect_db() as conn:
        with conn.cursor() as cur:
            for alt_id, value in alt_data.items():
                cur.execute("INSERT INTO alt_btc_strength (alt_id, alt_btc, volume) VALUES (%s, %s, %s)", (alt_id, value["btc"], value["volume"]))
            conn.commit()

# Fetch past data for ranking and accumulation detection
def fetch_past_alt_data():
    past_data = {}
    btc_dominance_trend = []
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT timestamp, btc_dominance FROM btc_dominance WHERE timestamp >= NOW() - INTERVAL '7 days'")
            btc_dominance_trend = cur.fetchall()
            cur.execute("SELECT alt_id, alt_btc, volume FROM alt_btc_strength WHERE timestamp >= NOW() - INTERVAL '7 days'")
            rows = cur.fetchall()
            for alt_id, alt_btc, volume in rows:
                if alt_id not in past_data:
                    past_data[alt_id] = []
                past_data[alt_id].append((alt_btc, volume))
    return past_data, btc_dominance_trend

# Identify ranking and accumulation
def analyze_alts():
    past_data, btc_dominance_trend = fetch_past_alt_data()
    rankings = {}
    accumulation_alerts = []
    
    btc_dominance_change = (btc_dominance_trend[-1][1] - btc_dominance_trend[0][1]) if len(btc_dominance_trend) >= 2 else 0

    for alt_id, records in past_data.items():
        if len(records) < 2:
            continue
        initial_price = records[0][0]
        latest_price = records[-1][0]
        avg_volume = sum(r[1] or 0 for r in records) / len(records)
        latest_volume = records[-1][1]
        price_change = (latest_price - initial_price) / initial_price
        relative_strength = price_change - btc_dominance_change
        rankings[alt_id] = relative_strength
        
        if latest_volume > avg_volume * ACCUMULATION_VOLUME_SPIKE:
            accumulation_alerts.append(f"{alt_id.upper()} shows accumulation! Volume spike: {latest_volume:.2f} (Avg: {avg_volume:.2f})")
    
    top_alts = sorted(rankings.items(), key=lambda x: x[1], reverse=True)[:5]
    return top_alts, accumulation_alerts

# Console alert function
def send_alert(message):
    print(f"ALERT: {message}")

# Telegram alert function
def send_telegram_alert(message):
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(TELEGRAM_URL, data=payload)
    print(f"TELEGRAM ALERT SENT: {message}")

# Main function to run the tracker
def main():
    setup_database()
    send_alert("BTC Dominance Tracker Started.")
    send_telegram_alert("BTC Dominance Tracker Started.")
    
    while True:
        btc_dominance = fetch_btc_dominance()
        alt_data = fetch_alt_btc_strength()
        
        if btc_dominance:
            print(f"{datetime.now()} - BTC Dominance: {btc_dominance:.2f}%")
            store_btc_dominance(btc_dominance)
            
        if alt_data:
            store_alt_btc_strength(alt_data)
            top_alts, accumulation_alerts = analyze_alts()
            send_telegram_alert(f"Top Alts: {', '.join(f'{alt.upper()} ({change:.2%})' for alt, change in top_alts)}")
            for alert in accumulation_alerts:
                send_telegram_alert(alert)

        time.sleep(300)

if __name__ == "__main__":
    main()
