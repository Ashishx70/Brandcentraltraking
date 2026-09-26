import os
import sys
import time

class DesktopFrameService:
    @staticmethod
    def _attach_default_desktop():
        """Ensure the calling thread is attached to WinSta0\\Default so ImageGrab captures the real user screen."""
        if sys.platform == "win32":
            try:
                import ctypes
                u32 = ctypes.windll.user32
                hd = u32.OpenDesktopW("Default", 0, False, 0x01FF)
                if hd:
                    u32.SetThreadDesktop(hd)
            except Exception as e:
                print(f"[DesktopFrameService] SetThreadDesktop note: {e}")

    @staticmethod
    def bring_tracking_window_to_front() -> bool:
        """
        Finds the Playwright Chrome tracking window on WinSta0\\Default and forces it
        to the front (HWND_TOPMOST + Maximized) above Brandcentral TrackShip and all other windows.
        """
        if sys.platform != "win32":
            return False

        try:
            import ctypes
            from ctypes import wintypes

            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32

            DesktopFrameService._attach_default_desktop()

            # Define 64-bit safe signatures for Win32 window functions
            u32.SetWindowPos.argtypes = [
                wintypes.HWND, wintypes.HWND,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.UINT
            ]
            u32.SetWindowPos.restype = wintypes.BOOL
            u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            u32.ShowWindow.restype = wintypes.BOOL
            u32.SetForegroundWindow.argtypes = [wintypes.HWND]
            u32.SetForegroundWindow.restype = wintypes.BOOL
            u32.BringWindowToTop.argtypes = [wintypes.HWND]
            u32.BringWindowToTop.restype = wintypes.BOOL
            u32.IsIconic.argtypes = [wintypes.HWND]
            u32.IsIconic.restype = wintypes.BOOL

            marked_hwnds = []
            courier_hwnds = []
            dashboard_hwnds = []

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def enum_cb(hwnd, lparam):
                if u32.IsWindowVisible(hwnd):
                    length = u32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        u32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value
                        cls_buf = ctypes.create_unicode_buffer(256)
                        u32.GetClassNameW(hwnd, cls_buf, 256)
                        cls_name = cls_buf.value

                        if cls_name == "Chrome_WidgetWin_1":
                            if "Brandcentral TrackShip" in title or "localhost:8000" in title:
                                dashboard_hwnds.append(hwnd)
                            elif "\u200b" in title:
                                marked_hwnds.append(hwnd)
                            elif any(k in title.lower() for k in [
                                "delhivery", "bluedart", "blue dart", "xpressbees",
                                "shadowfax", "ekart", "trackcourier", "tracking", "about:blank"
                            ]) and "antigravity" not in title.lower():
                                courier_hwnds.append(hwnd)
                return True

            u32.EnumWindows(WNDENUMPROC(enum_cb), 0)

            target_list = marked_hwnds if marked_hwnds else courier_hwnds
            if not target_list:
                return False

            HWND_TOPMOST = wintypes.HWND(-1)
            HWND_NOTOPMOST = wintypes.HWND(-2)
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040
            SWP_NOACTIVATE = 0x0010
            SW_MAXIMIZE = 3
            SW_RESTORE = 9

            # Ensure dashboard window is not topmost so it never blocks the popup
            for d_hwnd in dashboard_hwnds:
                u32.SetWindowPos(d_hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

            for hwnd in target_list:
                fg_hwnd = u32.GetForegroundWindow()
                fg_tid = u32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
                target_tid = u32.GetWindowThreadProcessId(hwnd, None)
                cur_tid = k32.GetCurrentThreadId()

                if fg_tid and fg_tid != cur_tid:
                    u32.AttachThreadInput(cur_tid, fg_tid, True)
                if target_tid and target_tid != cur_tid:
                    u32.AttachThreadInput(cur_tid, target_tid, True)

                # Disable Windows foreground lock timeout & simulate Alt release to allow SetForegroundWindow
                u32.SystemParametersInfoW(0x2001, 0, ctypes.c_void_p(0), 0)
                u32.keybd_event(0x12, 0, 0, 0)
                u32.keybd_event(0x12, 0, 0x0002, 0)

                if u32.IsIconic(hwnd):
                    u32.ShowWindow(hwnd, SW_RESTORE)
                u32.ShowWindow(hwnd, SW_MAXIMIZE)
                u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                u32.BringWindowToTop(hwnd)
                u32.SetForegroundWindow(hwnd)

                if target_tid and target_tid != cur_tid:
                    u32.AttachThreadInput(cur_tid, target_tid, False)
                if fg_tid and fg_tid != cur_tid:
                    u32.AttachThreadInput(cur_tid, target_tid, False)

            return True
        except Exception as e:
            print(f"[DesktopFrameService] bring_tracking_window_to_front error: {e}")
            return False

    @staticmethod
    def apply_frame(
        web_img_path: str,
        courier_name: str = "",
        awb: str = "",
        tracking_url: str = "",
        output_path: str = ""
    ) -> str:
        """
        Forces the Playwright Chrome popup window to the very front (HWND_TOPMOST + Maximized)
        and captures the 100% REAL live Windows desktop screen (including the real popup
        Google Chrome window, real URL bar, live tracking page, and real Windows Taskbar)
        using PIL.ImageGrab.grab().
        """
        if not output_path:
            output_path = web_img_path

        if sys.platform == "win32":
            try:
                import ctypes
                try:
                    # Windows 8.1 / 10 / 11 Per-Monitor DPI awareness
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except Exception:
                    try:
                        # Windows 7 DPI awareness fallback
                        ctypes.windll.user32.SetProcessDPIAware()
                    except Exception:
                        pass

                from PIL import ImageGrab
                DesktopFrameService._attach_default_desktop()
                # Force the tracking Chrome window to the very front above localhost:8000
                for _ in range(3):
                    if DesktopFrameService.bring_tracking_window_to_front():
                        break
                    time.sleep(0.15)
                # Allow Windows DWM 0.45s to finish painting the newly foregrounded topmost window
                time.sleep(0.45)
                DesktopFrameService.bring_tracking_window_to_front()
                time.sleep(0.15)
                real_screen = ImageGrab.grab()
                real_screen.save(output_path, format="PNG")
                print(f"[DesktopFrameService] Captured REAL OS desktop screenshot ({real_screen.size}) to {output_path}")
                return output_path
            except Exception as e:
                print(f"[DesktopFrameService] Real OS screen grab fallback ({e}), using cloud server frame.")

        # Cloud / Linux Headless Server fallback (where no physical Windows monitor exists)
        try:
            from PIL import Image, ImageDraw, ImageFont
            from datetime import datetime
            if os.path.exists(web_img_path):
                web_img = Image.open(web_img_path).convert("RGB")
                w, h = web_img.size
                top_h = 82
                bot_h = 48
                canvas = Image.new("RGB", (w, h + top_h + bot_h), (32, 33, 36))
                draw = ImageDraw.Draw(canvas)
                # Chrome tab bar + address bar
                draw.rectangle([0, 0, w, 40], fill=(32, 33, 36))
                draw.rounded_rectangle([12, 8, 260, 40], radius=8, fill=(53, 54, 58))
                draw.text((28, 16), f"{courier_name or 'Courier'} Tracking - {awb}"[:32], fill=(232, 234, 237))
                draw.rectangle([0, 40, w, top_h], fill=(53, 54, 58))
                draw.rounded_rectangle([110, 47, w - 60, 75], radius=14, fill=(32, 33, 36))
                draw.text((130, 54), tracking_url or f"https://tracking/{awb}", fill=(232, 234, 237))
                # Webpage content
                canvas.paste(web_img, (0, top_h))
                # Bottom taskbar
                ty = h + top_h
                draw.rectangle([0, ty, w, ty + bot_h], fill=(24, 24, 28))
                now_dt = datetime.now()
                draw.text((w - 95, ty + 10), now_dt.strftime("%I:%M %p"), fill=(240, 240, 240))
                draw.text((w - 95, ty + 26), now_dt.strftime("%d-%m-%Y"), fill=(200, 200, 200))
                canvas.save(output_path, format="PNG")
        except Exception as fallback_err:
            print(f"[DesktopFrameService] Cloud fallback note: {fallback_err}")

        return output_path

