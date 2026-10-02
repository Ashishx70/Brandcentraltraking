import os
import sys

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
        Composites a realistic Chrome browser frame (title bar + address bar + taskbar)
        directly around the Playwright screenshot (web_img_path).
        This NEVER uses ImageGrab / OS screen capture — it reads the actual Playwright
        render buffer so the result is always 100% crisp and independent of window focus.
        """
        if not output_path:
            output_path = web_img_path

        try:
            from PIL import Image, ImageDraw, ImageFont
            from datetime import datetime
            import os as _os

            if not _os.path.exists(web_img_path):
                return output_path

            web_img = Image.open(web_img_path).convert("RGB")
            w, h = web_img.size

            # ── Chrome colour palette ────────────────────────────────────────
            TAB_BG      = (32,  33,  36)   # dark chrome tab strip
            TAB_ACTIVE  = (255, 255, 255)  # white active-tab background
            ADDR_BG     = (241, 243, 244)  # address bar bg
            TEXT_DARK   = (32,  33,  36)   # tab label colour
            TEXT_URL    = (95, 99, 104)    # url text colour (grey)
            TEXT_TIME   = (240, 240, 240)
            TEXT_DATE   = (200, 200, 200)
            TASKBAR_BG  = (22,  22,  26)

            # ── Dimensions ───────────────────────────────────────────────────
            TOP_H     = 76   # chrome header height (tab bar 36px + address bar 40px)
            BOT_H     = 44   # windows taskbar height
            TAB_H     = 36
            ADDR_H    = 40

            # Pick best available Windows font, fall back to PIL default
            font_regular = None
            font_bold    = None
            font_small   = None
            for fp in [
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/tahoma.ttf",
            ]:
                if _os.path.exists(fp):
                    try:
                        font_regular = ImageFont.truetype(fp, 13)
                        font_bold    = ImageFont.truetype(fp, 13)
                        font_small   = ImageFont.truetype(fp, 11)
                    except Exception:
                        pass
                    break

            # ── Canvas ───────────────────────────────────────────────────────
            canvas = Image.new("RGB", (w, h + TOP_H + BOT_H), TAB_BG)
            draw   = ImageDraw.Draw(canvas)

            # ── Tab bar ──────────────────────────────────────────────────────
            draw.rectangle([0, 0, w, TAB_H], fill=TAB_BG)
            # Favicon circle (coloured dot simulating site icon)
            draw.ellipse([14, 10, 28, 24], fill=(66, 133, 244))
            # Active tab pill
            tab_label = f"{courier_name} Tracking – {awb}"
            tab_label = tab_label[:38] + "…" if len(tab_label) > 40 else tab_label
            draw.rounded_rectangle([8, 4, min(320, w - 8), TAB_H], radius=6, fill=TAB_ACTIVE)
            draw.text((34, 11), tab_label, fill=TEXT_DARK, font=font_regular)
            # Close button (×) inside tab
            draw.text((min(300, w - 26), 11), "×", fill=(150, 150, 150), font=font_regular)
            # New-tab (+) outside active tab
            draw.text((min(330, w - 8), 11), "+", fill=(180, 180, 180), font=font_bold)

            # ── Address bar row ───────────────────────────────────────────────
            addr_y = TAB_H
            draw.rectangle([0, addr_y, w, addr_y + ADDR_H], fill=TAB_BG)
            # Back / Forward / Refresh buttons
            for bx, sym in [(8, "‹"), (30, "›"), (54, "↺")]:
                draw.text((bx, addr_y + 11), sym, fill=(180, 180, 180), font=font_bold)
            # Address bar pill
            addr_pill_x1, addr_pill_x2 = 78, w - 110
            draw.rounded_rectangle([addr_pill_x1, addr_y + 6, addr_pill_x2, addr_y + 34], radius=14, fill=ADDR_BG)
            # Lock icon placeholder (📍→🔒)
            draw.text((addr_pill_x1 + 10, addr_y + 12), "🔒", fill=(95, 99, 104), font=font_small)
            # URL text (truncated to fit pill width)
            url_text = tracking_url or f"https://tracking.courier.in/track/{awb}"
            max_url_chars = max(10, (addr_pill_x2 - addr_pill_x1 - 36) // 7)
            url_display = url_text[:max_url_chars] + "…" if len(url_text) > max_url_chars else url_text
            draw.text((addr_pill_x1 + 32, addr_y + 12), url_display, fill=TEXT_URL, font=font_regular)
            # Right side: Extensions icon + profile + menu (dots)
            for rx, sym in [(w - 100, "⋮"), (w - 76, "☰"), (w - 48, "⊕")]:
                draw.text((rx, addr_y + 11), sym, fill=(180, 180, 180), font=font_regular)

            # ── Webpage content ───────────────────────────────────────────────
            canvas.paste(web_img, (0, TOP_H))

            # ── Windows taskbar ───────────────────────────────────────────────
            ty = h + TOP_H
            draw.rectangle([0, ty, w, ty + BOT_H], fill=TASKBAR_BG)
            # Start button
            draw.rounded_rectangle([4, ty + 6, 36, ty + BOT_H - 6], radius=4, fill=(66, 133, 244))
            draw.text((10, ty + 11), "⊞", fill=(255, 255, 255), font=font_bold)
            # Clock + date (right side)
            now_dt = datetime.now()
            draw.text((w - 88, ty + 6),  now_dt.strftime("%I:%M %p"),  fill=TEXT_TIME, font=font_regular)
            draw.text((w - 88, ty + 22), now_dt.strftime("%d-%m-%Y"), fill=TEXT_DATE, font=font_small)

            canvas.save(output_path, format="PNG")
            print(f"[DesktopFrameService] Composited crisp Chrome frame ({canvas.size}) → {output_path}")

        except Exception as frame_err:
            print(f"[DesktopFrameService] Frame composite error: {frame_err}")

        return output_path

