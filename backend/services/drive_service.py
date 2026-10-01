import os
import sys
import json
import base64
import io
import asyncio
import urllib.request
from typing import Optional
from PIL import Image

# Google Apps Script Web App URL for Brandcentral Tracking
GOOGLE_DRIVE_WEBAPP_URL = os.environ.get(
    "GOOGLE_DRIVE_WEBAPP_URL",
    "https://script.google.com/macros/s/AKfycbwlW6x8Kf_xVg2-jJKbpZlQMR8tmp6aqB50k32JmpUSxDerUgW3cGNhBW_AESRYvC-8jg/exec"
)

class GoogleAppsScriptRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    Google Apps Script responds to POST with a 302 redirect to script.googleusercontent.com.
    This handler follows the redirect via GET to read the JSON response body.
    """
    def http_error_302(self, req, fp, code, msg, headers):
        new_url = headers.get('Location')
        if new_url:
            return urllib.request.urlopen(new_url, timeout=35)
        return super().http_error_302(req, fp, code, msg, headers)

class DriveService:
    @staticmethod
    def compress_image_to_jpeg_base64(image_path: str, quality: int = 88) -> Optional[str]:
        """
        Compresses image into High-Quality JPEG with 4:4:4 color subsampling (subsampling=0)
        to maintain 100% sharp text, barcodes, and dates while reducing file size to ~120-180KB.
        """
        try:
            with Image.open(image_path) as img:
                rgb_img = img.convert("RGB")
                buf = io.BytesIO()
                # subsampling=0 ensures zero chroma blur on sharp text
                rgb_img.save(buf, format="JPEG", quality=quality, subsampling=0, optimize=True)
                buf.seek(0)
                return base64.b64encode(buf.read()).decode("utf-8")
        except Exception as e:
            print(f"[DriveService] Error compressing image {image_path}: {e}")
            return None

    @staticmethod
    def upload_to_drive(image_path: str, filename: Optional[str] = None, delete_local_after_upload: bool = True) -> Optional[str]:
        """
        Synchronously uploads screenshot to Google Drive via Apps Script Web App.
        Returns the public Google Drive URL, or None if failed.
        Optionally deletes the local file to keep server disk usage at 0 MB.
        """
        if not os.path.exists(image_path):
            return None

        clean_filename = filename or os.path.basename(image_path)
        if not clean_filename.lower().endswith(".jpg") and not clean_filename.lower().endswith(".jpeg"):
            clean_filename = os.path.splitext(clean_filename)[0] + ".jpg"

        base64_data = DriveService.compress_image_to_jpeg_base64(image_path, quality=88)
        if not base64_data:
            return None

        payload = json.dumps({
            "filename": clean_filename,
            "image_base64": base64_data,
            "mime_type": "image/jpeg"
        }).encode("utf-8")

        req = urllib.request.Request(
            GOOGLE_DRIVE_WEBAPP_URL,
            data=payload,
            headers={
                "Content-Type": "application/json"
            }
        )

        opener = urllib.request.build_opener(GoogleAppsScriptRedirectHandler)
        try:
            res = opener.open(req, timeout=35)
            resp_body = res.read().decode("utf-8")
            data = json.loads(resp_body)
            if data.get("status") == "success" and data.get("url"):
                drive_url = data["url"]
                print(f"[DriveService] Uploaded {clean_filename} to Google Drive: {drive_url}")

                # Delete local image from server to ensure 0 MB disk usage on Render / Local
                if delete_local_after_upload:
                    try:
                        if os.path.exists(image_path):
                            os.remove(image_path)
                    except Exception as rm_err:
                        print(f"[DriveService] Local cleanup note: {rm_err}")

                return drive_url
            else:
                print(f"[DriveService] Google Drive upload rejected: {resp_body}")
                return None
        except Exception as upload_err:
            print(f"[DriveService] Failed to upload to Google Drive: {upload_err}")
            return None

    @staticmethod
    async def upload_to_drive_async(image_path: str, filename: Optional[str] = None, delete_local_after_upload: bool = True) -> Optional[str]:
        """
        Non-blocking async wrapper to upload image to Google Drive.
        """
        return await asyncio.to_thread(
            DriveService.upload_to_drive,
            image_path,
            filename,
            delete_local_after_upload
        )

    @staticmethod
    async def upload_and_cleanup(image_path: str, courier_name: str, clean_awb: str, fallback_relative_path: str) -> str:
        """
        Uploads screenshot to Google Drive via Apps Script Web App,
        and deletes local file upon success to ensure 0 MB server disk/RAM usage.
        Returns the Google Drive URL if successful, or fallback_relative_path if upload fails.
        """
        try:
            filename = f"{clean_awb}_{courier_name}.jpg"
            drive_url = await DriveService.upload_to_drive_async(
                image_path=image_path,
                filename=filename,
                delete_local_after_upload=True
            )
            if drive_url:
                print(f"[DriveService] Successfully uploaded & linked: {drive_url}")
                return drive_url
        except Exception as e:
            print(f"[DriveService] Upload failed for {clean_awb} ({courier_name}): {e}")
        return fallback_relative_path

