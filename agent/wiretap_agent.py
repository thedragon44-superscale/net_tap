import os
import requests
from dotenv import load_dotenv
from scanner import run_scan
from sniffer import run_sniff

# --- CONFIGURATION ---
load_dotenv()

# The destination URL of your cloud server
# The destination URL of your cloud server
CLOUD_ENDPOINT = os.getenv("DRAGON_CLOUD_URL", "https://net-tap.onrender.com/api/wiretap/ingest")
AGENT_SECRET_KEY = os.getenv("AGENT_SECRET_KEY", "dragon_production_key_999")
USER_EMAIL = os.getenv("AGENT_USER_EMAIL", "edge_operative@system.local")

def push_intelligence_to_cloud(scan_type: str, scan_data: dict):
    """Packages the raw scan data and POSTs it to the Dragon HMS cloud."""
    payload = {
        "user_email": USER_EMAIL,
        "scan_type": scan_type,
        "scan_data": scan_data
    }
    
    headers = {
        "X-Dragon-Agent-Key": AGENT_SECRET_KEY,
        "Content-Type": "application/json"
    }
    
    print(f"[*] Uplinking {scan_type.upper()} intelligence to Dragon HMS...")
    try:
        response = requests.post(CLOUD_ENDPOINT, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            print("[+] MATRIX ACCEPTED PAYLOAD.")
        else:
            print(f"[!] MATRIX REJECTED PAYLOAD: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"[!] CLOUD UPLINK FAILED: Connection dropped. {e}")

def execute_agent_cycle():
    print("===============================================")
    print("      WIRETAP EDGE AGENT INITIALIZED           ")
    print("===============================================")
    
    # 1. Execute Network Sweep
    print("\n[*] Initiating Nmap perimeter sweep...")
    try:
        # Calling the exact function from our new scanner.py
        nmap_results = run_scan() 
        push_intelligence_to_cloud("nmap", nmap_results)
    except Exception as e:
        print(f"[!] Scanner module encountered an error: {e}")

    # 2. Execute Packet Capture
    print("\n[*] Initiating PyShark packet capture...")
    try:
        # Calling the exact function from our new sniffer.py
        pcap_results = run_sniff()
        push_intelligence_to_cloud("pcap", pcap_results)
    except Exception as e:
        print(f"[!] Sniffer module encountered an error: {e}")

if __name__ == "__main__":
    execute_agent_cycle()
