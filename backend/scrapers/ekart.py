from .base import BaseScraper
import asyncio
import os
import re
import json
import requests
from datetime import datetime

def fetch_ekart(awb: str) -> dict:
    session = requests.Session()
    page_url = f"https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/{awb}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }
    
    r_page = session.get(page_url, headers=headers, timeout=10)
    csrf_match = re.search(r'name="csrf-token"\s+content="([^"]+)"', r_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ""
    
    api_url = "https://www.ekartlogistics.com/ekartlogistics-web-routes-api/ekartlogistics-web-proxy/trackings/v2"
    api_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": page_url,
        "content-type": "application/json",
        "csrf-token": csrf_token,
        "x-user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 EKCL/website/1"
    }
    payload = {"tracking_ids": awb}
    
    r_api = session.post(api_url, json=payload, headers=api_headers, timeout=10)
    if r_api.status_code != 200:
        return {
            "status": "",
            "last_location": "",
            "timestamp": "-",
            "events": []
        }
    
    data = r_api.json()
    shipment_info = data.get(awb)
    
    if not shipment_info or not isinstance(shipment_info, dict):
        return {
            "status": "Awaiting scan",
            "last_location": "No scan records yet",
            "timestamp": "-",
            "events": []
        }
    
    tracking_details = shipment_info.get("shipmentTrackingDetails", [])
    if not tracking_details:
        return {
            "status": "Awaiting scan",
            "last_location": "No scan records yet",
            "timestamp": "-",
            "events": []
        }
    
    # Sort details by date timestamp ascending
    sorted_details = sorted(tracking_details, key=lambda x: x.get("date", 0))
    latest_event = sorted_details[-1]
    
    status_detail = (latest_event.get("statusDetails") or "").strip()
    city = (latest_event.get("city") or "").strip()
    event_timestamp_ms = latest_event.get("date")
    
    timestamp = "-"
    if event_timestamp_ms:
        try:
            dt = datetime.fromtimestamp(event_timestamp_ms / 1000)
            timestamp = dt.strftime("%d-%b-%Y %I:%M %p")
        except Exception:
            pass
            
    if city and status_detail:
        last_location = f"{city} ({status_detail})"
    elif city:
        last_location = city
    else:
        last_location = status_detail or "Awaiting scan"
    
    # Status normalization
    status = status_detail or "In Transit"
    status_lower = status.lower()
    if "delivered" in status_lower and "unsuccessful" not in status_lower and "undelivered" not in status_lower:
        status = "Delivered"
    elif "out for delivery" in status_lower:
        status = "Out for Delivery"
    elif "rto" in status_lower or "reject" in status_lower or "returned" in status_lower:
        status = status_detail
    elif "dispatched" in status_lower or "received at" in status_lower or "in transit" in status_lower:
        status = status_detail
    
    # Extract all event milestones
    events = []
    for d in reversed(sorted_details):
        ev_ts = d.get("date")
        ev_time = "-"
        if ev_ts:
            try:
                dt = datetime.fromtimestamp(ev_ts / 1000)
                ev_time = dt.strftime("%d-%b-%Y %I:%M %p")
            except Exception:
                pass
        events.append({
            "status": (d.get("statusDetails") or "").strip(),
            "location": (d.get("city") or "").strip(),
            "time": ev_time
        })

    return {
        "status": status,
        "last_location": last_location,
        "timestamp": timestamp,
        "screenshot": "-",
        "events": events
    }

class EkartScraper(BaseScraper):
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
            screenshot_filename = f"{clean_awb}_Ekart.png"
            screenshot_file = os.path.join(backend_dir, "static", "screenshots", screenshot_filename)
            os.makedirs(os.path.dirname(screenshot_file), exist_ok=True)

            page = await playwright_manager.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
            await page.add_init_script("delete navigator.__proto__.webdriver;")

            async def filter_route(route):
                req = route.request
                rtype = req.resource_type
                url = req.url.lower()
                if rtype in ["media", "font"]:
                    await route.abort()
                    return
                if any(x in url for x in ["google", "analytics", "doubleclick", "ads", "facebook", "clarity", "criteo"]):
                    await route.abort()
                    return
                await route.continue_()

            await page.route("**/*", filter_route)

            try:
                # 1. Primary: Official Ekart tracking portal
                await page.goto(f"https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/{clean_awb}", wait_until="domcontentloaded", timeout=35000)
                # Wait for tracking details or status to be rendered
                for _ in range(25):
                    await asyncio.sleep(1.0)
                    content = await page.content()
                    if clean_awb in content and any(k in content for k in ["Tracking Details", "Status", "Delivered", "Picked", "Awaiting", "Shipment"]):
                        break
                # Zoom out Ekart page so full Tracking Details table fits on a single screen
                try:
                    await page.evaluate("""() => {
                        document.documentElement.style.zoom = '65%';
                        window.scrollTo(0, 0);
                    }""")
                except Exception:
                    pass
                await asyncio.sleep(0.8)
                await page.bring_to_front()
                await page.screenshot(path=screenshot_file, full_page=False)
                try:
                    from services.desktop_frame_service import DesktopFrameService
                    DesktopFrameService.apply_frame(
                        web_img_path=screenshot_file,
                        courier_name="Ekart",
                        awb=clean_awb,
                        tracking_url=f"https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/{clean_awb}",
                        output_path=screenshot_file
                    )
                except Exception as fe:
                    print(f"[DesktopFrame] Ekart error: {fe}")
                return f"/static/screenshots/{screenshot_filename}"
            except Exception as e_ek:
                print(f"[Ekart] Official screenshot error: {e_ek}, falling back to TrackCourier...")
                # 2. Fast reliable fallback
                await page.goto(f"https://trackcourier.io/track-and-trace/ekart-logistics/{clean_awb}", wait_until="domcontentloaded", timeout=12000)
                card = page.locator(".block.m-b-2, .card, body").first
                await card.screenshot(path=screenshot_file)
                try:
                    from services.desktop_frame_service import DesktopFrameService
                    DesktopFrameService.apply_frame(
                        web_img_path=screenshot_file,
                        courier_name="Ekart",
                        awb=clean_awb,
                        tracking_url=f"https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/{clean_awb}",
                        output_path=screenshot_file
                    )
                except Exception:
                    pass
                return f"/static/screenshots/{screenshot_filename}"
        except Exception as e:
            print(f"[Ekart] Screenshot capture failed for {clean_awb}: {e}")
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

    async def track(self, awb: str, capture_screenshot: bool = False) -> dict:
        clean_awb = str(awb).strip()
        try:
            res = await asyncio.to_thread(fetch_ekart, clean_awb)
            
            # If screenshot not requested, return immediately in super-fast mode (0.3s)
            if not capture_screenshot:
                res["screenshot"] = "-"
                return res
            
            # Optional screenshot capture via Playwright
            res["screenshot"] = await self._capture_screenshot(clean_awb)
            return res
        except Exception as e:
            return {
                "status": "Scrape Error",
                "last_location": f"Error: {str(e)}",
                "timestamp": "-",
                "screenshot": "-",
                "events": []
            }


