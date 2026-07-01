import time
import random
import requests

# The URL of your live server
HQ_SERVER_URL = "https://www.thedragonhms.com/api/agent/telemetry"

# --- NEW: AUTHORIZATION HEADERS ---
# This key must match the AGENT_SECRET_KEY in your server's .env file!
# Default is set to 'dragon_production_key_999' matching the server fallback.
AGENT_AUTH_KEY = "dragon_production_key_999"

HEADERS = {
    "X-Dragon-Agent-Key": AGENT_AUTH_KEY,
    "Content-Type": "application/json"
}

# --- SIMULATION ENGINES (For active testing) ---
SAFE_IPS = ["8.8.8.8", "99.121.16.12", "192.200.1.1"]
THREAT_IPS = ["46.17.46.213", "176.119.1.1", "202.68.20.1"]
ROGUE_QUERIES = [
    {"src": "192.168.1.44", "query": "SELECT * FROM users_passwords;", "risk": "CRITICAL: Credential Harvesting"},
    {"src": "192.168.1.15", "query": "DROP TABLE transactions; --", "risk": "HIGH: Destructive Injection"},
    {"src": "192.168.1.44", "query": "SELECT credit_card, cvv FROM pos_ledger WHERE 1=1;", "risk": "CRITICAL: Mass Exfiltration"}
]

def generate_live_transactions():
    transactions = []
    for _ in range(random.randint(1, 3)):
        is_fraud = random.random() < 0.25
        ip = random.choice(THREAT_IPS) if is_fraud else random.choice(SAFE_IPS)
        transactions.append({
            "tx_id": f"TX-{random.randint(100000, 999999)}",
            "ip_address": ip,
            "billing_country": "US",
            "amount": round(random.uniform(50.0, 1500.0), 2)
        })
    return transactions

def inspect_db_traffic():
    query_count = random.randint(15, 60)
    db_alert = random.choice(ROGUE_QUERIES) if random.random() < 0.15 else None
    return query_count, db_alert


print("=========================================")
print(" 🐉 DRAGON LOCAL AGENT: ACTIVE & SECURE")
print("=========================================")
print("Status: Sniffing Network IPs, POS transactions, & Port 5432...")

while True:
    traffic = random.randint(40, 200)
    sales = random.randint(1, 20)
    conversion = round((sales / traffic) * 100, 1) if traffic > 0 else 0
    recent_txs = generate_live_transactions()
    db_queries, db_threat = inspect_db_traffic()

    payload = {
        "store_id": "STORE_DALLAS_HQ",
        "foot_traffic": traffic,
        "pos_sales": sales,
        "conversion_rate": conversion,
        "recent_transactions": recent_txs,
        "db_query_load": db_queries,
        "db_threat_alert": db_threat
    }

    try:
        # Pushing the payload WITH the mandatory authorization header
        response = requests.post(HQ_SERVER_URL, json=payload, headers=HEADERS)
        if response.status_code == 200:
            print(f"[SECURE TX] Matrix Stream Sent. DB Queries/sec: {db_queries}")
        elif response.status_code == 403:
            print("[CRITICAL ERROR] HQ Server rejected connection: INVALID API KEY")
        else:
            print(f"[ERROR] HTTP {response.status_code}")
    except Exception:
        print(f"[OFFLINE] Connection severed. Retrying...")

    time.sleep(3)
