import socket
import re
import time
import concurrent.futures
from threading import Lock
import requests
import os
import random
import zipfile

# --- Configuration ---
IS_GITHUB = os.getenv('GITHUB_ACTIONS') == 'true'
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

BRIDGE_SOURCES = [
    {"type": "obfs4", "url": "https://raw.githubusercontent.com/scriptzteam/Tor-Bridges-Collector/main/bridges-obfs4", "output_file": "working_obfs4.txt"},
    {"type": "webtunnel", "url": "https://raw.githubusercontent.com/scriptzteam/Tor-Bridges-Collector/main/bridges-webtunnel", "output_file": "working_webtunnel.txt"},
    {"type": "vanilla", "url": "https://github.com/scriptzteam/Tor-Bridges-Collector/raw/refs/heads/main/bridges-vanilla", "output_file": "working_vanilla.txt"}
]

# تنظیم مسیر برای ویندوز
if not IS_GITHUB:
    for source in BRIDGE_SOURCES:
        source['output_file'] = os.path.join(r"C:\PyCharm\All\tor", source['output_file'])

MAX_WORKERS = 100
CONNECTION_TIMEOUT = 10
MAX_RETRIES = 2
file_lock = Lock()

def test_bridge(bridge_line):
    try:
        if not bridge_line or len(bridge_line) < 10: return None
        
        # تشخیص Host و Port
        if "obfs4" in bridge_line.lower():
            match = re.search(r'(\d{1,3}(?:\.\d{1,3}){3}:\d+)', bridge_line)
            addr = match.group(1) if match else None
        elif "https" in bridge_line.lower():
            match = re.search(r'https://([^/:]+)(?::(\d+))?', bridge_line)
            addr = f"{match.group(1)}:{match.group(2) or 443}" if match else None
        else:
            addr = bridge_line.split()[0] if ":" in bridge_line.split()[0] else None

        if addr:
            host, port = addr.split(':')
            sock = socket.create_connection((host, int(port)), timeout=CONNECTION_TIMEOUT)
            sock.close()
            return bridge_line
    except: pass
    return None

def send_to_telegram(file_path):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            # ارسال فایل با کپشن حاوی زمان و آمار
            response = requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': f"🔄 Tor Bridges Update\n📅 {time.ctime()}"}, files={'document': f})
        print(f"Telegram Response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Telegram Error: {e}")

def main():
    print(f"Starting execution. Environment: {'GitHub' if IS_GITHUB else 'Local'}")
    
    generated_files = []
    
    for source in BRIDGE_SOURCES:
        # در ویندوز فقط وانیلا، در گیت هاب همه
        if not IS_GITHUB and source['type'] != 'vanilla': continue
        
        print(f"Processing {source['type']}...")
        try:
            response = requests.get(source['url'], timeout=20)
            bridges = [line.strip() for line in response.text.splitlines() if line.strip() and not line.startswith('#')]
        except: continue

        # محدودیت 1000 تایی فقط برای وانیلا در لوکال
        if not IS_GITHUB and source['type'] == 'vanilla' and len(bridges) > 1000:
            bridges = random.sample(bridges, 1000)

        working_list = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(test_bridge, bridges))
            working_list = [r for r in results if r]

        with open(source['output_file'], 'w', encoding='utf-8') as f:
            for line in working_list:
                f.write(line + '\n')
        
        generated_files.append(source['output_file'])
        print(f"Found {len(working_list)} working bridges for {source['type']}")

    # فشرده‌سازی
    zip_name = "Tor_Bridges_Configs.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in generated_files:
            if os.path.exists(file):
                zipf.write(file, os.path.basename(file))
    
    print(f"Created ZIP: {zip_name}")

    if IS_GITHUB:
        send_to_telegram(zip_name)

if __name__ == "__main__":
    main()
