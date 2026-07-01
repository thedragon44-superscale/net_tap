import pyshark
import base64

def run_sniff(interface="wlo1", packet_count=20):
    """
    Captures packets on the specified interface, extracts raw TCP payloads,
    and returns a summary dictionary. No database required.
    """
    # NOTE: You may need to change "eth0" to your actual network interface (e.g., "wlan0")
    print(f"[*] Starting packet capture on {interface} ({packet_count} packets)...")
    
    capture = pyshark.LiveCapture(interface=interface)
    capture.sniff(packet_count=packet_count)
    
    packets_summary = []
    
    for pkt in capture:
        try:
            protocol = pkt.highest_layer
            src_ip = pkt.ip.src if hasattr(pkt, 'ip') else "N/A"
            dst_ip = pkt.ip.dst if hasattr(pkt, 'ip') else "N/A"
            length = pkt.length
            
            # Extract Raw Byte Payloads
            hex_payload = None
            base64_payload = None
            utf8_payload = None
            
            if hasattr(pkt, 'tcp') and hasattr(pkt.tcp, 'payload'):
                # 1. Clean the raw hex string from PyShark
                hex_payload = pkt.tcp.payload.replace(':', '')
                try:
                    # 2. Convert to raw bytes
                    raw_bytes = bytes.fromhex(hex_payload)
                    # 3. Encode to Base64 for safe JSON storage
                    base64_payload = base64.b64encode(raw_bytes).decode('ascii')
                    # 4. Attempt readable text decode
                    utf8_payload = raw_bytes.decode('utf-8', errors='replace')
                except Exception as e:
                    utf8_payload = f"[Decoding Error: {e}]"
            
            packets_summary.append({
                "protocol": protocol,
                "source": src_ip,
                "destination": dst_ip,
                "length": length,
                "payload_raw_hex": hex_payload,
                "payload_base64": base64_payload,
                "payload_utf8": utf8_payload
            })
        except AttributeError:
            continue
            
    # Wrap it in a dictionary so it matches the format the agent expects
    return {"alerts": packets_summary}
