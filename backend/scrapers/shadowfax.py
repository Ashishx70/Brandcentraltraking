from .base import BaseScraper
import asyncio
import os
import requests
import base64
import json
import time
from datetime import datetime

def fetch_shadowfax_api(awb: str) -> dict:
    clean_awb = str(awb).strip()
    url = f"https://saruman.shadowfax.in/web_app/delivery/track/{clean_awb}/"
    headers = {
        'authorization': 'Token cePcVR7z7FIETB4PxguHC2YJGk6NncHnByrJttgRIUqNxfWezuzAUvtALyqcHJEC',
        'referer': 'https://tracker.shadowfax.in/',
        'origin': 'https://tracker.shadowfax.in',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'accept': 'application/json, text/plain, */*'
    }
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                order_details = d.get("order_details", {})
                final_status = order_details.get("final_status") or "Unknown"
                status_id = (order_details.get("status_id") or "").lower()
                
                events = d.get("data", [])
                last_loc = ""
                timestamp = "-"
                
                if events:
                    first_ev = events[0]
                    main_st = first_ev.get("main_status")
                    if not final_status or final_status == "Unknown":
                        final_status = main_st or "Unknown"
                        
                    sub_list = first_ev.get("sub_status", [])
                    if sub_list and isinstance(sub_list, list):
                        last_loc = sub_list[0]
                    elif isinstance(sub_list, str):
                        last_loc = sub_list
                        
                    time_list = first_ev.get("time", [])
                    raw_time = ""
                    if time_list and isinstance(time_list, list):
                        raw_time = time_list[0]
                    elif isinstance(time_list, str):
                        raw_time = time_list
                        
                    if raw_time:
                        try:
                            dt = datetime.fromisoformat(raw_time.split(".")[0])
                            timestamp = dt.strftime("%d-%b-%Y %I:%M %p")
                        except Exception:
                            timestamp = raw_time

                st_lower = final_status.lower()
                if "delivered" in st_lower and "not" not in st_lower and "fail" not in st_lower:
                    mapped_status = "Delivered"
                elif "rto" in status_id or "returned" in st_lower or "return" in st_lower:
                    mapped_status = "Returned"
                elif "fail" in st_lower:
                    mapped_status = "Delivery Failed"
                elif "cancel" in st_lower:
                    mapped_status = "Pickup Cancelled"
                elif "unsuccessful" in st_lower:
                    mapped_status = "Pickup Unsuccessful"
                elif "received" in st_lower:
                    mapped_status = "Shipment Received"
                else:
                    mapped_status = final_status

                formatted_events = []
                for ev in events:
                    m_st = ev.get("main_status") or ""
                    sub_l = ev.get("sub_status", [])
                    loc_val = sub_l[0] if (sub_l and isinstance(sub_l, list)) else (sub_l if isinstance(sub_l, str) else "")
                    t_l = ev.get("time", [])
                    raw_t = t_l[0] if (t_l and isinstance(t_l, list)) else (t_l if isinstance(t_l, str) else "")
                    ev_time = "-"
                    if raw_t:
                        try:
                            dt = datetime.fromisoformat(raw_t.split(".")[0])
                            ev_time = dt.strftime("%d-%b-%Y %I:%M %p")
                        except Exception:
                            ev_time = raw_t
                    formatted_events.append({
                        "status": m_st,
                        "location": loc_val,
                        "time": ev_time
                    })

                clean_last_loc = (last_loc or "In Transit").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').strip()
                clean_status = mapped_status.replace("’", "'").replace("‘", "'").strip()

                return {
                    "success": True,
                    "status": clean_status,
                    "last_location": clean_last_loc,
                    "timestamp": timestamp,
                    "screenshot": "-",
                    "events": formatted_events
                }
            elif r.status_code == 404:
                return {"success": False, "events": []}
            elif r.status_code == 429 and attempt < 2:
                time.sleep(1.0)
                continue
        except Exception:
            if attempt < 2:
                time.sleep(0.5)
                continue
            
    return {"success": False, "events": []}

class ShadowfaxScraper(BaseScraper):
    async def _capture_screenshot(self, clean_awb: str) -> str:
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
            screenshot_filename = f"{clean_awb}_Shadowfax.png"
            screenshot_file = os.path.join(backend_dir, "static", "screenshots", screenshot_filename)
            os.makedirs(os.path.dirname(screenshot_file), exist_ok=True)

            page = await playwright_manager.new_page(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
            await page.add_init_script("delete navigator.__proto__.webdriver;")

            async def filter_route(route):
                req = route.request
                rtype = req.resource_type
                url_str = req.url.lower()
                if rtype == "media":
                    await route.abort()
                    return
                ignored_kw = ["google-analytics", "doubleclick", "ads", "facebook", "clarity", "criteo"]
                if any(x in url_str for x in ignored_kw):
                    await route.abort()
                    return
                await route.continue_()

            await page.route("**/*", filter_route)
            try:
                # 1. Primary: Official Shadowfax tracking portal
                await page.goto("https://tracker.shadowfax.in/", wait_until="domcontentloaded", timeout=30000)
                inp = await page.wait_for_selector("input", timeout=12000)
                await inp.fill(clean_awb)
                btn = await page.wait_for_selector("button:has-text('Track Your Order')", timeout=10000)
                await btn.click()

                # Wait for actual tracking status to appear (clean_awb must be inside card text, not just skeleton)
                for _ in range(35):
                    await asyncio.sleep(1.0)
                    content = await page.content()
                    has_awb = clean_awb in content
                    has_real_status = any(k.lower() in content.lower() for k in [
                        'pick up canceled', 'pickup cancelled', 'delivered', 'in transit',
                        'out for delivery', 'the shipment is', 'dispatched', 'picked',
                        'cancelled', 'return to origin', 'return', 'delivery failed'
                    ])
                    if has_awb and has_real_status:
                        break

                await asyncio.sleep(1.5)
                await page.screenshot(path=screenshot_file, full_page=False)
                return f"/static/screenshots/{screenshot_filename}"
            except Exception as e_sf:
                print(f"[Shadowfax] Official tracker screenshot error: {e_sf}, falling back to TrackCourier...")
                # 2. Fast reliable fallback
                await page.goto(f"https://trackcourier.io/track-and-trace/shadowfax/{clean_awb}", wait_until="domcontentloaded", timeout=12000)
                card = page.locator(".block.m-b-2, .card, body").first
                await card.screenshot(path=screenshot_file)
                return f"/static/screenshots/{screenshot_filename}"
        except Exception as e:
            print(f"[Shadowfax] Screenshot capture failed for {clean_awb}: {e}")
            return "-"
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def track(self, awb: str, capture_screenshot: bool = False) -> dict:
        clean_awb = str(awb).strip()
        
        # 1. Fast direct official Shadowfax API call (takes ~0.2s)
        try:
            api_res = await asyncio.to_thread(fetch_shadowfax_api, clean_awb)
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
        except Exception:
            pass

        # If screenshot is not requested, return immediately in ultra-fast mode (<0.2s)
        if not capture_screenshot:
            return {
                "status": "Awaiting scan",
                "last_location": "No scan records yet",
                "timestamp": "-",
                "screenshot": "-",
                "events": []
            }

        # 2. Secondary fallback: Capture screenshot proof
        screenshot_path = "-"
        if capture_screenshot:
            screenshot_path = await self._capture_screenshot(clean_awb)

        return {
            "status": "Awaiting scan",
            "last_location": "No scan records yet",
            "timestamp": "-",
            "screenshot": screenshot_path,
            "events": []
        }


