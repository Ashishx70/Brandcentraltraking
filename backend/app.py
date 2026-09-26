import os
import sys
import uuid
import json
import csv
import io
import zipfile
from datetime import datetime
import time
import asyncio
import sqlite3
from typing import List, Optional
from pydantic import BaseModel
import pandas as pd

# Set event loop policy on Windows for Playwright subprocess support
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from services.tracking_service import TrackingService
from scrapers.factory import ScraperFactory

app = FastAPI(title="TrackShip API")

# Allow CORS for development ease
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path.lower()
    if path.endswith(".js") or path.endswith(".css") or path.endswith(".html") or path == "/" or "/screenshots/" in path:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SCREENSHOTS_DIR = os.path.join(STATIC_DIR, "screenshots")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
DB_PATH = os.path.join(BASE_DIR, "tracking.db")

# Ensure folders exist
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def get_courier_direct_url(courier: str, awb: str) -> str:
    c = (courier or "").lower()
    awb_upper = (awb or "").upper().strip()
    if "shadowfax" in c or awb_upper.startswith("SF") or awb_upper.startswith("R"):
        return f"https://trackcourier.io/track-and-trace/shadowfax/{awb}"
    elif "delhivery" in c:
        return f"https://www.delhivery.com/track/package/{awb}"
    elif "bluedart" in c or "blue dart" in c:
        return f"https://www.bluedart.com/tracking"
    elif "ekart" in c or "ekl" in c or "myntra" in c or awb_upper.startswith("FMP") or awb_upper.startswith("EKART") or awb_upper.startswith("MY"):
        return f"https://www.ekartlogistics.com/ekartlogistics-web/shipmenttrack/{awb}"
    elif "xpressbees" in c:
        return f"https://www.xpressbees.com/track?isawb=Yes&trackid={awb}"
    elif "dtdc" in c:
        return f"https://www.dtdc.in/tracking.asp"
    elif "ecom" in c:
        return f"https://ecomexpress.in/tracking/?awb_field={awb}"
    elif "india post" in c or "indiapost" in c:
        return f"https://www.indiapost.gov.in/_layouts/15/dop.portal.tracking/trackconsignment.aspx"
    else:
        return f"https://www.delhivery.com/track/package/{awb}"

@app.get('/static/screenshots/{filename}')
async def serve_screenshot(filename: str):
    """
    Intelligent screenshot server:
    1. Returns cached screenshot if present on disk.
    2. If missing (e.g. Render server restarted/slept), tries live-capturing screenshot.
    3. If capture fails or times out, seamlessly redirects to live official courier tracking page.
    Never returns 404!
    """
    raw_name = filename.replace(".png", "").strip()
    courier = ""
    if "_" in raw_name:
        parts = raw_name.rsplit("_", 1)
        awb = parts[0].strip()
        courier_hint = parts[1].strip()
        for known in ["Delhivery", "Shadowfax", "Xpressbees", "Ekart", "BlueDart"]:
            if known.lower() == courier_hint.lower():
                courier = known
                break
    else:
        awb = raw_name

    file_path = os.path.join(SCREENSHOTS_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/png")

    # Check if any matching screenshot file already exists for this AWB
    try:
        if os.path.exists(SCREENSHOTS_DIR):
            for existing in os.listdir(SCREENSHOTS_DIR):
                if (existing.startswith(f"{awb}_") or existing == f"{awb}.png") and existing.endswith(".png"):
                    found_path = os.path.join(SCREENSHOTS_DIR, existing)
                    if os.path.exists(found_path):
                        return FileResponse(found_path, media_type="image/png")
    except Exception:
        pass

    # Identify courier if not yet resolved
    if not courier:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT courier FROM shipments WHERE tracking_number = ? LIMIT 1", (awb,))
            row = cursor.fetchone()
            if row and row[0]:
                courier = row[0]
            conn.close()
        except Exception:
            pass
        
    if not courier:
        awb_upper = awb.upper()
        if awb_upper.startswith("R") or awb_upper.startswith("SF"):
            courier = "Shadowfax"
        elif awb_upper.startswith("FMP") or awb_upper.startswith("EKART") or awb_upper.startswith("MY"):
            courier = "Ekart"
        elif awb_upper.startswith("X") or (awb.isdigit() and len(awb) == 14 and awb.startswith("14")):
            courier = "Xpressbees"
        elif awb.isdigit() and len(awb) in [12, 13, 14, 15]:
            courier = "Delhivery"
        elif len(awb) in [8, 9, 10, 11] and awb.isdigit():
            courier = "BlueDart"
        else:
            courier = "Delhivery"

    # Attempt on-demand capture with sufficient time for official rendering
    scraper = ScraperFactory.get_scraper(courier)
    if scraper:
        try:
            res = await asyncio.wait_for(scraper.track(awb, capture_screenshot=True), timeout=70.0)
            ss_url = res.get("screenshot", "")
            if ss_url and ss_url != "-":
                ss_filename = os.path.basename(ss_url)
                captured_path = os.path.join(SCREENSHOTS_DIR, ss_filename)
                if os.path.exists(captured_path):
                    return FileResponse(captured_path, media_type="image/png")
            if os.path.exists(file_path):
                return FileResponse(file_path, media_type="image/png")
        except Exception as e:
            print(f"On-demand screenshot capture failed for {awb}: {e}")

    # Fallback to official tracking URL so clicking link in Excel always works
    direct_url = get_courier_direct_url(courier, awb)
    return RedirectResponse(url=direct_url, status_code=307)

@app.get('/download/{filename}')
async def download_single_file(filename: str):
    file_path = os.path.join(SCREENSHOTS_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type="image/png")
    raise HTTPException(status_code=404, detail="File not found")

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    # Create tasks table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        status TEXT,
        progress INTEGER,
        current_action TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Create shipments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shipments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT,
        channel TEXT,
        seller_name TEXT,
        return_date TEXT,
        mp_date TEXT,
        days_left TEXT,
        invoice_no TEXT,
        tracking_number TEXT,
        courier TEXT,
        platform_status TEXT,
        status TEXT,
        last_location TEXT,
        timestamp TEXT,
        last_sync TEXT,
        screenshot TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    );
    """)
    # Migration step to add new columns if table already exists
    for col in ["last_sync", "invoice_no", "screenshot", "platform_status", "channel", "seller_name", "return_date", "mp_date", "days_left", "raw_data"]:
        try:
            cursor.execute(f"ALTER TABLE shipments ADD COLUMN {col} TEXT;")
        except sqlite3.OperationalError:
            pass
    # Create logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT,
        message TEXT,
        level TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    );
    """)
    # Create api_usage table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS api_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Prune task data older than 24 hours
    cursor.execute("DELETE FROM tasks WHERE created_at < datetime('now', '-24 hours');")
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

class StartTrackRequest(BaseModel):
    task_id: str
    shipments: Optional[List[dict]] = None
    capture_screenshot: Optional[bool] = False
    selected_tracking_numbers: Optional[List[str]] = None

class DownloadScreenshotsRequest(BaseModel):
    task_id: Optional[str] = None
    tracking_numbers: Optional[List[str]] = None

class SyncSingleRequest(BaseModel):
    task_id: str
    tracking_number: str
    courier: str
    channel: Optional[str] = ""
    seller_name: Optional[str] = ""
    return_date: Optional[str] = ""
    mp_date: Optional[str] = ""
    days_left: Optional[str] = ""
    invoice_no: Optional[str] = ""
    platform_status: Optional[str] = ""
    capture_screenshot: Optional[bool] = False

class RestoreTaskRequest(BaseModel):
    task_id: str
    shipments: List[dict]

class ExportDirectRequest(BaseModel):
    task_id: Optional[str] = "export"
    shipments: List[dict]

@app.get('/')
def root():
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

def clean_date_str(val) -> str:
    if not val or pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith(" 00:00:00"):
        s = s[:-9].strip()
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        parts = s.split("-")
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return s

def clean_tracking_number(awb_val) -> str:
    if pd.isna(awb_val):
        return ""
    s = str(awb_val).strip()
    if not s:
        return ""
        
    # If string contains scientific notation (e.g. 1.95e+14)
    if 'e' in s.lower():
        try:
            val = float(s)
            return str(int(val)) if val.is_integer() else f"{val:.0f}"
        except ValueError:
            pass
            
    # If float-like (e.g. 195042600200336.0)
    try:
        val = float(s)
        if val.is_integer():
            return str(int(val))
    except ValueError:
        pass
        
    return s

def find_col_value(row, aliases) -> str:
    # Normalized search over row keys
    row_dict = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        norm_alias = alias.strip().lower()
        if norm_alias in row_dict:
            val = row_dict[norm_alias]
            if pd.notna(val):
                return str(val).strip()
    return ""

def normalize_courier_name(raw_courier: str, awb: str = "") -> str:
    name = str(raw_courier or "").lower().replace(" ", "").replace("-", "").replace("_", "")
    awb_clean = str(awb or "").upper().strip()
    
    if any(k in name for k in ["xpress", "xpess", "xpes", "xbees", "xb"]):
        return "Xpressbees"
    elif any(k in name for k in ["shadowfax", "shadofex", "shadofax", "shadow", "shado", "sf"]):
        return "Shadowfax"
    elif any(k in name for k in ["delhivery", "delivery", "dlv", "delh"]):
        return "Delhivery"
    elif any(k in name for k in ["bluedart", "blue", "bdart"]):
        return "Bluedart"
    elif any(k in name for k in ["ekart", "ekl", "myntra", "mysc"]):
        return "Ekart"
        
    if awb_clean:
        if awb_clean.startswith("SF") or awb_clean.startswith("R") or "AJI" in awb_clean or "MYE" in awb_clean:
            return "Shadowfax"
        elif len(awb_clean) in [13, 14, 15] and (awb_clean.startswith("13") or awb_clean.startswith("14") or awb_clean.startswith("23")):
            return "Xpressbees"
        elif awb_clean.startswith("19") and len(awb_clean) >= 12:
            return "Delhivery"
        elif len(awb_clean) in [9, 10, 11] and awb_clean.isdigit():
            return "Bluedart"
            
    return raw_courier.title() if raw_courier else "Delhivery"

@app.post('/api/upload')
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in ['.csv', '.xlsx', '.xls']:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV or Excel.")

    contents = await file.read()
    shipments = []

    channel_aliases = ['channel', 'channels', 'sales channel', 'platform']
    seller_name_aliases = ['seller name', 'seller_name', 'seller', 'vendor', 'sellername']
    return_date_aliases = ['return date', 'return_date', 'ret date', 'ret_date', 'retum date', 'retum_date', 'retum', 'return_dt', 'ret_dt']
    mp_date_aliases = ['mp date', 'mp_date', 'marketplace date', 'mp date.', 'marketplace_date']
    days_left_aliases = ['days left', 'days_left', 'days', 'daysleft', 'day left', 'day_left']
    invoice_aliases = ['invoice no', 'invoice_no', 'invoice no.', 'invoice', 'invoice number', 'inv no', 'inv_no', 'invoice#', 'inv']
    awb_aliases = ['awb', 'awb no', 'awb no.', 'awb number', 'tracking number', 'tracking_number', 'tracking no', 'tracking_no', 'tracking #', 'waybill']
    courier_aliases = ['courier', 'courier partner', 'courier_partner', 'courier name', 'courier_name', 'partner', 'logistic', 'logistics']
    platform_status_aliases = ['platform status', 'platform_status', 'order status', 'order_status', 'platform status name', 'platform_status_name']

    try:
        if ext == '.csv':
            decoded = contents.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(decoded))
            for row in csv_reader:
                channel = find_col_value(row, channel_aliases)
                seller_name = find_col_value(row, seller_name_aliases)
                return_date = clean_date_str(find_col_value(row, return_date_aliases))
                mp_date = clean_date_str(find_col_value(row, mp_date_aliases))
                days_left = find_col_value(row, days_left_aliases)
                invoice = find_col_value(row, invoice_aliases)
                awb = find_col_value(row, awb_aliases)
                courier = find_col_value(row, courier_aliases)
                platform_status = find_col_value(row, platform_status_aliases)
                
                if awb:
                    clean_awb = clean_tracking_number(awb)
                    if clean_awb:
                        norm_courier = normalize_courier_name(courier, clean_awb)
                        shipments.append({
                            "channel": channel,
                            "seller_name": seller_name,
                            "return_date": return_date,
                            "mp_date": mp_date,
                            "days_left": days_left,
                            "invoice_no": invoice,
                            "tracking_number": clean_awb,
                            "courier": norm_courier,
                            "platform_status": platform_status,
                            "status": "Pending",
                            "last_location": "Awaiting scan",
                            "timestamp": "-",
                            "last_sync": "-",
                            "screenshot": "-"
                        })
        else:
            df = pd.read_excel(io.BytesIO(contents), dtype=str)
            for _, row in df.iterrows():
                # row can be converted to dict to use find_col_value
                row_dict = row.to_dict()
                channel = find_col_value(row_dict, channel_aliases)
                seller_name = find_col_value(row_dict, seller_name_aliases)
                return_date = clean_date_str(find_col_value(row_dict, return_date_aliases))
                mp_date = clean_date_str(find_col_value(row_dict, mp_date_aliases))
                days_left = find_col_value(row_dict, days_left_aliases)
                invoice = find_col_value(row_dict, invoice_aliases)
                awb = find_col_value(row_dict, awb_aliases)
                courier = find_col_value(row_dict, courier_aliases)
                platform_status = find_col_value(row_dict, platform_status_aliases)
                
                if awb and str(awb).strip():
                    clean_awb = clean_tracking_number(awb)
                    norm_courier = normalize_courier_name(courier, clean_awb)
                    shipments.append({
                        "channel": channel,
                        "seller_name": seller_name,
                        "return_date": return_date,
                        "mp_date": mp_date,
                        "days_left": days_left,
                        "invoice_no": invoice,
                        "tracking_number": clean_awb,
                        "courier": norm_courier,
                        "platform_status": platform_status,
                        "status": "Pending",
                        "last_location": "Awaiting scan",
                        "timestamp": "-",
                        "last_sync": "-",
                        "screenshot": "-"
                    })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing tracking sheet: {str(e)}")

    if not shipments:
        raise HTTPException(status_code=400, detail="No tracking numbers found in the uploaded sheet. Please check headers (AWB, Courier).")

    task_id = str(uuid.uuid4())
    
    # Save upload to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (task_id, status, progress, current_action) VALUES (?, ?, ?, ?)", (task_id, "pending", 0, "Ready to start"))
    
    for s in shipments:
        cursor.execute("""
        INSERT INTO shipments (task_id, channel, seller_name, return_date, mp_date, days_left, invoice_no, tracking_number, courier, platform_status, status, last_location, timestamp, last_sync, screenshot)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            s.get("channel", ""),
            s.get("seller_name", ""),
            s.get("return_date", ""),
            s.get("mp_date", ""),
            s.get("days_left", ""),
            s.get("invoice_no", ""),
            s["tracking_number"],
            s["courier"],
            s.get("platform_status", ""),
            s["status"],
            s["last_location"],
            s["timestamp"],
            "-",
            "-"
        ))
        
    cursor.execute("INSERT INTO logs (task_id, message, level) VALUES (?, ?, ?)", (task_id, f"Successfully parsed {filename}. Found {len(shipments)} records.", "success"))
    cursor.execute("INSERT INTO logs (task_id, message, level) VALUES (?, ?, ?)", (task_id, "Ready to begin courier web scraping simulation.", "info"))
    
    # Get today's API calls count
    cursor.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp >= datetime('now', 'start of day');")
    today_api_calls = cursor.fetchone()[0]

    conn.commit()
    conn.close()

    # Calculate stats
    delivered = sum(1 for s in shipments if s["status"].lower() == "delivered")
    transit = sum(1 for s in shipments if s["status"].lower() in ["in transit", "out for delivery", "picked up", "out for pickup"])
    failed = sum(1 for s in shipments if "failed" in s["status"].lower() or "invalid" in s["status"].lower() or "error" in s["status"].lower())

    stats = {
        "total": len(shipments),
        "delivered": delivered,
        "transit": transit,
        "failed": failed,
        "api_calls": today_api_calls
    }

    return {"task_id": task_id, "shipments": shipments, "stats": stats}


# Real background task runner calling TrackingService
async def run_tracking_simulation(task_id: str, capture_screenshot: bool = False, selected_tracking_numbers: Optional[List[str]] = None):
    # Retrieve shipments from database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT tracking_number, courier, status, last_location, timestamp, last_sync, screenshot, channel, seller_name, return_date, mp_date, days_left, invoice_no, platform_status FROM shipments WHERE task_id = ?", (task_id,))
    rows = cursor.fetchall()
    conn.close()
    
    shipments = []
    for r in rows:
        shipments.append({
            "tracking_number": r[0],
            "courier": r[1],
            "status": r[2],
            "last_location": r[3],
            "timestamp": r[4],
            "last_sync": r[5] or "-",
            "screenshot": r[6] or "-",
            "channel": r[7] or "",
            "seller_name": r[8] or "",
            "return_date": r[9] or "",
            "mp_date": r[10] or "",
            "days_left": r[11] or "",
            "invoice_no": r[12] or "",
            "platform_status": r[13] or ""
        })

    if selected_tracking_numbers:
        selected_set = set(selected_tracking_numbers)
        shipments_to_track = [s for s in shipments if s["tracking_number"] in selected_set]
        if not shipments_to_track:
            shipments_to_track = shipments
    else:
        shipments_to_track = shipments
        
    # Set status to running
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("running", task_id))
    conn.commit()
    conn.close()
    
    # We define progress callback to update SQLite task
    async def progress_callback(progress, current_action, log_message, log_level, shipment=None):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=20.0)
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET progress = ?, current_action = ? WHERE task_id = ?", (progress, current_action, task_id))
            
            # High performance update: update ONLY the shipment that just finished
            if shipment:
                cursor.execute("""
                UPDATE shipments 
                SET status = ?, last_location = ?, timestamp = ?, last_sync = ?, screenshot = ?, raw_data = ? 
                WHERE task_id = ? AND tracking_number = ?
                """, (shipment["status"], shipment["last_location"], shipment["timestamp"], shipment.get("last_sync", "-"), shipment.get("screenshot", "-"), json.dumps(shipment.get("events", [])), task_id, shipment["tracking_number"]))
            else:
                for s in shipments_to_track:
                    cursor.execute("""
                    UPDATE shipments 
                    SET status = ?, last_location = ?, timestamp = ?, last_sync = ?, screenshot = ?, raw_data = ? 
                    WHERE task_id = ? AND tracking_number = ?
                    """, (s["status"], s["last_location"], s["timestamp"], s.get("last_sync", "-"), s.get("screenshot", "-"), json.dumps(s.get("events", [])), task_id, s["tracking_number"]))
                
            cursor.execute("INSERT INTO logs (task_id, message, level) VALUES (?, ?, ?)", (task_id, log_message, log_level))
            conn.commit()
            conn.close()
        except Exception as db_err:
            print("progress_callback DB error:", db_err)

    try:
        await TrackingService.track_shipments(shipments_to_track, task_id, progress_callback, capture_screenshot=capture_screenshot)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("completed", task_id))
        conn.commit()
        conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("failed", task_id))
        cursor.execute("INSERT INTO logs (task_id, message, level) VALUES (?, ?, ?)", (task_id, f"Fatal tracking engine error: {str(e)}", "error"))
        conn.commit()
        conn.close()


class QuerySingleRequest(BaseModel):
    tracking_number: str
    courier: str
    capture_screenshot: Optional[bool] = False

@app.post('/api/track/query_single')
async def query_single_shipment(body: QuerySingleRequest):
    awb = body.tracking_number.strip()
    courier = body.courier.strip()
    capture_screenshot = body.capture_screenshot or False
    
    if not awb or not courier:
        raise HTTPException(status_code=400, detail="AWB number and Courier are required")
        
    scraper = ScraperFactory.get_scraper(courier, awb=awb)
    if not scraper:
        raise HTTPException(status_code=400, detail=f"Courier '{courier}' not supported")
        
    req_payload = {
        "tracking_number": awb,
        "courier": courier,
        "capture_screenshot": capture_screenshot
    }
    print(f"\n========================================================")
    print(f"[SINGLE QUERY REQUEST] >>> Courier: {courier} | AWB: {awb}")
    print(f"[SINGLE QUERY REQUEST] JSON: {json.dumps(req_payload)}")
    print(f"--------------------------------------------------------")

    # Track immediately
    try:
        result = await scraper.track(awb, capture_screenshot=capture_screenshot)
        print(f"[SINGLE QUERY RESPONSE] <<< Courier: {courier} | AWB: {awb}")
        print(f"[SINGLE QUERY RESPONSE] JSON Result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"========================================================\n")
        status = result["status"]
        last_location = result["last_location"]
        timestamp = result["timestamp"]
        screenshot = result.get("screenshot", "-")
        events = result.get("events", [])
    except Exception as e:
        print(f"[SINGLE QUERY ERROR] <<< Courier: {courier} | AWB: {awb} | Error: {e}")
        status = "Scrape Error"
        last_location = f"Error: {str(e)}"
        timestamp = "-"
        screenshot = "-"
        events = []
        
    # API calls tracking
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO api_usage DEFAULT VALUES;")
    cursor.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp >= datetime('now', 'start of day');")
    today_api_calls = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    
    return {
        "tracking_number": awb,
        "courier": courier,
        "status": status,
        "last_location": last_location,
        "timestamp": timestamp,
        "screenshot": screenshot,
        "events": events,
        "api_calls": today_api_calls
    }




@app.post('/api/track/start')
async def start_tracking(body: StartTrackRequest, background_tasks: BackgroundTasks):
    task_id = body.task_id
    capture_screenshot = body.capture_screenshot or False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,))
    exists = cursor.fetchone()
    
    # Self-healing: If task doesn't exist in DB (e.g. server woke up or restarted), re-create it if shipments are sent
    if not exists:
        if body.shipments:
            cursor.execute("INSERT OR REPLACE INTO tasks (task_id, status, progress, current_action) VALUES (?, ?, ?, ?)", (task_id, "pending", 0, "Ready to start"))
            for s in body.shipments:
                cursor.execute("""
                INSERT INTO shipments (task_id, channel, seller_name, return_date, mp_date, days_left, invoice_no, tracking_number, courier, platform_status, status, last_location, timestamp, last_sync, screenshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id,
                    s.get("channel", ""),
                    s.get("seller_name", ""),
                    s.get("return_date", ""),
                    s.get("mp_date", ""),
                    s.get("days_left", ""),
                    s.get("invoice_no", ""),
                    s["tracking_number"],
                    s.get("courier", "Delhivery"),
                    s.get("platform_status", ""),
                    s.get("status", "Pending"),
                    s.get("last_location", "Awaiting scan"),
                    s.get("timestamp", "-"),
                    s.get("last_sync", "-"),
                    s.get("screenshot", "-")
                ))
            cursor.execute("INSERT INTO logs (task_id, message, level) VALUES (?, ?, ?)", (task_id, f"Restored {len(body.shipments)} records into task session.", "info"))
            conn.commit()
        else:
            conn.close()
            raise HTTPException(status_code=404, detail="Task ID not found")
            
    selected_tracking_numbers = body.selected_tracking_numbers or None
    background_tasks.add_task(run_tracking_simulation, task_id, capture_screenshot, selected_tracking_numbers)
    return {"status": "started"}


@app.post('/api/track/sync_single')
async def sync_single_shipment(body: SyncSingleRequest):
    task_id = body.task_id
    awb = body.tracking_number
    courier = body.courier
    capture_screenshot = body.capture_screenshot or False
    
    scraper = ScraperFactory.get_scraper(courier, awb=awb)
    if not scraper:
        raise HTTPException(status_code=400, detail=f"Courier '{courier}' not supported")
        
    req_payload = {
        "tracking_number": awb,
        "courier": courier,
        "task_id": task_id,
        "capture_screenshot": capture_screenshot
    }
    print(f"\n========================================================")
    print(f"[SINGLE SYNC REQUEST] >>> Courier: {courier} | AWB: {awb}")
    print(f"[SINGLE SYNC REQUEST] JSON: {json.dumps(req_payload)}")
    print(f"--------------------------------------------------------")

    try:
        result = await scraper.track(awb, capture_screenshot=capture_screenshot)
        print(f"[SINGLE SYNC RESPONSE] <<< Courier: {courier} | AWB: {awb}")
        print(f"[SINGLE SYNC RESPONSE] JSON Result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"========================================================\n")
        
        from datetime import datetime
        last_sync_str = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
        
        # Self-healing: Ensure task and shipment exist in DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO api_usage DEFAULT VALUES;")
        cursor.execute("INSERT OR IGNORE INTO tasks (task_id, status, progress, current_action) VALUES (?, ?, ?, ?)", (task_id, "completed", 100, "Idle"))
        
        events = result.get("events", [])
        events_json = json.dumps(events)
        
        cursor.execute("SELECT screenshot FROM shipments WHERE task_id = ? AND tracking_number = ?", (task_id, awb))
        existing_shipment = cursor.fetchone()
        
        final_screenshot = result.get("screenshot", "-")
        if (not final_screenshot or final_screenshot == "-") and existing_shipment and existing_shipment[0] and existing_shipment[0] != "-":
            final_screenshot = existing_shipment[0]
            
        if not existing_shipment:
            cursor.execute("""
            INSERT INTO shipments (task_id, channel, seller_name, return_date, mp_date, days_left, invoice_no, tracking_number, courier, platform_status, status, last_location, timestamp, last_sync, screenshot, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id,
                body.channel or "",
                body.seller_name or "",
                body.return_date or "",
                body.mp_date or "",
                body.days_left or "",
                body.invoice_no or "",
                awb,
                courier,
                body.platform_status or "",
                result.get("status"),
                result.get("last_location"),
                result.get("timestamp"),
                last_sync_str,
                final_screenshot,
                events_json
            ))
        else:
            cursor.execute("""
            UPDATE shipments 
            SET status = ?, last_location = ?, timestamp = ?, last_sync = ?, screenshot = ?, raw_data = ? 
            WHERE task_id = ? AND tracking_number = ?
            """, (result.get("status"), result.get("last_location"), result.get("timestamp"), last_sync_str, final_screenshot, events_json, task_id, awb))
        
        # Log the manual update
        cursor.execute("""
        INSERT INTO logs (task_id, message, level) 
        VALUES (?, ?, ?)
        """, (task_id, f"Manually synced {courier} AWB {awb}. Status: {result.get('status')}", "success"))
        
        # Get today's API calls count
        cursor.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp >= datetime('now', 'start of day');")
        today_api_calls = cursor.fetchone()[0]

        conn.commit()
        conn.close()
        
        return {
            "status": result.get("status"),
            "last_location": result.get("last_location"),
            "timestamp": result.get("timestamp"),
            "last_sync": last_sync_str,
            "screenshot": final_screenshot,
            "events": events,
            "api_calls": today_api_calls
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape error: {str(e)}")


@app.get('/api/track/events/{awb}')
async def get_shipment_events(awb: str):
    clean_awb = awb.strip()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT raw_data, courier, status, last_location, timestamp, screenshot FROM shipments WHERE tracking_number = ? ORDER BY id DESC LIMIT 1", (clean_awb,))
    row = cursor.fetchone()
    conn.close()
    
    events = []
    if row and row[0]:
        try:
            events = json.loads(row[0])
        except Exception:
            events = []
            
    return {
        "tracking_number": clean_awb,
        "courier": row[1] if row else "",
        "status": row[2] if row else "Pending",
        "last_location": row[3] if row else "",
        "timestamp": row[4] if row else "-",
        "screenshot": row[5] if row else "-",
        "events": events
    }


@app.get('/api/track/progress')
async def get_progress(task_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, progress, current_action FROM tasks WHERE task_id = ?", (task_id,))
    task_row = cursor.fetchone()
    if not task_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Task ID not found")
        
    status, progress, current_action = task_row
    
    # Get shipments
    cursor.execute("SELECT channel, seller_name, return_date, mp_date, days_left, invoice_no, tracking_number, courier, platform_status, status, last_location, timestamp, last_sync, screenshot, raw_data FROM shipments WHERE task_id = ?", (task_id,))
    shipment_rows = cursor.fetchall()
    shipments = []
    for r in shipment_rows:
        raw_events = []
        if len(r) > 14 and r[14]:
            try:
                raw_events = json.loads(r[14])
            except Exception:
                raw_events = []
        shipments.append({
            "channel": r[0] or "",
            "seller_name": r[1] or "",
            "return_date": r[2] or "",
            "mp_date": r[3] or "",
            "days_left": r[4] or "",
            "invoice_no": r[5] or "",
            "tracking_number": r[6],
            "courier": r[7],
            "platform_status": r[8] or "",
            "status": r[9],
            "last_location": r[10],
            "timestamp": r[11],
            "last_sync": r[12] or "-",
            "screenshot": r[13] or "-",
            "events": raw_events
        })
        
    # Get logs
    cursor.execute("SELECT message, level FROM logs WHERE task_id = ? ORDER BY id ASC", (task_id,))
    log_rows = cursor.fetchall()
    logs = [{"message": r[0], "level": r[1]} for r in log_rows]
    
    # Clear logs for this poll (so they are only displayed once on console)
    cursor.execute("DELETE FROM logs WHERE task_id = ?", (task_id,))
    
    # Get today's API calls count
    cursor.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp >= datetime('now', 'start of day');")
    today_api_calls = cursor.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    # Calculate stats
    delivered = sum(1 for s in shipments if s["status"].lower() == "delivered")
    transit = sum(1 for s in shipments if s["status"].lower() in ["in transit", "out for delivery", "picked up", "out for pickup"])
    failed = sum(1 for s in shipments if "failed" in s["status"].lower() or "invalid" in s["status"].lower() or "error" in s["status"].lower())
    
    stats = {
        "total": len(shipments),
        "delivered": delivered,
        "transit": transit,
        "failed": failed,
        "api_calls": today_api_calls
    }
    
    return {
        "status": status,
        "progress": progress,
        "current_action": current_action,
        "shipments": shipments,
        "stats": stats,
        "logs": logs
    }


def generate_excel_stream(shipment_rows, task_id: str, request: Request):
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    has_pillow = False
    OpenpyxlImage = None
    try:
        from PIL import Image as PILImage
        from openpyxl.drawing.image import Image as OpenpyxlImage
        has_pillow = True
    except Exception as e:
        print(f"[EXCEL EXPORT] Pillow/OpenpyxlImage not available ({e}). Falling back to text links.")
        has_pillow = False

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tracking Results"

    # Define headers matching the Excel layout followed by tracking status
    headers = [
        "Channel", "Seller Name", "Return Date", "MP Date", "Days Left",
        "Invoice No.", "AWB No.", "Courier Partner", "Platform Status",
        "Status", "Last Location", "Timestamp", "Last Sync", "Image"
    ]
    ws.append(headers)
    ws.row_dimensions[1].height = 26

    # Set Header styling (bold, light gray background, center align)
    header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="334155")
    header_align = Alignment(horizontal="center", vertical="center")

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    # Add data rows with colors matching the frontend palette
    AWB_COLORS_HEX = [
        '1E40AF', '9D174D', '065F46', '92400E', '5B21B6',
        'C2410C', '155E75', '9F1239', '166534', '3730A3',
        '854D0E', '6B21A8', '134E4A', '991B1B', '075985',
        '86198F', '3F6212', '334155', 'BE123C', '115E59',
        'A21CAF', '14532D', '1E3A8A', '78350F', '831843',
        '4C1D95', '064E3B', '9A3412', '0F172A', '713F12'
    ]

    blue_icon_path = os.path.join(STATIC_DIR, "gallery_icon_blue_excel.png")
    red_icon_path = os.path.join(STATIC_DIR, "gallery_icon_red_excel.png")

    for idx, r in enumerate(shipment_rows):
        row_num = idx + 2
        ws.row_dimensions[row_num].height = 24
        row_color = AWB_COLORS_HEX[idx % len(AWB_COLORS_HEX)]
        row_font = Font(name="Segoe UI", size=11, color=row_color)
        
        # Write values
        values = [
            r[0] or "",   # Channel
            r[1] or "",   # Seller Name
            r[2] or "",   # Return Date
            r[3] or "",   # MP Date
            r[4] or "",   # Days Left
            r[5] or "",   # Invoice No.
            r[6] or "",   # AWB No.
            r[7] or "",   # Courier Partner
            r[8] or "",   # Platform Status
            r[9] or "",   # Status
            r[10] or "",  # Last Location
            r[11] or "",  # Timestamp
            r[12] or "-"  # Last Sync
        ]
        
        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.font = row_font
            # Alignments: Left align for text/location/seller, Center for status/numbers/dates
            if col_idx in [1, 3, 4, 5, 6, 7, 9, 10, 12, 13]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
                
        # Write Image icon / hyperlink column (col_idx = 14)
        # NOTE: Floating images (ws.add_image) sit on TOP of the cell and block
        # click events, so cell.hyperlink is never triggered. Instead we use a
        # proper text-based cell hyperlink ("🔗") which is 100% clickable in Excel.
        screenshot_path = r[13] if len(r) > 13 else "-"
        awb_for_link = r[6] or ""    # tracking_number
        courier_for_link = r[7] or ""  # courier
        cell = ws.cell(row=row_num, column=14)
        cell.alignment = Alignment(horizontal="center", vertical="center")

        if screenshot_path and screenshot_path != "-":
            # Build screenshot URL
            base_url_str = str(request.base_url).rstrip('/')
            if str(screenshot_path).startswith("http"):
                link_url = screenshot_path
            else:
                link_url = f"{base_url_str}{screenshot_path}"

            # Only gallery emoji, no text — clicking opens screenshot/tracking page
            cell.value = "🖼️"
            cell.hyperlink = link_url
            cell.font = Font(name="Segoe UI", size=14, color="1155CC", underline="single", bold=True)
        else:
            # No screenshot — show direct courier tracking link with just gallery icon
            direct_url = get_courier_direct_url(courier_for_link, awb_for_link)
            cell.value = "🖼️"
            cell.hyperlink = direct_url
            cell.font = Font(name="Segoe UI", size=14, color="CC4400", underline="single")

    # Auto-adjust column widths
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        if col_letter == 'N':
            ws.column_dimensions['N'].width = 14
            continue
        max_len = 0
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # Save to dynamic buffer
    out_buf = io.BytesIO()
    wb.save(out_buf)
    out_buf.seek(0)

    filename_suffix = (task_id[:8] if task_id else "export")
    return StreamingResponse(
        out_buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=tracking_export_{filename_suffix}.xlsx"}
    )


@app.get('/api/export')
async def export_results(task_id: str, request: Request):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT channel, seller_name, return_date, mp_date, days_left, invoice_no, tracking_number, courier, platform_status, status, last_location, timestamp, last_sync, screenshot FROM shipments WHERE task_id = ?", (task_id,))
    shipment_rows = cursor.fetchall()
    conn.close()
    
    if not shipment_rows:
        raise HTTPException(status_code=404, detail="Task ID not found")
        
    return generate_excel_stream(shipment_rows, task_id, request)


@app.post('/api/export_direct')
async def export_direct(body: ExportDirectRequest, request: Request):
    """Export Excel directly from client-supplied shipments if server DB was reset."""
    rows = []
    for s in body.shipments:
        rows.append((
            s.get("channel", ""),
            s.get("seller_name", ""),
            s.get("return_date", ""),
            s.get("mp_date", ""),
            s.get("days_left", ""),
            s.get("invoice_no", ""),
            s.get("tracking_number", ""),
            s.get("courier", ""),
            s.get("platform_status", ""),
            s.get("status", ""),
            s.get("last_location", ""),
            s.get("timestamp", ""),
            s.get("last_sync", "-"),
            s.get("screenshot", "-")
        ))
    return generate_excel_stream(rows, body.task_id or "export", request)


@app.post('/api/download-screenshots')
async def download_screenshots(body: DownloadScreenshotsRequest):
    tracking_numbers = [str(x).strip() for x in (body.tracking_numbers or []) if str(x).strip()]
    task_id = (body.task_id or "").strip()

    target_screenshots = []
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if tracking_numbers:
        placeholders = ','.join('?' for _ in tracking_numbers)
        cursor.execute(f"SELECT tracking_number, courier, screenshot FROM shipments WHERE tracking_number IN ({placeholders})", tracking_numbers)
        rows = cursor.fetchall()
        for r in rows:
            if r[2] and r[2] != '-':
                target_screenshots.append((r[0], r[1], r[2]))
    elif task_id:
        cursor.execute("SELECT tracking_number, courier, screenshot FROM shipments WHERE task_id = ?", (task_id,))
        rows = cursor.fetchall()
        for r in rows:
            if r[2] and r[2] != '-':
                target_screenshots.append((r[0], r[1], r[2]))
    else:
        cursor.execute("SELECT tracking_number, courier, screenshot FROM shipments WHERE screenshot IS NOT NULL AND screenshot != '-'")
        rows = cursor.fetchall()
        for r in rows:
            target_screenshots.append((r[0], r[1], r[2]))
    conn.close()

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    zip_buffer = io.BytesIO()
    found_count = 0
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        added_awbs = set()
        
        # 1. From database records (exact registered screenshot path with courier name)
        for awb, courier, sc_path in target_screenshots:
            if awb in added_awbs:
                continue
            filename = os.path.basename(sc_path)
            disk_path = os.path.join(SCREENSHOTS_DIR, filename)
            if os.path.exists(disk_path):
                zip_file.write(disk_path, arcname=filename)
                added_awbs.add(awb)
                found_count += 1
                
        # 2. Disk fallback: Only select files with courier name ({awb}_{courier}.png)
        all_disk_files = [f for f in os.listdir(SCREENSHOTS_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        
        candidate_awbs = tracking_numbers if tracking_numbers else [
            f.split('_')[0] for f in all_disk_files 
            if '_' in f and not f.startswith(('test_', 'delhivery_'))
        ]
        
        for awb in candidate_awbs:
            if awb in added_awbs:
                continue
            # Look for file starting with {awb}_ (contains courier name)
            matching = [f for f in all_disk_files if f.startswith(f"{awb}_")]
            if matching:
                chosen = matching[0]
                disk_path = os.path.join(SCREENSHOTS_DIR, chosen)
                if os.path.isfile(disk_path):
                    zip_file.write(disk_path, arcname=chosen)
                    added_awbs.add(awb)
                    found_count += 1

    if found_count == 0:
        raise HTTPException(status_code=404, detail="No screenshots found. Please sync with Screenshot Mode first.")

    zip_buffer.seek(0)
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    headers = {
        "Content-Disposition": f"attachment; filename=screenshots_{now_str}.zip"
    }
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)



@app.post('/api/restore_task')
async def restore_task(body: RestoreTaskRequest):
    """Restore task and shipments into SQLite database from client session storage."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO tasks (task_id, status, progress, current_action) VALUES (?, ?, ?, ?)", (body.task_id, "completed", 100, "Restored from session"))
    cursor.execute("DELETE FROM shipments WHERE task_id = ?", (body.task_id,))
    for s in body.shipments:
        cursor.execute("""
        INSERT INTO shipments (task_id, channel, seller_name, return_date, mp_date, days_left, invoice_no, tracking_number, courier, platform_status, status, last_location, timestamp, last_sync, screenshot)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            body.task_id,
            s.get("channel", ""),
            s.get("seller_name", ""),
            s.get("return_date", ""),
            s.get("mp_date", ""),
            s.get("days_left", ""),
            s.get("invoice_no", ""),
            s["tracking_number"],
            s.get("courier", "Delhivery"),
            s.get("platform_status", ""),
            s.get("status", "Pending"),
            s.get("last_location", "Awaiting scan"),
            s.get("timestamp", "-"),
            s.get("last_sync", "-"),
            s.get("screenshot", "-")
        ))
    conn.commit()
    conn.close()
    return {"status": "restored", "count": len(body.shipments)}



@app.get('/api/latest')
async def get_latest_task():
    """Return the most recent task's shipments so the UI can restore on page refresh."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get the most recent task
    cursor.execute("SELECT task_id FROM tasks ORDER BY created_at DESC LIMIT 1")
    task_row = cursor.fetchone()

    if not task_row:
        conn.close()
        return {"task_id": None, "shipments": [], "stats": {"total": 0, "delivered": 0, "transit": 0, "failed": 0, "api_calls": 0}}

    task_id = task_row[0]

    # Get shipments
    cursor.execute("SELECT channel, seller_name, return_date, mp_date, days_left, invoice_no, tracking_number, courier, platform_status, status, last_location, timestamp, last_sync, screenshot FROM shipments WHERE task_id = ?", (task_id,))
    shipment_rows = cursor.fetchall()
    shipments = []
    for r in shipment_rows:
        shipments.append({
            "channel": r[0] or "",
            "seller_name": r[1] or "",
            "return_date": r[2] or "",
            "mp_date": r[3] or "",
            "days_left": r[4] or "",
            "invoice_no": r[5] or "",
            "tracking_number": r[6],
            "courier": r[7],
            "platform_status": r[8] or "",
            "status": r[9],
            "last_location": r[10],
            "timestamp": r[11],
            "last_sync": r[12] or "-",
            "screenshot": r[13] or "-"
        })

    # Get today's API calls count
    cursor.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp >= datetime('now', 'start of day');")
    today_api_calls = cursor.fetchone()[0]

    conn.close()

    # Calculate stats
    delivered = sum(1 for s in shipments if s["status"].lower() == "delivered")
    transit = sum(1 for s in shipments if s["status"].lower() in ["in transit", "out for delivery", "picked up", "out for pickup"])
    failed = sum(1 for s in shipments if "failed" in s["status"].lower() or "invalid" in s["status"].lower() or "error" in s["status"].lower())

    stats = {
        "total": len(shipments),
        "delivered": delivered,
        "transit": transit,
        "failed": failed,
        "api_calls": today_api_calls
    }

    return {"task_id": task_id, "shipments": shipments, "stats": stats}


@app.delete('/api/clear')
async def clear_all_data():
    """Delete all tasks, shipments, and logs from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logs")
    cursor.execute("DELETE FROM shipments")
    cursor.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()
    return {"status": "cleared"}
