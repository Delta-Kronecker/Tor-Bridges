import socket
import re
import time
import concurrent.futures
from threading import Lock
import requests
import os

# --- Configuration ---
# مسیرها برای سازگاری با GitHub Actions به صورت محلی تنظیم شده‌اند
BRIDGE_SOURCES = [
    {
        "type": "obfs4",
        "url": "https://raw.githubusercontent.com/scriptzteam/Tor-Bridges-Collector/main/bridges-obfs4",
        "output_file": "working_obfs4.txt",
    },
    {
        "type": "webtunnel",
        "url": "https://raw.githubusercontent.com/scriptzteam/Tor-Bridges-Collector/main/bridges-webtunnel",
        "output_file": "working_webtunnel.txt",
    },
    {
        "type": "vanilla",
        "url": "https://github.com/scriptzteam/Tor-Bridges-Collector/raw/refs/heads/main/bridges-vanilla",
        "output_file": "working_vanilla.txt",
    }
]

MAX_WORKERS = min(100, (os.cpu_count() or 1) * 10) # افزایش تعداد ورکرها برای سرعت بیشتر
CONNECTION_TIMEOUT = 10
MAX_RETRIES = 2 

file_lock = Lock()
stats = {}

def get_bridges_from_source(source):
    """دریافت تمامی پل‌ها بدون محدودیت تعداد"""
    try:
        response = requests.get(source['url'], timeout=15)
        response.raise_for_status()
        # فیلتر کردن خطوط خالی و کامنت‌ها
        return [line.strip() for line in response.text.splitlines() if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"Error fetching {source['type']}: {e}")
        return []

def test_bridge(bridge_line):
    """تست اتصال سوکت به پل"""
    parts = bridge_line.split()
    if not parts: return None
    
    bridge_type_candidate = parts[0].lower()
    host, port = None, None

    try:
        if bridge_type_candidate == "obfs4":
            match = re.search(r'(\d{1,3}(?:\.\d{1,3}){3}:\d+)', bridge_line)
            if match:
                address = match.group(1)
                host, port_str = address.split(':')
                port = int(port_str)

        elif bridge_type_candidate == "webtunnel":
            if len(parts) >= 2:
                url_part = parts[1]
                match = re.search(r'https://([^/:]+)(?::(\d+))?', url_part)
                if match:
                    host = match.group(1)
                    port = int(match.group(2)) if match.group(2) else 443

        else:
            # منطق پل‌های Vanilla (آدرس IP:Port در ابتدای خط)
            match = re.search(r'^(\d{1,3}(?:\.\d{1,3}){3}):(\d+)', parts[0])
            if match:
                host = match.group(1)
                port = int(match.group(2))
            
    except: return None

    if not host or not port: return None

    for _ in range(MAX_RETRIES):
        try:
            sock = socket.create_connection((host, port), timeout=CONNECTION_TIMEOUT)
            sock.close()
            return bridge_line
        except:
            time.sleep(0.5)
    return None

def process_source(source_config):
    b_type = source_config['type']
    print(f"\n[+] Scanning {b_type.upper()} bridges...")
    
    bridges = get_bridges_from_source(source_config)
    total_found = len(bridges)
    
    if total_found == 0:
        stats[b_type] = {"total": 0, "working": 0}
        return

    # آماده‌سازی فایل خروجی
    with open(source_config['output_file'], 'w', encoding='utf-8') as f: 
        f.write("")
    
    working_count = 0
    
    # استفاده از tqdm در صورت نصب بودن
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_bridge = {executor.submit(test_bridge, b): b for b in bridges}
        iterator = concurrent.futures.as_completed(future_to_bridge)
        
        if use_tqdm:
            iterator = tqdm(iterator, total=total_found, desc=f"Testing {b_type}")

        for future in iterator:
            result = future.result()
            if result:
                working_count += 1
                with file_lock:
                    with open(source_config['output_file'], 'a', encoding='utf-8') as f:
                        f.write(result + '\n')
    
    stats[b_type] = {"total": total_found, "working": working_count}

def main():
    start_time = time.time()
    for source in BRIDGE_SOURCES:
        process_source(source)
    
    # --- چاپ گزارش نهایی دقیق ---
    print("\n" + "="*60)
    print(f"{'BRIDGE TYPE':<15} | {'TOTAL':<10} | {'WORKING':<10} | {'HEALTH'}")
    print("-" * 60)
    
    total_all = 0
    working_all = 0
    
    for b_type, data in stats.items():
        total = data['total']
        working = data['working']
        health_pct = (working/total)*100 if total > 0 else 0
        print(f"{b_type.upper():<15} | {total:<10} | {working:<10} | {health_pct:.1f}%")
        total_all += total
        working_all += working
    
    print("-" * 60)
    final_health = (working_all/total_all)*100 if total_all > 0 else 0
    print(f"{'OVERALL':<15} | {total_all:<10} | {working_all:<10} | {final_health:.1f}%")
    print(f"Execution Time: {time.time() - start_time:.2f} seconds")
    print("="*60)

if __name__ == "__main__":
    main()
