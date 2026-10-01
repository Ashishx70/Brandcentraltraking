from .base import BaseScraper
import asyncio
import os
import json
import re
import hashlib
import base64
from datetime import datetime
import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


def solve_altcha(challenge: str, salt: str, max_num: int = 100000) -> int:
    """
    Pure Python solver for Altcha SHA-256 Proof-of-Work challenge (~0.015s).
    Requires zero external browser or node dependencies.
    """
    salt_bytes = salt.encode('utf-8')
    for num in range(max_num + 1):
        if hashlib.sha256(salt_bytes + str(num).encode('utf-8')).hexdigest() == challenge:
            return num
    return None


def fetch_xpressbees_official_web(clean_awb: str) -> dict:
    """
    Direct official XpressBees web tracking API (0.3s - 0.5s).
    Interacts directly with https://www.xpressbees.com/api/tracking using
    an ultra-fast pure Python Altcha challenge solver.
    """
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.xpressbees.com",
        "Referer": f"https://www.xpressbees.com/shipment/tracking?awbNo={clean_awb}"
    }

    try:
        # 1. Fetch challenge from Altcha API
        r_ch = session.get("https://altcha-api.xbees.in/v1/challenge", headers=headers, timeout=5)
        if r_ch.status_code == 200:
            ch_data = r_ch.json()
            num = solve_altcha(ch_data["challenge"], ch_data["salt"], ch_data.get("maxnumber", 100000))
            if num is not None:
                payload_obj = {
                    "algorithm": ch_data.get("algorithm", "SHA-256"),
                    "challenge": ch_data["challenge"],
                    "number": num,
                    "salt": ch_data["salt"],
                    "signature": ch_data["signature"]
                }
                altcha_b64 = base64.b64encode(json.dumps(payload_obj).encode('utf-8')).decode('utf-8')

                # 2. Query official web tracking endpoint
                track_url = "https://www.xpressbees.com/api/tracking"
                req_body = {"awbNo": clean_awb, "altchaPayload": altcha_b64}
                print(f"[XPRESSBEES WEB API] >>> Sending POST to {track_url} for AWB: {clean_awb}")
                track_res = session.post(track_url, json=req_body, headers=headers, timeout=7)
                print(f"[XPRESSBEES WEB API] <<< Response status: {track_res.status_code}")

                if track_res.status_code == 200:
                    data = track_res.json()
                    shipments = data.get("domestic") or data.get("international") or []
                    if shipments:
                        ship = shipments[0]
                        shipping_id = str(ship.get("shippingId") or clean_awb).strip()
                        raw_status = (ship.get("status") or "").strip()
                        origin = (ship.get("origin") or "").strip()
                        shipping_date = (ship.get("shippingDate") or "-").strip()

                        st_upper = raw_status.upper()
                        if "DLVD" in st_upper or "DELIVER" in st_upper:
                            status = "Delivered"
                        elif "RTO" in st_upper or "RETURN" in st_upper:
                            status = "Returned"
                        elif "TRANSIT" in st_upper:
                            status = "In Transit"
                        elif "PICK" in st_upper:
                            status = "Picked Up"
                        elif "OUT" in st_upper:
                            status = "Out for Delivery"
                        elif raw_status:
                            status = raw_status.title()
                        else:
                            status = "In Transit"

                        events = []
                        last_location = origin or "In Transit"
                        timestamp = shipping_date

                        # 3. Fetch detailed event history
                        try:
                            r_hist = session.get(f"https://www.xpressbees.com/api/tracking/{shipping_id}", headers=headers, timeout=5)
                            if r_hist.status_code == 200:
                                hist_data = r_hist.json()
                                event_list = hist_data.get("data") or []
                                for ev in event_list:
                                    events.append({
                                        "time": ev.get("shipmentDate") or "-",
                                        "status": ev.get("label") or "",
                                        "location": ev.get("location") or ""
                                    })
                                if event_list:
                                    first_ev = event_list[0]
                                    last_location = first_ev.get("location") or last_location
                                    timestamp = first_ev.get("shipmentDate") or timestamp
                        except Exception as hist_err:
                            print(f"[XPRESSBEES WEB API] Event history warning: {hist_err}")

                        result = {
                            "success": True,
                            "status": status,
                            "last_location": last_location,
                            "timestamp": timestamp,
                            "events": events
                        }
                        print(f"[XPRESSBEES WEB API] <<< Found: Status={status}, Loc={last_location}, Time={timestamp}")
                        return result
    except Exception as e:
        print(f"[XPRESSBEES WEB API] Request error: {e}")

    return {"success": False}


def fetch_xpressbees_direct_api(clean_awb: str) -> dict:
    """
    Direct official XpressBees shipment API (0.2s - 0.4s).
    Extracted from XpressBees Vite portal (shipmentv2.xpressbees.com).
    Requires no captcha and no authentication token.
    """
    url = "https://xbshipmentstatustracking.xbees.in/api/v1/webhookTracking/find"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Origin": "https://shipmentv2.xpressbees.com",
        "Referer": "https://shipmentv2.xpressbees.com/orders/tracking",
        "Accept": "application/json, text/plain, */*"
    }
    print(f"\n[XPRESSBEES API] >>> Sending POST Request to: {url}")
    payload = {"AWBNO": clean_awb}
    print(f"[XPRESSBEES API] >>> Request Payload JSON: {json.dumps(payload)}")
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=6)
        print(f"[XPRESSBEES API] <<< Response Status Code: {r.status_code}")
        if r.status_code == 200:
            res = r.json()
            print(f"[XPRESSBEES API] <<< Raw Response JSON for {clean_awb}:")
            print(json.dumps(res, indent=2, ensure_ascii=False))
            if res.get("status") and res.get("data"):
                data = res["data"]
                shipment = data.get("shipment", {}) or {}
                tracking = data.get("tracking", []) or []

                raw_status = (shipment.get("ship_status") or "").strip()
                st_clean = raw_status.replace("-", " ").replace("_", " ")
                st_lower = st_clean.lower()

                if "deliver" in st_lower and "fail" not in st_lower and "not" not in st_lower:
                    status = "Delivered"
                elif "rto" in st_lower or "return" in st_lower:
                    status = "Returned"
                elif "out for delivery" in st_lower:
                    status = "Out for Delivery"
                elif "out for pickup" in st_lower:
                    status = "Out for Pickup"
                elif "picked" in st_lower:
                    status = "Picked Up"
                elif "fail" in st_lower or "undeliver" in st_lower:
                    status = "Delivery Failed"
                elif "transit" in st_lower:
                    status = "In Transit"
                elif st_clean:
                    status = st_clean.title()
                else:
                    status = "In Transit"

                events = []
                for ev in tracking:
                    ev_act = (ev.get("activity") or ev.get("status") or "").strip()
                    ev_loc = (ev.get("location") or "").strip()
                    ev_date = ev.get("date") or ""
                    if not ev_date and ev.get("event_time"):
                        try:
                            ev_date = datetime.fromtimestamp(int(ev["event_time"])).strftime("%d-%b-%Y %I:%M %p")
                        except Exception:
                            ev_date = "-"
                    events.append({
                        "time": ev_date or "-",
                        "status": ev_act,
                        "location": ev_loc
                    })

                last_location = ""
                timestamp = "-"
                if events:
                    last_location = events[0].get("location") or ""
                    timestamp = events[0].get("time") or "-"
                elif shipment.get("current_location"):
                    last_location = shipment["current_location"]

                if not last_location:
                    last_location = status

                return {
                    "success": True,
                    "status": status,
                    "last_location": last_location,
                    "timestamp": timestamp,
                    "events": events
                }
    except Exception as e:
        print(f"[Xpressbees] Direct API fetch failed: {e}")

    return {"success": False}


def fetch_trackcourier_http(clean_awb: str) -> dict:
    """
    Direct HTTP scraper for TrackCourier.io (0.8s - 1.2s).
    Uses lightweight requests + BeautifulSoup without launching Playwright.
    """
    url = f"https://trackcourier.io/track-and-trace/xpressbees-logistics/{clean_awb}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    print(f"\n[TRACKCOURIER HTTP] >>> Sending GET Request to: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=8)
        print(f"[TRACKCOURIER HTTP] <<< Response Status Code: {r.status_code}")
        if r.status_code == 200:
            checkpoints = []
            if BeautifulSoup is not None:
                soup = BeautifulSoup(r.text, "html.parser")
                items = soup.select("li.checkpoint")
                for item in items:
                    t_el = item.select_one(".checkpoint__time")
                    act_el = item.select_one(".checkpoint__content strong span:not(.checkpoint__courier-name)")
                    loc_el = item.select_one(".checkpoint__content .hint")

                    t_str = t_el.get_text(strip=True) if t_el else ""
                    act_str = act_el.get_text(strip=True) if act_el else ""
                    loc_str = loc_el.get_text(strip=True) if loc_el else ""

                    if "||" in t_str or "||" in act_str:
                        continue

                    if "no information is available" in act_str.lower() or "no records" in act_str.lower():
                        res_obj = {
                            "success": True,
                            "status": "Invalid AWB / Not Found",
                            "last_location": "No records found on XpressBees portal",
                            "timestamp": "-",
                            "events": []
                        }
                        print(f"[TRACKCOURIER HTTP] <<< Parsed Data JSON for {clean_awb}:")
                        print(json.dumps(res_obj, indent=2, ensure_ascii=False))
                        return res_obj

                    if act_str or loc_str:
                        checkpoints.append({
                            "time": t_str,
                            "status": act_str,
                            "location": loc_str
                        })
            else:
                # Built-in Regex parser fallback (zero dependencies, 100% safe)
                li_matches = re.findall(r'<li[^>]*class="[^"]*checkpoint[^"]*"[^>]*>(.*?)</li>', r.text, re.DOTALL | re.IGNORECASE)
                for li_html in li_matches:
                    time_m = re.search(r'class="[^"]*checkpoint__time[^"]*"[^>]*>(.*?)</div>', li_html, re.DOTALL)
                    act_m = re.search(r'<strong>\s*<span[^>]*>(.*?)</span>', li_html, re.DOTALL)
                    loc_m = re.search(r'class="[^"]*hint[^"]*"[^>]*>(.*?)</div>', li_html, re.DOTALL)

                    t_str = re.sub(r'<[^>]+>', '', time_m.group(1)).strip() if time_m else ""
                    act_str = re.sub(r'<[^>]+>', '', act_m.group(1)).strip() if act_m else ""
                    loc_str = re.sub(r'<[^>]+>', '', loc_m.group(1)).strip() if loc_m else ""

                    if "||" in t_str or "||" in act_str:
                        continue

                    if "no information is available" in act_str.lower() or "no records" in act_str.lower():
                        res_obj = {
                            "success": True,
                            "status": "Invalid AWB / Not Found",
                            "last_location": "No records found on XpressBees portal",
                            "timestamp": "-",
                            "events": []
                        }
                        print(f"[TRACKCOURIER HTTP] <<< Parsed Data JSON for {clean_awb}:")
                        print(json.dumps(res_obj, indent=2, ensure_ascii=False))
                        return res_obj

                    if act_str or loc_str:
                        checkpoints.append({
                            "time": t_str,
                            "status": act_str,
                            "location": loc_str
                        })

            if checkpoints:
                print(f"[TRACKCOURIER HTTP] <<< Checkpoints JSON for {clean_awb}:")
                print(json.dumps(checkpoints, indent=2, ensure_ascii=False))

                latest_cp = checkpoints[0]
                raw_act = latest_cp.get("status", "")
                raw_loc = latest_cp.get("location", "")
                raw_time = latest_cp.get("time", "").replace("\n", " ").strip()

                act_upper = raw_act.upper()
                if "DLVD" in act_upper or "DELIVER" in act_upper:
                    status = "Delivered"
                elif "RTO" in act_upper or "RETURN" in act_upper:
                    status = "Returned"
                elif "TRANSIT" in act_upper or "INTRANSIT" in act_upper:
                    status = "In Transit"
                elif "PICKDONE" in act_upper or "PICKED" in act_upper:
                    status = "Picked Up"
                elif "OUTFORPICKUP" in act_upper:
                    status = "Out for Pickup"
                elif "OUTFORDELIVERY" in act_upper:
                    status = "Out for Delivery"
                elif "FAIL" in act_upper or "UNDELIVER" in act_upper:
                    status = "Delivery Failed"
                elif raw_act:
                    status = raw_act
                else:
                    status = "In Transit"

                if raw_loc and raw_act:
                    last_location = f"{raw_loc} ({raw_act})"
                elif raw_loc:
                    last_location = raw_loc
                elif raw_act:
                    last_location = raw_act
                else:
                    last_location = "In Transit"

                timestamp = raw_time or "-"

                events = []
                for cp in checkpoints:
                    ev_time = cp.get("time", "").replace("\n", " ").replace("·", " ").replace("•", " ").replace("—", " ").strip()
                    events.append({
                        "time": ev_time or "-",
                        "status": cp.get("status", ""),
                        "location": cp.get("location", "")
                    })

                return {
                    "success": True,
                    "status": status,
                    "last_location": last_location,
                    "timestamp": timestamp,
                    "events": events
                }

            # Check additional-info box
            add_info_el = soup.select_one(".additional-info")
            if add_info_el and add_info_el.get_text(strip=True):
                info_text = add_info_el.get_text(strip=True)
                if "no information" in info_text.lower():
                    return {
                        "success": True,
                        "status": "Invalid AWB / Not Found",
                        "last_location": "No records found on XpressBees portal",
                        "timestamp": "-",
                        "events": []
                    }

    except Exception as e:
        print(f"[Xpressbees] TrackCourier HTTP fetch failed: {e}")

    return {"success": False}


def _build_xpressbees_html(awb: str, api_data: dict) -> str:
    """
    Builds a beautiful XpressBees-branded HTML tracking page for headless screenshot.
    Used on Render (Linux) where the Altcha JS worker does not complete.
    """
    status = api_data.get("status", "In Transit")
    last_location = api_data.get("last_location", "-")
    timestamp = api_data.get("timestamp", "-")
    events = api_data.get("events", [])

    # Status badge color
    status_lower = status.lower()
    if any(w in status_lower for w in ["deliver", "dlvd"]):
        badge_color = "#16a34a"
        badge_bg = "#dcfce7"
        dot_color = "#16a34a"
    elif any(w in status_lower for w in ["out for", "transit", "dispatch", "intransit"]):
        badge_color = "#ea580c"
        badge_bg = "#fff7ed"
        dot_color = "#ea580c"
    elif any(w in status_lower for w in ["return", "rto", "cancel"]):
        badge_color = "#dc2626"
        badge_bg = "#fee2e2"
        dot_color = "#dc2626"
    elif any(w in status_lower for w in ["pick", "received", "booked"]):
        badge_color = "#2563eb"
        badge_bg = "#dbeafe"
        dot_color = "#2563eb"
    else:
        badge_color = "#7c3aed"
        badge_bg = "#ede9fe"
        dot_color = "#7c3aed"

    # Build event rows
    events_html = ""
    if events:
        for i, ev in enumerate(events):
            ev_status = ev.get("status", ev.get("activity", "Update"))
            ev_location = ev.get("location", "")
            ev_time = ev.get("timestamp", ev.get("time", ""))
            is_first = i == 0
            dot_style = f"background:{dot_color}; box-shadow: 0 0 0 4px {badge_bg};" if is_first else "background:#d1d5db;"
            text_weight = "font-weight:700; color:#111827;" if is_first else "color:#374151;"
            events_html += f"""
            <div style="display:flex; gap:16px; align-items:flex-start; padding:14px 0; border-bottom:1px solid #f3f4f6;">
                <div style="display:flex; flex-direction:column; align-items:center; padding-top:4px;">
                    <div style="width:14px; height:14px; border-radius:50%; {dot_style} flex-shrink:0;"></div>
                    {"" if i == len(events)-1 else '<div style="width:2px; flex:1; background:#e5e7eb; margin-top:4px; min-height:24px;"></div>'}
                </div>
                <div style="flex:1; min-width:0;">
                    <div style="{text_weight} font-size:14px; line-height:1.4;">{ev_status}</div>
                    {f'<div style="font-size:12px; color:#6b7280; margin-top:2px;">📍 {ev_location}</div>' if ev_location else ''}
                    {f'<div style="font-size:12px; color:#9ca3af; margin-top:2px;">🕐 {ev_time}</div>' if ev_time else ''}
                </div>
            </div>"""
    else:
        events_html = '<div style="color:#6b7280; font-size:14px; padding:20px 0;">No event history available.</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XpressBees Tracking - {awb}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f8fafc;
    color: #1f2937;
    min-height: 100vh;
  }}
  .header {{
    background: linear-gradient(135deg, #ff6b00 0%, #ff8c00 50%, #e55a00 100%);
    padding: 18px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 12px rgba(255,107,0,0.3);
  }}
  .logo-area {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .logo-icon {{
    width: 42px;
    height: 42px;
    background: white;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    font-weight: 900;
    color: #ff6b00;
    letter-spacing: -1px;
  }}
  .logo-text {{
    color: white;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.5px;
  }}
  .logo-sub {{
    color: rgba(255,255,255,0.8);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 1px;
    text-transform: uppercase;
  }}
  .header-awb {{
    background: rgba(255,255,255,0.2);
    color: white;
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 600;
    border: 1px solid rgba(255,255,255,0.3);
  }}
  .container {{
    max-width: 900px;
    margin: 24px auto;
    padding: 0 24px;
  }}
  .card {{
    background: white;
    border-radius: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.04);
    overflow: hidden;
    margin-bottom: 20px;
  }}
  .card-header {{
    padding: 18px 24px;
    border-bottom: 1px solid #f3f4f6;
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .card-title {{
    font-size: 16px;
    font-weight: 700;
    color: #111827;
  }}
  .card-body {{
    padding: 20px 24px;
  }}
  .status-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 700;
    background: {badge_bg};
    color: {badge_color};
    border: 1.5px solid {badge_color}22;
  }}
  .status-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: {badge_color};
    animation: pulse 1.5s infinite;
  }}
  @keyframes pulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.6; transform: scale(0.85); }}
  }}
  .info-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
    margin-top: 16px;
  }}
  .info-cell {{
    background: #f9fafb;
    border-radius: 10px;
    padding: 14px 16px;
    border: 1px solid #e5e7eb;
  }}
  .info-label {{
    font-size: 11px;
    font-weight: 600;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
  }}
  .info-value {{
    font-size: 14px;
    font-weight: 600;
    color: #111827;
    line-height: 1.3;
  }}
  .section-icon {{
    width: 28px;
    height: 28px;
    background: #fff7ed;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
  }}
  .footer {{
    text-align: center;
    padding: 16px;
    color: #9ca3af;
    font-size: 11px;
  }}
</style>
</head>
<body>
<div class="header">
  <div class="logo-area">
    <div class="logo-icon">XB</div>
    <div>
      <div class="logo-text">XpressBees</div>
      <div class="logo-sub">Shipment Tracking</div>
    </div>
  </div>
  <div class="header-awb">AWB: {awb}</div>
</div>

<div class="container">
  <!-- Shipping Details Card -->
  <div class="card">
    <div class="card-header">
      <div class="section-icon">📦</div>
      <div class="card-title">Shipping Details</div>
    </div>
    <div class="card-body">
      <div class="status-badge">
        <div class="status-dot"></div>
        {status}
      </div>
      <div class="info-grid">
        <div class="info-cell">
          <div class="info-label">AWB Number</div>
          <div class="info-value">{awb}</div>
        </div>
        <div class="info-cell">
          <div class="info-label">Last Location</div>
          <div class="info-value">{last_location if last_location and last_location != "-" else "—"}</div>
        </div>
        <div class="info-cell">
          <div class="info-label">Last Updated</div>
          <div class="info-value">{timestamp if timestamp and timestamp != "-" else "—"}</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Shipment History Card -->
  <div class="card">
    <div class="card-header">
      <div class="section-icon">🕐</div>
      <div class="card-title">Shipment History</div>
      <span style="margin-left:auto; font-size:12px; color:#9ca3af;">{len(events)} events</span>
    </div>
    <div class="card-body">
      {events_html}
    </div>
  </div>
</div>

<div class="footer">
  Powered by XpressBees Logistics · xpressbees.com
</div>
</body>
</html>"""


class XpressBeesScraper(BaseScraper):
    async def track(self, awb: str, capture_screenshot: bool = False) -> dict:
        clean_awb = str(awb).strip()

        # ==========================================================
        # 1. PRIMARY TIER: Official Web Tracking API (Altcha PoW) (~0.4s)
        # ==========================================================
        try:
            web_res = await asyncio.to_thread(fetch_xpressbees_official_web, clean_awb)
            if web_res.get("success"):
                screenshot_path = "-"
                if capture_screenshot:
                    screenshot_path = await self._capture_screenshot(clean_awb, api_data=web_res)
                return {
                    "status": web_res["status"],
                    "last_location": web_res["last_location"],
                    "timestamp": web_res["timestamp"],
                    "screenshot": screenshot_path,
                    "events": web_res.get("events", [])
                }
        except Exception as e:
            print(f"[Xpressbees] Primary Web API error: {e}")

        # ==========================================================
        # 2. SECONDARY TIER: Direct Official XpressBees V2 API (~0.2s - 0.4s)
        # ==========================================================
        try:
            api_res = await asyncio.to_thread(fetch_xpressbees_direct_api, clean_awb)
            if api_res.get("success"):
                screenshot_path = "-"
                if capture_screenshot:
                    screenshot_path = await self._capture_screenshot(clean_awb, api_data=api_res)
                return {
                    "status": api_res["status"],
                    "last_location": api_res["last_location"],
                    "timestamp": api_res["timestamp"],
                    "screenshot": screenshot_path,
                    "events": api_res.get("events", [])
                }
        except Exception as e:
            print(f"[Xpressbees] Secondary V2 API error: {e}")

        # ==========================================================
        # 2. FAST TIER 2: Direct HTTP TrackCourier Fetch (~0.8s - 1.2s)
        # ==========================================================
        try:
            tc_res = await asyncio.to_thread(fetch_trackcourier_http, clean_awb)
            if tc_res.get("success"):
                if not capture_screenshot:
                    return {
                        "status": tc_res["status"],
                        "last_location": tc_res["last_location"],
                        "timestamp": tc_res["timestamp"],
                        "screenshot": "-",
                        "events": tc_res.get("events", [])
                    }
                else:
                    screenshot_path = await self._capture_screenshot(clean_awb, api_data=tc_res)
                    return {
                        "status": tc_res["status"],
                        "last_location": tc_res["last_location"],
                        "timestamp": tc_res["timestamp"],
                        "screenshot": screenshot_path,
                        "events": tc_res.get("events", [])
                    }
        except Exception as e:
            print(f"[Xpressbees] Tier 2 TrackCourier error: {e}")

        # ==========================================================
        # 3. FALLBACK: Default cleanly in < 2 seconds total
        # ==========================================================
        screenshot_path = "-"
        if capture_screenshot:
            screenshot_path = await self._capture_screenshot(clean_awb)

        return {
            "status": "Invalid AWB / Not Found",
            "last_location": "No records found on XpressBees portal",
            "timestamp": "-",
            "screenshot": screenshot_path,
            "events": []
        }

    async def _capture_screenshot(self, clean_awb: str, api_data: dict = None) -> str:
        """
        Official XpressBees site screenshot — both Render (Linux) and Windows.
        Strategy: Python solves Altcha challenge, injects token into browser form,
        submits, waits for tracking page to load, takes screenshot.
        CONFIRMED: Server accepts independently-fetched Altcha tokens (tested).
        """
        page = None
        try:
            try:
                from browser.playwright_manager import playwright_manager
            except ImportError:
                import sys as _sys2
                backend_dir2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if backend_dir2 not in _sys2.path:
                    _sys2.path.insert(0, backend_dir2)
                from browser.playwright_manager import playwright_manager

            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            screenshot_filename = f"{clean_awb}_Xpressbees.png"
            screenshot_file = os.path.join(backend_dir, "static", "screenshots", screenshot_filename)
            os.makedirs(os.path.dirname(screenshot_file), exist_ok=True)

            # ─────────────────────────────────────────────────────────────
            # STEP 1: Solve Altcha in Python (works on any OS, any env)
            # ─────────────────────────────────────────────────────────────
            solved_token = None
            try:
                import requests as _req
                _headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Origin": "https://www.xpressbees.com",
                    "Referer": f"https://www.xpressbees.com/shipment/tracking?awbNo={clean_awb}"
                }
                r_ch = _req.get("https://altcha-api.xbees.in/v1/challenge", headers=_headers, timeout=12)
                if r_ch.status_code == 200:
                    ch_data = r_ch.json()
                    num = solve_altcha(ch_data["challenge"], ch_data["salt"], ch_data.get("maxnumber", 100000))
                    if num is not None:
                        payload_obj = {
                            "algorithm": ch_data.get("algorithm", "SHA-256"),
                            "challenge": ch_data["challenge"],
                            "number": num,
                            "salt": ch_data["salt"],
                            "signature": ch_data["signature"]
                        }
                        solved_token = base64.b64encode(json.dumps(payload_obj).encode('utf-8')).decode('utf-8')
                        print(f"[Xpressbees] Altcha solved in Python, token len={len(solved_token)}")
            except Exception as altcha_err:
                print(f"[Xpressbees] Python Altcha solve error: {altcha_err}")

            # ─────────────────────────────────────────────────────────────
            # STEP 2: Open official XpressBees page in Playwright
            # ─────────────────────────────────────────────────────────────
            official_url = f"https://www.xpressbees.com/shipment/tracking?awbNo={clean_awb}"
            page = await playwright_manager.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
            await page.add_init_script("delete navigator.__proto__.webdriver;")
            await page.set_viewport_size({"width": 1440, "height": 900})

            async def intercept(route):
                req = route.request
                url_lower = req.url.lower()
                if req.resource_type in ["media", "font"]:
                    await route.abort()
                    return
                ignored = ["google-analytics", "doubleclick", "adsense", "facebook", "criteo", "pubmatic"]
                if any(kw in url_lower for kw in ignored):
                    await route.abort()
                    return
                await route.continue_()

            await page.route("**/*", intercept)
            await page.goto(official_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(1.5)

            # Remove popups
            await page.evaluate("""() => {
                document.querySelectorAll('div[class*="modal"], div[class*="popup"], div[role="dialog"]').forEach(e => e.remove());
            }""")

            # Check if tracking already loaded (URL with AWB pre-filled sometimes auto-loads)
            content_check = await page.content()
            already_loaded = any(k in content_check for k in [
                "Shipping Details", "Shipment History", "Your Domestic Shipments"
            ])

            if not already_loaded:
                # ─────────────────────────────────────────────────────────────
                # STEP 3: Inject Python-solved token and submit form
                # ─────────────────────────────────────────────────────────────
                if solved_token:
                    injected = await page.evaluate("""(token) => {
                        // Try altcha-widget shadow root
                        const widget = document.querySelector('altcha-widget');
                        if (widget && widget.shadowRoot) {
                            const inp = widget.shadowRoot.querySelector('input[name="altcha"]');
                            if (inp) { inp.value = token; return 'shadow'; }
                        }
                        // Try regular DOM hidden input
                        const inp2 = document.querySelector('input[name="altcha"]');
                        if (inp2) { inp2.value = token; return 'dom'; }
                        // Create and append to form
                        const f = document.querySelector('form');
                        if (f) {
                            let h = document.createElement('input');
                            h.type = 'hidden'; h.name = 'altcha'; h.value = token;
                            f.appendChild(h); return 'created';
                        }
                        return 'not-found';
                    }""", solved_token)
                    print(f"[Xpressbees] Token inject result: {injected}")

                # Click Search button (try multiple selectors)
                clicked = False
                for sel in [
                    'button.sc-fTyFcS.gRKEpD',
                    'button:has(img[alt="Submit Button"])',
                    'button[type="submit"]',
                    'form button'
                ]:
                    try:
                        btn = page.locator(sel).first
                        if await btn.count() > 0:
                            await btn.click()
                            clicked = True
                            print(f"[Xpressbees] Clicked button: {sel}")
                            break
                    except Exception:
                        pass

                if not clicked:
                    await page.evaluate("""() => {
                        const f = document.querySelector('form');
                        if (f && f.requestSubmit) f.requestSubmit();
                        else if (f) f.submit();
                    }""")

                # ─────────────────────────────────────────────────────────────
                # STEP 4: Wait up to 90s for tracking content to appear
                # Also retry submit at intervals if not loaded
                # ─────────────────────────────────────────────────────────────
                results_ready = False
                for attempt in range(90):
                    await asyncio.sleep(1.0)
                    content = await page.content()
                    if any(k in content for k in [
                        "Your Domestic Shipments", "Shipping Details", "Shipment History",
                        "Return Delivered", "Data Received", "DLVD", "Delivered",
                        "RPCancel", "OutForPickUp", "No Records", "No Data Found", "Invalid"
                    ]):
                        results_ready = True
                        break
                    # Retry submit at 15s, 30s, 50s in case first click didn't register
                    if attempt in [15, 30, 50] and solved_token:
                        print(f"[Xpressbees] Retry submit at attempt {attempt}...")
                        await page.evaluate("""() => {
                            const f = document.querySelector('form');
                            if (f && f.requestSubmit) f.requestSubmit();
                        }""")
            else:
                results_ready = True
                print(f"[Xpressbees] Page auto-loaded tracking data!")

            if not results_ready:
                raise Exception("Official XpressBees page did not load tracking data after 40s")

            # ─────────────────────────────────────────────────────────────
            # STEP 5: Expand 'View' → clean → zoom → screenshot
            # ─────────────────────────────────────────────────────────────
            try:
                await page.evaluate("""() => {
                    const all = Array.from(document.querySelectorAll('*'));
                    const viewEl = all.find(e => e.children.length === 0 && e.textContent.trim() === 'View');
                    if (viewEl) viewEl.click();
                }""")
                await asyncio.sleep(1.0)
            except Exception:
                pass

            await page.evaluate("""() => {
                document.querySelectorAll('div[class*="modal"], div[class*="popup"], div[role="dialog"]').forEach(e => e.remove());
                const style = document.createElement('style');
                style.innerHTML = '* { -webkit-font-smoothing: antialiased !important; text-rendering: geometricPrecision !important; }';
                document.head.appendChild(style);
                document.documentElement.style.zoom = '65%';
                window.scrollTo(0, 155);
            }""")
            await asyncio.sleep(0.6)

            await page.screenshot(path=screenshot_file, full_page=False)
            print(f"[Xpressbees] Official screenshot captured: {screenshot_filename}")

            try:
                from services.desktop_frame_service import DesktopFrameService
                DesktopFrameService.apply_frame(
                    web_img_path=screenshot_file,
                    courier_name="Xpressbees",
                    awb=clean_awb,
                    tracking_url=f"https://www.xpressbees.com/track?isawb=Yes&trackid={clean_awb}",
                    output_path=screenshot_file
                )
            except Exception as fe:
                print(f"[DesktopFrame] Xpressbees error: {fe}")

            try:
                from services.drive_service import DriveService
                return await DriveService.upload_and_cleanup(
                    image_path=screenshot_file,
                    courier_name="Xpressbees",
                    clean_awb=clean_awb,
                    fallback_relative_path=f"/static/screenshots/{screenshot_filename}"
                )
            except Exception:
                return f"/static/screenshots/{screenshot_filename}"

        except Exception as e:
            print(f"[Xpressbees] Official screenshot failed: {e} — falling back to TrackCourier.io")
            try:
                if page:
                    await page.goto(
                        f"https://trackcourier.io/track-and-trace/xpressbees-logistics/{clean_awb}",
                        wait_until="domcontentloaded", timeout=10000
                    )
                    await asyncio.sleep(3)
                    card = page.locator(".block.m-b-2, .card, body").first
                    await card.screenshot(path=screenshot_file)
                    try:
                        from services.desktop_frame_service import DesktopFrameService
                        DesktopFrameService.apply_frame(
                            web_img_path=screenshot_file,
                            courier_name="Xpressbees",
                            awb=clean_awb,
                            tracking_url=f"https://www.xpressbees.com/track?isawb=Yes&trackid={clean_awb}",
                            output_path=screenshot_file
                        )
                    except Exception:
                        pass
                    try:
                        from services.drive_service import DriveService
                        return await DriveService.upload_and_cleanup(
                            image_path=screenshot_file,
                            courier_name="Xpressbees",
                            clean_awb=clean_awb,
                            fallback_relative_path=f"/static/screenshots/{screenshot_filename}"
                        )
                    except Exception:
                        return f"/static/screenshots/{screenshot_filename}"
            except Exception as fb_err:
                print(f"[Xpressbees] Fallback also failed: {fb_err}")
            return "-"
        finally:
            if page:
                try:
                    ctx = page.context
                    await page.close()
                    if ctx:
                        await ctx.close()
                except Exception:
                    pass




        page = None
        try:
            try:
                from browser.playwright_manager import playwright_manager
            except ImportError:
                import sys
                backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if backend_dir not in sys.path:
                    sys.path.insert(0, backend_dir)
                from browser.playwright_manager import playwright_manager
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            screenshot_filename = f"{clean_awb}_Xpressbees.png"
            screenshot_file = os.path.join(backend_dir, "static", "screenshots", screenshot_filename)
            os.makedirs(os.path.dirname(screenshot_file), exist_ok=True)

            import sys as _sys

            # ==============================================================
            # HEADLESS PATH (Render / Linux): Intercept browser's Altcha
            # challenge response → solve in Python → inject matched token.
            # Key: We MUST use the SAME challenge the browser fetched,
            # not a separate one, or the server will reject it.
            # ==============================================================
            is_headless_env = (_sys.platform != "win32")
            if is_headless_env:
                print(f"[Xpressbees] Headless env — intercepting Altcha challenge from browser for {clean_awb}")
                captured_challenge = {}  # will be filled by response listener

                try:
                    official_url = f"https://www.xpressbees.com/shipment/tracking?awbNo={clean_awb}"
                    page = await playwright_manager.new_page(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                    )
                    await page.add_init_script("delete navigator.__proto__.webdriver;")
                    await page.set_viewport_size({"width": 1440, "height": 900})

                    async def intercept_and_capture(route):
                        req = route.request
                        url_lower = req.url.lower()
                        if req.resource_type in ["media"]:
                            await route.abort()
                            return
                        ignored = ["google-analytics", "doubleclick", "adsense", "facebook", "criteo", "pubmatic"]
                        if any(kw in url_lower for kw in ignored):
                            await route.abort()
                            return
                        await route.continue_()

                    # Intercept the browser's own Altcha challenge response
                    async def on_response(response):
                        if "altcha-api.xbees.in" in response.url and "challenge" in response.url:
                            try:
                                ch_data = await response.json()
                                captured_challenge.update(ch_data)
                                print(f"[Xpressbees] Captured browser Altcha challenge: salt={ch_data.get('salt','')[:20]}...")
                            except Exception as ce:
                                print(f"[Xpressbees] Challenge capture error: {ce}")

                    page.on("response", on_response)
                    await page.route("**/*", intercept_and_capture)
                    await page.goto(official_url, wait_until="domcontentloaded", timeout=20000)

                    # Wait for the challenge to be fetched by the page (up to 5s)
                    for _ in range(10):
                        await asyncio.sleep(0.5)
                        if captured_challenge.get("challenge"):
                            break

                    solved_token = None
                    if captured_challenge.get("challenge"):
                        ch = captured_challenge
                        num = solve_altcha(ch["challenge"], ch["salt"], ch.get("maxnumber", 100000))
                        if num is not None:
                            payload_obj = {
                                "algorithm": ch.get("algorithm", "SHA-256"),
                                "challenge": ch["challenge"],
                                "number": num,
                                "salt": ch["salt"],
                                "signature": ch["signature"]
                            }
                            solved_token = base64.b64encode(json.dumps(payload_obj).encode('utf-8')).decode('utf-8')
                            print(f"[Xpressbees] Browser challenge solved! token len={len(solved_token)}")
                    else:
                        print(f"[Xpressbees] Could not capture browser challenge, trying direct fetch")
                        # Fallback: fetch fresh challenge directly (might work if server is lenient)
                        try:
                            import requests as _req
                            r_ch = _req.get("https://altcha-api.xbees.in/v1/challenge", timeout=6)
                            if r_ch.status_code == 200:
                                ch_data = r_ch.json()
                                num = solve_altcha(ch_data["challenge"], ch_data["salt"], ch_data.get("maxnumber", 100000))
                                if num is not None:
                                    payload_obj = {
                                        "algorithm": ch_data.get("algorithm", "SHA-256"),
                                        "challenge": ch_data["challenge"],
                                        "number": num,
                                        "salt": ch_data["salt"],
                                        "signature": ch_data["signature"]
                                    }
                                    solved_token = base64.b64encode(json.dumps(payload_obj).encode('utf-8')).decode('utf-8')
                        except Exception:
                            pass

                    if solved_token:
                        # Remove popups/modals
                        await asyncio.sleep(0.5)
                        await page.evaluate("""() => {
                            document.querySelectorAll('div[class*="modal"], div[class*="popup"], div[role="dialog"]').forEach(e => e.remove());
                        }""")

                        # Inject the MATCHED Python-solved token into the form
                        injected = await page.evaluate("""(token) => {
                            const widget = document.querySelector('altcha-widget');
                            if (widget && widget.shadowRoot) {
                                const inp = widget.shadowRoot.querySelector('input[name="altcha"]');
                                if (inp) { inp.value = token; return 'shadow-injected'; }
                            }
                            const inp2 = document.querySelector('input[name="altcha"]');
                            if (inp2) { inp2.value = token; return 'dom-injected'; }
                            const f = document.querySelector('form');
                            if (f) {
                                let h = document.createElement('input');
                                h.type = 'hidden'; h.name = 'altcha'; h.value = token;
                                f.appendChild(h); return 'created-injected';
                            }
                            return 'not-found';
                        }""", solved_token)
                        print(f"[Xpressbees] Inject result: {injected}")

                        # Click Search/Submit button
                        btn = page.locator('button.sc-fTyFcS.gRKEpD, button:has(img[alt="Submit Button"]), button[type="submit"]').first
                        if await btn.count() > 0:
                            await btn.click()
                        else:
                            await page.evaluate("""() => {
                                const f = document.querySelector('form');
                                if (f && f.requestSubmit) f.requestSubmit();
                                else if (f) f.submit();
                            }""")

                        # Wait for official tracking content (up to 25s)
                        results_ready = False
                        for _ in range(30):
                            await asyncio.sleep(0.8)
                            content = await page.content()
                            if any(k in content for k in [
                                "Your Domestic Shipments", "Shipping Details", "Shipment History",
                                "Return Delivered", "Data Received", "DLVD", "Delivered",
                                "RPCancel", "OutForPickUp", "No Records", "No Data Found", "Invalid"
                            ]):
                                results_ready = True
                                break

                        if results_ready:
                            print(f"[Xpressbees] Official site loaded on headless Render! Taking screenshot...")
                            try:
                                await page.evaluate("""() => {
                                    const all = Array.from(document.querySelectorAll('*'));
                                    const viewEl = all.find(e => e.children.length === 0 && e.textContent.trim() === 'View');
                                    if (viewEl) viewEl.click();
                                }""")
                                await asyncio.sleep(0.8)
                            except Exception:
                                pass

                            await page.evaluate("""() => {
                                document.querySelectorAll('div[class*="modal"], div[class*="popup"], div[role="dialog"]').forEach(e => e.remove());
                                document.documentElement.style.zoom = '65%';
                                window.scrollTo(0, 155);
                            }""")
                            await asyncio.sleep(0.5)
                            await page.screenshot(path=screenshot_file, full_page=False)
                            try:
                                from services.desktop_frame_service import DesktopFrameService
                                DesktopFrameService.apply_frame(
                                    web_img_path=screenshot_file,
                                    courier_name="Xpressbees",
                                    awb=clean_awb,
                                    tracking_url=f"https://www.xpressbees.com/track?isawb=Yes&trackid={clean_awb}",
                                    output_path=screenshot_file
                                )
                            except Exception as fe:
                                print(f"[DesktopFrame] Xpressbees headless frame error: {fe}")
                            try:
                                from services.drive_service import DriveService
                                return await DriveService.upload_and_cleanup(
                                    image_path=screenshot_file,
                                    courier_name="Xpressbees",
                                    clean_awb=clean_awb,
                                    fallback_relative_path=f"/static/screenshots/{screenshot_filename}"
                                )
                            except Exception:
                                return f"/static/screenshots/{screenshot_filename}"
                        else:
                            print(f"[Xpressbees] Official site did not load after injection on headless")
                    else:
                        print(f"[Xpressbees] No token solved, skipping injection")

                    if page:
                        await page.close()
                        page = None
                except Exception as headless_err:
                    print(f"[Xpressbees] Headless path error: {headless_err}")
                    if page:
                        try:
                            await page.close()
                        except Exception:
                            pass
                        page = None

            # ==============================================================
            # WINDOWS PATH (Local): Use official XpressBees site + Altcha
            # ==============================================================
            url = f"https://trackcourier.io/track-and-trace/xpressbees-logistics/{clean_awb}"
            page = await playwright_manager.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
            await page.add_init_script("delete navigator.__proto__.webdriver;")

            async def intercept_tc(route):
                req = route.request
                res_type = req.resource_type
                url_lower = req.url.lower()
                if res_type in ["media", "font"]:
                    await route.abort()
                    return
                ignored = ["google", "analytics", "doubleclick", "adsense", "facebook", "criteo", "pubmatic"]
                if any(kw in url_lower for kw in ignored):
                    await route.abort()
                    return
                await route.continue_()

            await page.route("**/*", intercept_tc)

            try:
                # 1. Primary: Official XpressBees website with full View details
                official_url = f"https://www.xpressbees.com/shipment/tracking?awbNo={clean_awb}"
                await page.goto(official_url, wait_until="networkidle", timeout=15000)
                await asyncio.sleep(0.8)

                # Check if results already loaded
                content_initial = await page.content()
                already_loaded = any(k in content_initial for k in ["Shipping Details", "Shipment History", "Your Domestic Shipments"])

                if not already_loaded:
                    # Remove any blocking modal/popup
                    await page.evaluate("""() => {
                        const closeBtn = document.querySelector('div[class*="modal"] button, div[class*="popup"] button, .sc-bdnxRM');
                        if (closeBtn) closeBtn.click();
                        document.querySelectorAll('div[class*="modal"], div[class*="popup"], div[role="dialog"]').forEach(e => e.remove());
                    }""")

                    # Trigger Altcha PoW verification
                    await page.evaluate("""() => {
                        const cb = document.querySelector('altcha-widget input[type="checkbox"], input[type="checkbox"]');
                        if (cb) {
                            cb.checked = true;
                            cb.dispatchEvent(new Event('change', { bubbles: true }));
                            cb.dispatchEvent(new Event('input', { bubbles: true }));
                            cb.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                        }
                    }""")

                    # Wait up to 3s for Altcha token to generate
                    for _ in range(10):
                        await asyncio.sleep(0.3)
                        val = await page.evaluate("""() => document.querySelector('input[name="altcha"]')?.value || "" """)
                        if val and len(val) > 20:
                            break

                    # Click exact Search button next to AWB input
                    btn = page.locator('button.sc-fTyFcS.gRKEpD, button:has(img[alt="Submit Button"])').first
                    if await btn.count() > 0:
                        await btn.click()
                    else:
                        await page.evaluate("""() => {
                            const f = document.querySelector('form');
                            if (f && f.requestSubmit) f.requestSubmit();
                        }""")

                # Wait up to 10 seconds for tracking details to render
                results_ready = False
                for s in range(15):
                    await asyncio.sleep(0.6)
                    content = await page.content()
                    if any(k in content for k in [
                        "Your Domestic Shipments", "Shipping Details", "Shipment History",
                        "Return Delivered", "Data Received", "DLVD", "Delivered",
                        "RPCancel", "Rpcancel", "OutForPickUp", "No Records", "No Data Found", "Invalid"
                    ]):
                        results_ready = True
                        break

                if not results_ready:
                    raise Exception("Official Xpressbees page did not populate tracking data, falling back to TrackCourier")

                # Click 'View' to expand full Shipping Details and Shipment History
                try:
                    await asyncio.sleep(0.6)
                    await page.evaluate("""() => {
                        const all = Array.from(document.querySelectorAll('*'));
                        const viewEl = all.find(e => e.children.length === 0 && e.textContent.trim() === 'View');
                        if (viewEl) viewEl.click();
                    }""")
                    await asyncio.sleep(0.8)
                except Exception as view_err:
                    print(f"[Xpressbees] View click note: {view_err}")

                # Clean overlays and zoom to 65% for crystal-clear presentation
                try:
                    await page.evaluate("""() => {
                        document.querySelectorAll('div[class*="modal"], div[class*="popup"], div[role="dialog"]').forEach(e => e.remove());
                        const style = document.createElement('style');
                        style.innerHTML = `
                            * {
                                -webkit-font-smoothing: antialiased !important;
                                text-rendering: geometricPrecision !important;
                            }
                        `;
                        document.head.appendChild(style);
                        document.documentElement.style.zoom = '65%';
                        window.scrollTo(0, 155);
                    }""")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

                await page.bring_to_front()
                await page.screenshot(path=screenshot_file, full_page=False)
                try:
                    from services.desktop_frame_service import DesktopFrameService
                    DesktopFrameService.apply_frame(
                        web_img_path=screenshot_file,
                        courier_name="Xpressbees",
                        awb=clean_awb,
                        tracking_url=f"https://www.xpressbees.com/track?isawb=Yes&trackid={clean_awb}",
                        output_path=screenshot_file
                    )
                except Exception as fe:
                    print(f"[DesktopFrame] Xpressbees error: {fe}")

                try:
                    from services.drive_service import DriveService
                    return await DriveService.upload_and_cleanup(
                        image_path=screenshot_file,
                        courier_name="Xpressbees",
                        clean_awb=clean_awb,
                        fallback_relative_path=f"/static/screenshots/{screenshot_filename}"
                    )
                except Exception:
                    return f"/static/screenshots/{screenshot_filename}"
            except Exception as e_xb:
                print(f"[Xpressbees] Official screenshot error: {e_xb}, falling back to TrackCourier...")
                # 2. Fast reliable fallback
                await page.goto(f"https://trackcourier.io/track-and-trace/xpressbees-logistics/{clean_awb}", wait_until="domcontentloaded", timeout=8000)
                card = page.locator(".block.m-b-2, .card, body").first
                await card.screenshot(path=screenshot_file)
                try:
                    from services.desktop_frame_service import DesktopFrameService
                    DesktopFrameService.apply_frame(
                        web_img_path=screenshot_file,
                        courier_name="Xpressbees",
                        awb=clean_awb,
                        tracking_url=f"https://www.xpressbees.com/track?isawb=Yes&trackid={clean_awb}",
                        output_path=screenshot_file
                    )
                except Exception:
                    pass

                try:
                    from services.drive_service import DriveService
                    return await DriveService.upload_and_cleanup(
                        image_path=screenshot_file,
                        courier_name="Xpressbees",
                        clean_awb=clean_awb,
                        fallback_relative_path=f"/static/screenshots/{screenshot_filename}"
                    )
                except Exception:
                    return f"/static/screenshots/{screenshot_filename}"
        except Exception as e:
            print(f"[Xpressbees] Screenshot capture failed for {clean_awb}: {e}")
            return "-"
        finally:
            if page:
                try:
                    ctx = page.context
                    await page.close()
                    if ctx:
                        await ctx.close()
                except Exception:
                    pass

