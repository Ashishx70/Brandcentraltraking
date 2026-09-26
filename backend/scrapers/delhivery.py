import asyncio
import os
import urllib.request
import json
import ssl
from datetime import datetime
from .base import BaseScraper

def fetch_delhivery(awb: str) -> dict:
    url = f"https://dlv-api.delhivery.com/v3/unified-tracking-new?wbn={awb}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.delhivery.com",
        "Referer": f"https://www.delhivery.com/track/package/{awb}"
    }
    req = urllib.request.Request(url, headers=headers)
    context = ssl._create_unverified_context()
    # 10 second timeout for safety
    with urllib.request.urlopen(req, context=context, timeout=10) as response:
        return json.loads(response.read().decode())

class DelhiveryScraper(BaseScraper):
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
            screenshot_filename = f"{clean_awb}_Delhivery.png"
            screenshot_file = os.path.join(backend_dir, "static", "screenshots", screenshot_filename)
            os.makedirs(os.path.dirname(screenshot_file), exist_ok=True)

            page = await playwright_manager.new_page(
                viewport={"width": 1366, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
            await page.add_init_script("delete navigator.__proto__.webdriver;")

            async def intercept_route(route):
                req = route.request
                res_type = req.resource_type
                url_lower = req.url.lower()

                if res_type == "media":
                    await route.abort()
                    return

                if res_type == "image":
                    if "delhivery.com" in url_lower:
                        await route.continue_()
                        return
                    else:
                        await route.abort()
                        return

                ignored_domains = [
                    "google-analytics", "doubleclick", "adsense",
                    "facebook", "fundingchoices", "amazon-adsystem", "clarity"
                ]
                if any(kw in url_lower for kw in ignored_domains):
                    await route.abort()
                    return

                await route.continue_()

            await page.route("**/*", intercept_route)

            try:
                # Inject style to hide ONLY popup overlays/backdrops, explicitly preserving Delhivery header & logo
                await page.add_init_script("""
                    const injectStyle = () => {
                        const styleId = 'anti-modal-css';
                        if (!document.getElementById(styleId)) {
                            const st = document.createElement('style');
                            st.id = styleId;
                            st.textContent = `
                                /* Target modal overlay and backdrops ONLY */
                                div.fixed.inset-0.flex.items-center,
                                div.fixed.inset-0.bg-opacity-50,
                                div[class*="backdrop-blur"],
                                div[class*="bg-black/"],
                                div[class*="fixed"][class*="inset-0"]:not([class*="sticky"]) {
                                    visibility: hidden !important;
                                    opacity: 0 !important;
                                    pointer-events: none !important;
                                }
                                /* Ensure Delhivery official header and logo are always crisp and 100% visible */
                                div[class*="min-h-[68px]"],
                                div[class*="bg-black"],
                                div.sticky {
                                    visibility: visible !important;
                                    opacity: 1 !important;
                                }
                                /* Remove any blur from the background */
                                * {
                                    filter: none !important;
                                    -webkit-filter: none !important;
                                }
                            `;
                            document.head ? document.head.appendChild(st) : document.addEventListener('DOMContentLoaded', () => document.head.appendChild(st));
                        }
                    };
                    injectStyle();
                    setInterval(injectStyle, 200);
                """)

                # 1. Primary: Official Delhivery Tracking Portal
                await page.goto(f"https://www.delhivery.com/track-v2/package/{clean_awb}", wait_until="domcontentloaded", timeout=45000)

                # Poll rapidly (every 250ms) for tracking details to appear, capture instantly before popup
                card_ready = False
                for _ in range(80):  # up to 20 seconds
                    await asyncio.sleep(0.25)
                    content = await page.content()
                    has_status = any(k in content for k in [
                        "AWB #", "Returned", "Delivered", "In Transit", 
                        "Out for Delivery", "Pending", "Order Details", 
                        "Shipment Picked", "Manifested", "Your order has been"
                    ])
                    is_loading = "Loading..." in content

                    if has_status and not is_loading:
                        # Found tracking details! Wait a brief 300ms for layout to settle, then capture immediately
                        await asyncio.sleep(0.3)
                        card_ready = True
                        break

                if not card_ready:
                    # Try classic official Delhivery URL if v2 was slow
                    await page.goto(f"https://www.delhivery.com/track/package/{clean_awb}", wait_until="domcontentloaded", timeout=30000)
                    for _ in range(30):
                        await asyncio.sleep(0.5)
                        content = await page.content()
                        if any(k in content for k in ["AWB #", "Returned", "Delivered", "In Transit", "Out for Delivery", "Order Details"]):
                            await asyncio.sleep(0.3)
                            card_ready = True
                            break

                # Final safety cleanup for any OTP popup without removing React DOM nodes
                try:
                    await page.evaluate("""() => {
                        Array.from(document.querySelectorAll('div, dialog, section')).forEach(d => {
                            if (d.innerText && (d.innerText.includes('Enter your mobile number') || d.innerText.includes('Get OTP'))) {
                                let fixedParent = d.closest('div.fixed, div[class*="fixed"]');
                                if (fixedParent) {
                                    fixedParent.style.setProperty('visibility', 'hidden', 'important');
                                    fixedParent.style.setProperty('opacity', '0', 'important');
                                    fixedParent.style.setProperty('pointer-events', 'none', 'important');
                                }
                            }
                        });
                        document.querySelectorAll('*').forEach(el => {
                            if (window.getComputedStyle(el).filter !== 'none') {
                                el.style.filter = 'none';
                            }
                        });
                    }""")
                except Exception:
                    pass

                await page.screenshot(path=screenshot_file, full_page=False)
                return f"/static/screenshots/{screenshot_filename}"
            except Exception as e_primary:
                print(f"[Delhivery] Official screenshot error: {e_primary}, falling back to TrackCourier...")
                # 2. Fast reliable fallback to TrackCourier for Delhivery
                await page.goto(f"https://trackcourier.io/track-and-trace/delhivery/{clean_awb}", wait_until="domcontentloaded", timeout=12000)
                card = page.locator(".block.m-b-2, .card, body").first
                await card.screenshot(path=screenshot_file)
                return f"/static/screenshots/{screenshot_filename}"
        except Exception as e:
            print(f"Failed to capture Delhivery screenshot for {clean_awb}: {e}")
            return "-"
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass


    async def track(self, awb: str, capture_screenshot: bool = False) -> dict:
        clean_awb = str(awb).strip()
        try:
            # Execute the network call in a thread pool to avoid blocking the asyncio event loop
            res_json = await asyncio.to_thread(fetch_delhivery, clean_awb)
            if not res_json.get("data"):
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
            
            data = res_json["data"][0]
            
            # Map status
            hq_status = data.get("hqStatus", "Unknown")
            status_obj = data.get("status", {})
            instructions = status_obj.get("instructions")
            
            if data.get("currentFlow") == "Returned" or status_obj.get("status") == "DELIVERED_SELLER":
                status = "Returned"
            elif status_obj.get("status") == "DELIVERED" or hq_status == "DELIVERED":
                status = "Delivered"
            else:
                status = instructions if instructions else hq_status
            
            # Parse timestamp from statusDateTime
            timestamp = "-"
            status_date_time = status_obj.get("statusDateTime")
            if status_date_time:
                try:
                    dt = datetime.fromisoformat(status_date_time.split(".")[0])
                    timestamp = dt.strftime("%d-%b-%Y %I:%M %p")
                except Exception:
                    pass
            
            # Fallback for timestamp
            if timestamp == "-" and data.get("deliveryDate_v1"):
                v1_label = data["deliveryDate_v1"]
                if "on " in v1_label:
                    timestamp = v1_label.split("on ")[-1].strip()
            
            # Parse last location
            last_location = ""
            scans = []
            for state in (data.get("trackingStates") or []):
                for scan in (state.get("scans") or []):
                    scans.append(scan)
            
            if scans:
                latest_scan = scans[-1]
                scanned_loc = latest_scan.get("scannedLocation") or latest_scan.get("cityLocation")
                if scanned_loc:
                    last_location = scanned_loc
            
            events = []
            for scan in reversed(scans):
                scan_dt = scan.get("scanDateTime")
                scan_time = "-"
                if scan_dt:
                    try:
                        dt = datetime.fromisoformat(scan_dt.split(".")[0])
                        scan_time = dt.strftime("%d-%b-%Y %I:%M %p")
                    except Exception:
                        pass
                events.append({
                    "status": scan.get("scanType") or scan.get("instructions") or "-",
                    "location": scan.get("scannedLocation") or scan.get("cityLocation") or "",
                    "time": scan_time
                })

            screenshot_path = "-"
            if capture_screenshot:
                screenshot_path = await self._capture_screenshot(clean_awb)

            return {
                "status": status,
                "last_location": last_location,
                "timestamp": timestamp,
                "screenshot": screenshot_path,
                "events": events
            }
        except Exception as e:
            return {
                "status": "Scrape Error",
                "last_location": f"Error: {str(e)}",
                "timestamp": "-",
                "screenshot": "-",
                "events": []
            }

