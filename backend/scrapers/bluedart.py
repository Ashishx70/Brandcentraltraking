from .base import BaseScraper
import asyncio
import os
import re
import urllib.request
from datetime import datetime

def fetch_bluedart(awb: str) -> dict:
    url = f"https://www.bluedart.com/trackdartresult?trackFor=0&trackNo={awb}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    import ssl
    context = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=context, timeout=12) as response:
        html = response.read().decode('utf-8', errors='ignore')
        
    if "No record found" in html or "Invalid Waybill" in html or "No records found" in html or "No information is available" in html:
        return {
            "status": "Invalid AWB / Not Found",
            "last_location": "No tracking data available",
            "timestamp": "-",
            "screenshot": "-",
            "events": []
        }
        
    events = []
    status = ""
    last_location = ""
    timestamp = "-"
    summary_status = ""
    new_waybill = ""

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None

    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        for table in tables:
            rows = table.find_all("tr")
            for r in rows:
                cols = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
                if len(cols) == 2:
                    k, v = cols[0].lower(), cols[1]
                    if "status" in k and not summary_status:
                        summary_status = v
                    if "new waybill" in k and not new_waybill:
                        new_waybill = v

        for table in tables:
            text = table.get_text()
            if "Status and Scans" in text or ("Location" in text and "Details" in text and "Date" in text):
                for r in table.find_all("tr"):
                    tds = r.find_all("td")
                    if len(tds) >= 4:
                        loc = tds[0].get_text(strip=True)
                        det = tds[1].get_text(strip=True)
                        d_str = tds[2].get_text(strip=True)
                        t_str = tds[3].get_text(strip=True)
                        if det and d_str and det.lower() != "details":
                            full_time = f"{d_str} {t_str}".strip()
                            try:
                                dt = datetime.strptime(full_time, "%d %b %Y %H:%M")
                                formatted_time = dt.strftime("%d-%b-%Y %I:%M %p")
                            except Exception:
                                formatted_time = full_time
                            events.append({
                                "time": formatted_time,
                                "status": det,
                                "location": loc
                            })
    else:
        # Fallback regex parsing
        idx = html.find("Status and Scans")
        search_html = html[idx:] if idx != -1 else html
        row_matches = re.finditer(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>', search_html, re.DOTALL | re.IGNORECASE)
        for m in row_matches:
            cols = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', c)).strip() for c in m.groups()]
            loc, det, d_str, t_str = cols[0], cols[1], cols[2], cols[3]
            if det and d_str and det.lower() != "details":
                full_time = f"{d_str} {t_str}".strip()
                try:
                    dt = datetime.strptime(full_time, "%d %b %Y %H:%M")
                    formatted_time = dt.strftime("%d-%b-%Y %I:%M %p")
                except Exception:
                    formatted_time = full_time
                events.append({
                    "time": formatted_time,
                    "status": det,
                    "location": loc
                })

    if events:
        latest = events[0]
        status_text = latest["status"]
        loc_text = latest["location"]
        timestamp = latest["time"]
        st_lower = status_text.lower()

        if "delivered" in st_lower and "undelivered" not in st_lower:
            status = "Delivered"
        elif "out for delivery" in st_lower:
            status = "Out for Delivery"
        elif "in transit" in st_lower or "arrived" in st_lower or "connected" in st_lower:
            status = "In Transit"
        elif "picked" in st_lower:
            status = "Picked Up"
        elif "rto" in st_lower or "return" in st_lower:
            status = "Returned"
        else:
            status = status_text

        last_location = f"{loc_text} ({status_text})" if loc_text else status_text

    # Check summary status
    if summary_status:
        sm_lower = summary_status.lower()
        if "return" in sm_lower or "rto" in sm_lower:
            if status != "Delivered":
                status = "Returned"
        elif not status:
            if "delivered" in sm_lower and "undelivered" not in sm_lower:
                status = "Delivered"
            else:
                status = summary_status

    # Deduplicate events while preserving order
    unique_events = []
    seen = set()
    for ev in events:
        key = (ev["time"], ev["status"], ev["location"])
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    return {
        "status": status or "Pending",
        "last_location": last_location or "Awaiting scan",
        "timestamp": timestamp,
        "screenshot": "-",
        "events": unique_events
    }

class BlueDartScraper(BaseScraper):
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
            screenshot_filename = f"{clean_awb}_BlueDart.png"
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
                if rtype == "image":
                    if "bluedart" in url or "dhl" in url or "track" in url:
                        await route.continue_()
                        return
                    else:
                        await route.abort()
                        return
                if any(x in url for x in ["google", "analytics", "doubleclick", "ads", "facebook", "chatbot", "clarity"]):
                    await route.abort()
                    return
                await route.continue_()

            await page.route("**/*", filter_route)

            try:
                await page.goto(f"https://www.bluedart.com/trackdartresult?trackFor=0&trackNo={clean_awb}", wait_until="domcontentloaded", timeout=35000)
                for _ in range(25):
                    await asyncio.sleep(1.0)
                    content = await page.content()
                    if any(k in content for k in ["Shipment Delivered", "Waybill No", "Status and Scan", "Shipment Details"]):
                        break

                # Remove cookie consent banners, chat widgets, and overlays, and zoom out to fit full page
                try:
                    await page.evaluate("""() => {
                        const cookies = document.querySelectorAll('#cookie-law-info-bar, [id*="cookie"], [class*="cookie"], [class*="consent"]');
                        cookies.forEach(c => c.remove());
                        const chats = document.querySelectorAll('[id*="chat"], [class*="chat"], .livechat, [aria-label*="chat"]');
                        chats.forEach(c => c.remove());
                        document.documentElement.style.zoom = '80%';
                        window.scrollTo(0, 0);
                    }""")
                except Exception:
                    pass

                await asyncio.sleep(1.0)
                await page.bring_to_front()
                await page.screenshot(path=screenshot_file, full_page=False)
                try:
                    from services.desktop_frame_service import DesktopFrameService
                    DesktopFrameService.apply_frame(
                        web_img_path=screenshot_file,
                        courier_name="BlueDart",
                        awb=clean_awb,
                        tracking_url=f"https://www.bluedart.com/trackdartresult?trackFor=0&trackNo={clean_awb}",
                        output_path=screenshot_file
                    )
                except Exception as fe:
                    print(f"[DesktopFrame] BlueDart error: {fe}")
                return f"/static/screenshots/{screenshot_filename}"
            except Exception as e_bd:
                print(f"[BlueDart] Official screenshot error: {e_bd}, falling back to TrackCourier...")
                # Fast reliable fallback to TrackCourier for BlueDart
                await page.goto(f"https://trackcourier.io/track-and-trace/blue-dart/{clean_awb}", wait_until="domcontentloaded", timeout=12000)
                card = page.locator(".block.m-b-2, .card, body").first
                await card.screenshot(path=screenshot_file)
                try:
                    from services.desktop_frame_service import DesktopFrameService
                    DesktopFrameService.apply_frame(
                        web_img_path=screenshot_file,
                        courier_name="BlueDart",
                        awb=clean_awb,
                        tracking_url=f"https://www.bluedart.com/trackdartresult?trackFor=0&trackNo={clean_awb}",
                        output_path=screenshot_file
                    )
                except Exception:
                    pass
                return f"/static/screenshots/{screenshot_filename}"
        except Exception as ss_err:
            print(f"Failed to capture BlueDart screenshot for {clean_awb}: {ss_err}")
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
            # Fast direct fetch via official Blue Dart tracking page
            res = await asyncio.to_thread(fetch_bluedart, clean_awb)
            
            # If screenshot not requested, return immediately in super-fast mode
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


