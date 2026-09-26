import os
import sys
import time
import re
import socket
import subprocess
import threading
import webbrowser

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def stream_tunnel_output(proc, url_container):
    url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
    for line in iter(proc.stderr.readline, ''):
        if not line:
            break
        match = url_pattern.search(line)
        if match and not url_container:
            url_container.append(match.group(0))

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, "backend")
    cloudflared_path = os.path.join(root_dir, "cloudflared.exe")

    print("\n" + "="*70)
    print("🚀 STARTING BRANDCENTRAL COURIER TRACKING SERVER...")
    print("="*70 + "\n")

    # 1. Start backend server
    print("[1/2] Starting backend API on 0.0.0.0:8000...")
    backend_proc = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=backend_dir,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )

    time.sleep(2)
    local_ip = get_local_ip()
    local_url = f"http://{local_ip}:8000"

    # 2. Start Cloudflare Tunnel if available
    tunnel_url = None
    tunnel_proc = None
    if os.path.exists(cloudflared_path):
        print("[2/2] Generating secure public link via Cloudflare Tunnel...")
        tunnel_proc = subprocess.Popen(
            [cloudflared_path, "tunnel", "--url", "http://localhost:8000"],
            cwd=root_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        url_container = []
        t = threading.Thread(target=stream_tunnel_output, args=(tunnel_proc, url_container), daemon=True)
        t.start()

        for _ in range(30):
            if url_container:
                tunnel_url = url_container[0]
                break
            time.sleep(0.5)

    print("\n" + "="*70)
    print("🎉 SERVER READY! SABHI USERS IS LINK KO CHROME ME OPEN KAR SAKTE HAIN:")
    print("   (Kisi bhi user ke PC me Python install karne ki zaroorat NAHI hai!)")
    print("="*70)
    print(f"\n1️⃣  OFFICE WI-FI LINK (Sabhi office teammates ke liye):")
    print(f"    👉  {local_url}")

    if tunnel_url:
        print(f"\n2️⃣  WORLDWIDE PUBLIC LINK (Kahi se bhi - Phone, Laptop, Ghar se):")
        print(f"    👉  {tunnel_url}")

    print("\n" + "="*70)
    print("⚡ Fast Indian IP Scraping active - XpressBees, Delhivery, Ekart, Shadowfax")
    print("⚡ Is window ko open rehne dein. Server band karne ke liye Ctrl + C dabayein.")
    print("="*70 + "\n")

    # Automatically open in browser
    open_target = tunnel_url if tunnel_url else local_url
    webbrowser.open(open_target)

    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping servers...")
        backend_proc.terminate()
        if tunnel_proc:
            tunnel_proc.terminate()
        print("Servers stopped.")

if __name__ == "__main__":
    main()
