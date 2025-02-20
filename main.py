import os
import requests
import psycopg2
import time
from datetime import datetime
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
                    alt_btc FLOAT
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
        return {coin["id"]: {"btc": coin["current_price"]} for coin in data}
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
                cur.execute("INSERT INTO alt_btc_strength (alt_id, alt_btc) VALUES (%s, %s)", (alt_id, value["btc"]))
            conn.commit()

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
    send_alert("BTC Dominance Tracker Started.")  # Alert on script start
    send_telegram_alert("BTC Dominance Tracker Started.")  # Alert on script start
    last_alt_values = {}

    while True:
        btc_dominance = fetch_btc_dominance()
        alt_data = fetch_alt_btc_strength()

        if btc_dominance:
            print(f"{datetime.now()} - BTC Dominance: {btc_dominance:.2f}%")
            store_btc_dominance(btc_dominance)
            
            # Check for alerts
            if btc_dominance >= BTC_DOMINANCE_HIGH:
                send_alert(f"BTC Dominance has risen above {BTC_DOMINANCE_HIGH}%: {btc_dominance:.2f}%")
                send_telegram_alert(f"BTC Dominance has risen above {BTC_DOMINANCE_HIGH}%: {btc_dominance:.2f}%")
            elif btc_dominance <= BTC_DOMINANCE_LOW:
                send_alert(f"BTC Dominance has dropped below {BTC_DOMINANCE_LOW}%: {btc_dominance:.2f}%")
                send_telegram_alert(f"BTC Dominance has dropped below {BTC_DOMINANCE_LOW}%: {btc_dominance:.2f}%")
        else:
            print("Failed to fetch BTC Dominance.")

        if alt_data:
            store_alt_btc_strength(alt_data)
            for alt_id, value in alt_data.items():
                alt_btc = value["btc"]
                print(f"{alt_id.upper()}/BTC: {alt_btc:.6f}")
                
                # Check for ALT/BTC strength alerts
                if alt_id in last_alt_values and abs(alt_btc - last_alt_values[alt_id]) >= ALT_STRENGTH_CHANGE_THRESHOLD:
                    send_telegram_alert(f"{alt_id.upper()}/BTC changed significantly: {last_alt_values[alt_id]:.6f} → {alt_btc:.6f}")
                
                last_alt_values[alt_id] = alt_btc
        else:
            print("Failed to fetch ALT/BTC strength.")

        time.sleep(300)  # Fetch data every 5 minutes

if __name__ == "__main__":
    main()
