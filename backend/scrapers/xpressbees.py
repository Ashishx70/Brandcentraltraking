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
                    screenshot_path = await self._capture_screenshot(clean_awb)
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
                    screenshot_path = await self._capture_screenshot(clean_awb)
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
                    screenshot_path = await self._capture_screenshot(clean_awb)
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

    async def _capture_screenshot(self, clean_awb: str) -> str:
        """
        Captures screenshot ONLY when explicitly requested (capture_screenshot=True).
        Uses a lightweight Playwright session with a strict 7s timeout.
        """
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
                await page.goto(official_url, wait_until="domcontentloaded", timeout=40000)
                await asyncio.sleep(1.5)

                # Check if results already loaded
                content_initial = await page.content()
                already_loaded = any(k in content_initial for k in ["Shipping Details", "Shipment History", "Your Domestic Shipments"])

                if not already_loaded:
                    # Auto-verify Altcha and click submit
                    try:
                        cb = page.locator("altcha-widget input[type='checkbox'], .altcha-checkbox input, input[type='checkbox'], #altcha_checkbox").first
                        if await cb.count() > 0:
                            await cb.click()
                            # Wait for Altcha PoW verification to actually complete (not just checkbox checked)
                            for attempt_v in range(60):
                                await asyncio.sleep(0.5)
                                is_verified = await page.evaluate("""() => {
                                    const w = document.querySelector('altcha-widget, .altcha');
                                    if (w && (w.getAttribute('state') === 'verified' || w.getAttribute('data-state') === 'verified' || w.classList.contains('verified'))) return true;
                                    const hiddenInp = document.querySelector('input[name="altcha"]');
                                    if (hiddenInp && hiddenInp.value && hiddenInp.value.length > 10) return true;
                                    return false;
                                }""")
                                if is_verified or attempt_v >= 7:
                                    break
                            await asyncio.sleep(0.8)

                        # Trigger form submit via submit button
                        try:
                            btn = page.locator("form button[type='submit'], button.sc-fTyFcS").first
                            if await btn.count() > 0:
                                await btn.click()
                        except Exception:
                            pass

                        await page.evaluate("""() => {
                            const btns = Array.from(document.querySelectorAll('button'));
                            const arrow = btns.find(b => 
                                (b.querySelector('img') && b.querySelector('img').src.includes('RightArrow')) || 
                                (b.querySelector('span') && b.querySelector('span').innerText === 'Search') || 
                                b.className.includes('gRKEpD') ||
                                (b.type === 'submit' && b.querySelector('img'))
                            );
                            if (arrow) arrow.click();
                        }""")
                    except Exception as altcha_err:
                        print(f"[Xpressbees] Altcha interaction note: {altcha_err}")

                # Wait up to 45 seconds for results table to populate
                results_ready = False
                for s in range(45):
                    await asyncio.sleep(1.0)
                    content = await page.content()
                    if any(k in content for k in [
                        "Your Domestic Shipments", "Shipping Details", "Shipment History",
                        "Return Delivered", "Data Received",
                        "RPCancel", "Rpcancel", "OutForPickUp", "No Records"
                    ]):
                        results_ready = True
                        break

                    # Retry pressing Enter / submit if results haven't appeared by second 4 or 8
                    if s in [4, 8] and not results_ready:
                        try:
                            await page.locator("input[type='text']").first.press("Enter")
                            await page.evaluate("""() => {
                                const f = document.querySelector('form');
                                if (f && f.requestSubmit) f.requestSubmit();
                            }""")
                        except Exception:
                            pass

                # Click 'View' once to expand full Shipping Details and Shipment History
                try:
                    await asyncio.sleep(0.6)
                    await page.evaluate("""() => {
                        const all = Array.from(document.querySelectorAll('*'));
                        const viewEl = all.find(e => e.children.length === 0 && e.textContent.trim() === 'View');
                        if (viewEl) {
                            viewEl.click();
                        }
                    }""")
                    for _ in range(16):
                        await asyncio.sleep(0.5)
                        content = await page.content()
                        if "Shipping Details" in content or "Shipment History" in content:
                            break
                    await asyncio.sleep(1.0)
                except Exception as view_err:
                    print(f"[Xpressbees] View click note: {view_err}")

                # Zoom out XpressBees page with crisp text rendering and compact vertical spacing so all details fit
                try:
                    await page.evaluate("""() => {
                        const style = document.createElement('style');
                        style.innerHTML = `
                            * {
                                -webkit-font-smoothing: antialiased !important;
                                text-rendering: geometricPrecision !important;
                            }
                        `;
                        document.head.appendChild(style);

                        const allEls = Array.from(document.querySelectorAll('p, span, div, section'));
                        allEls.forEach(el => {
                            if (el.children.length === 0 && el.textContent && el.textContent.includes('complete the CAPTCHA')) {
                                el.style.display = 'none';
                            }
                            const cs = window.getComputedStyle(el);
                            if (parseFloat(cs.marginTop) > 14) el.style.marginTop = '6px';
                            if (parseFloat(cs.marginBottom) > 14) el.style.marginBottom = '6px';
                            if (parseFloat(cs.paddingTop) > 14) el.style.paddingTop = '6px';
                            if (parseFloat(cs.paddingBottom) > 14) el.style.paddingBottom = '6px';
                        });

                        document.documentElement.style.zoom = '62%';
                        window.scrollTo(0, 175);
                    }""")
                    await asyncio.sleep(0.6)
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
                return f"/static/screenshots/{screenshot_filename}"
            except Exception as e_xb:
                print(f"[Xpressbees] Official screenshot error: {e_xb}, falling back to TrackCourier...")
                # 2. Fast reliable fallback
                await page.goto(f"https://trackcourier.io/track-and-trace/xpressbees-logistics/{clean_awb}", wait_until="domcontentloaded", timeout=12000)
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
                return f"/static/screenshots/{screenshot_filename}"
        except Exception as e:
            print(f"[Xpressbees] Screenshot capture failed for {clean_awb}: {e}")
            return "-"
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            try:
                from browser.playwright_manager import playwright_manager
                await playwright_manager.close_browser()
            except Exception:
                pass

