import nmap

def run_scan(target_ip="127.0.0.1", arguments="-F"):
    """
    Runs an Nmap scan and returns the raw JSON dictionary.
    No database required.
    """
    print(f"[*] Executing Nmap scan on {target_ip}...")
    nm = nmap.PortScanner()
    nm.scan(hosts=target_ip, arguments=arguments)
    
    # Just return the raw dictionary payload
    return nm._scan_result
