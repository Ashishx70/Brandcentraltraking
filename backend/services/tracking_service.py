from scrapers.factory import ScraperFactory
import asyncio
import json

class TrackingService:
    @staticmethod
    async def track_shipments(shipments, task_id, progress_callback, capture_screenshot: bool = False):
        total = len(shipments)
        if total == 0:
            await progress_callback(
                progress=100,
                current_action="Tracking run completed",
                log_message="No shipments to process.",
                log_level="success"
            )
            return

        import time
        start_time = time.time()
        workers = 1 if capture_screenshot else 3
        print(f"\n==================================================")
        print(f"[*] [BATCH TRACKING STARTED] Total AWBs: {total}")
        print(f"    Workers: {workers} Parallel | Image Mode: {capture_screenshot} | Time: {time.strftime('%H:%M:%S')}")
        print(f"==================================================")

        completed_count = 0
        lock = asyncio.Lock()
        # Safe concurrency: 1 worker in screenshot mode (100% CPU/RAM allocated, 0 crashes on Render), 3 in data mode
        sem = asyncio.Semaphore(workers)

        async def track_single(shipment):
            nonlocal completed_count
            awb = shipment["tracking_number"]
            courier = shipment["courier"]

            async with sem:
                scraper = ScraperFactory.get_scraper(courier, awb=awb)
                if scraper:
                    req_payload = {
                        "tracking_number": awb,
                        "courier": courier,
                        "capture_screenshot": capture_screenshot
                    }
                    print(f"\n========================================================")
                    print(f"[AWB TRACKING REQUEST] >>> Courier: {courier} | AWB: {awb}")
                    print(f"[AWB TRACKING REQUEST] JSON: {json.dumps(req_payload)}")
                    print(f"--------------------------------------------------------")
                    try:
                        # Log API call
                        try:
                            import sqlite3
                            db_conn = sqlite3.connect("tracking.db")
                            db_conn.execute("INSERT INTO api_usage DEFAULT VALUES;")
                            db_conn.commit()
                            db_conn.close()
                        except Exception as db_err:
                            pass

                        result = await scraper.track(awb, capture_screenshot=capture_screenshot)

                        print(f"[AWB TRACKING RESPONSE] <<< Courier: {courier} | AWB: {awb}")
                        print(f"[AWB TRACKING RESPONSE] JSON Result:")
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                        print(f"========================================================\n")
                        
                        from datetime import datetime
                        last_sync_str = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
                        
                        shipment["status"] = result["status"]
                        shipment["last_location"] = result["last_location"]
                        shipment["timestamp"] = result["timestamp"]
                        shipment["last_sync"] = last_sync_str
                        shipment["screenshot"] = result.get("screenshot", "-")
                        shipment["events"] = result.get("events", [])
                        
                        log_level = "success" if "delivered" in result["status"].lower() else "info"
                        if "error" in result["status"].lower() or "invalid" in result["status"].lower():
                            log_level = "error"
                            
                        async with lock:
                            completed_count += 1
                            pct = int((completed_count / total) * 100)
                            await progress_callback(
                                progress=pct,
                                current_action=f"Tracked {awb} ({completed_count}/{total})",
                                log_message=f"[{completed_count}/{total}] {courier} {awb}: {result['status']}",
                                log_level=log_level,
                                shipment=shipment
                            )
                    except Exception as e:
                        import traceback
                        tb = traceback.format_exc()
                        print(f"--- SCRAPER EXCEPTION TRACEBACK ---\n{tb}------------------------------------")
                        error_msg = str(e) or type(e).__name__
                        from datetime import datetime
                        last_sync_str = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
                        
                        shipment["status"] = "Scrape Failed"
                        shipment["last_location"] = error_msg
                        shipment["last_sync"] = last_sync_str
                        
                        async with lock:
                            completed_count += 1
                            pct = int((completed_count / total) * 100)
                            await progress_callback(
                                progress=pct,
                                current_action=f"Error {awb} ({completed_count}/{total})",
                                log_message=f"[{completed_count}/{total}] Error {courier} {awb}: {error_msg}",
                                log_level="error",
                                shipment=shipment
                            )
                else:
                    shipment["status"] = "Scraper Not Implemented"
                    shipment["last_location"] = "Service pending integration"
                    async with lock:
                        completed_count += 1
                        pct = int((completed_count / total) * 100)
                        await progress_callback(
                            progress=pct,
                            current_action=f"Skipped {awb} ({completed_count}/{total})",
                            log_message=f"[{completed_count}/{total}] Scraper for '{courier}' not implemented. Skipped {awb}.",
                            log_level="warning",
                            shipment=shipment
                        )
                
                # Safe pacing between worker tasks
                if "shadowfax" in courier.lower():
                    await asyncio.sleep(0.4)
                else:
                    await asyncio.sleep(0.2)

        # Launch all tasks controlled by the semaphore
        tasks = [asyncio.create_task(track_single(s)) for s in shipments]
        await asyncio.gather(*tasks)

        elapsed_time = time.time() - start_time
        mins = int(elapsed_time // 60)
        secs = int(elapsed_time % 60)
        time_formatted = f"{mins}m {secs}s" if mins > 0 else f"{elapsed_time:.1f}s"
        avg_speed = elapsed_time / total if total > 0 else 0
        
        summary_msg = f"[DONE] Batch Finished! Tracked {total} AWBs in {time_formatted} (Avg: {avg_speed:.2f}s/AWB) with 3 Workers"
        print(f"\n==================================================")
        print(f"[DONE] [BATCH TRACKING COMPLETED]")
        print(f"   Total AWBs  : {total}")
        print(f"   Total Time  : {time_formatted} ({elapsed_time:.2f} seconds)")
        print(f"   Avg per AWB : {avg_speed:.2f}s")
        print(f"==================================================\n")

        # Final completion update
        await progress_callback(
            progress=100,
            current_action=f"Completed in {time_formatted}",
            log_message=summary_msg,
            log_level="success"
        )

