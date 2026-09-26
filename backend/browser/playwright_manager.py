from playwright.async_api import async_playwright, Playwright, Browser, Page
import asyncio
import sys

class PlaywrightManager:
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PlaywrightManager, cls).__new__(cls)
            cls._instance._playwright = None
            cls._instance._browser = None
        return cls._instance

    async def get_browser(self) -> Browser:
        if self._browser is None or not self._browser.is_connected():
            await self.new_page()
        return self._browser

    async def new_page(self, **kwargs) -> Page:
        async with self._lock:
            for attempt in range(2):
                try:
                    if self._browser is not None:
                        is_conn = False
                        try:
                            is_conn = self._browser.is_connected() if callable(self._browser.is_connected) else bool(self._browser.is_connected)
                        except Exception:
                            pass
                        if not is_conn:
                            try:
                                await self._browser.close()
                            except Exception:
                                pass
                            self._browser = None

                    import os
                    has_display = (sys.platform == "win32") or bool(os.environ.get("DISPLAY"))

                    if self._browser is None:
                        if self._playwright is None:
                            self._playwright = await async_playwright().start()
                        
                        launch_args = [
                            '--start-maximized',
                            '--window-position=0,0',
                            '--no-sandbox',
                            '--disable-setuid-sandbox',
                            '--disable-dev-shm-usage',
                            '--no-first-run',
                            '--disable-audio-output',
                            '--disable-default-apps',
                            '--disable-extensions',
                            '--disable-sync',
                            '--disable-translate',
                            '--disable-blink-features=AutomationControlled',
                            '--log-level=3'
                        ]
                        
                        if has_display:
                            try:
                                # Launch real installed Google Chrome on Windows 7/10/11
                                self._browser = await self._playwright.chromium.launch(
                                    channel="chrome",
                                    headless=False,
                                    ignore_default_args=["--enable-automation"],
                                    args=launch_args
                                )
                            except Exception:
                                # Fallback to bundled Chromium if Chrome is not installed
                                self._browser = await self._playwright.chromium.launch(
                                    headless=False,
                                    ignore_default_args=["--enable-automation"],
                                    args=launch_args
                                )
                        else:
                            # Headless Linux / Live Cloud Server (Render, Docker, VPS without monitor)
                            self._browser = await self._playwright.chromium.launch(
                                headless=True,
                                args=launch_args
                            )
                    
                    ctx_kwargs = dict(kwargs)
                    ctx_kwargs.pop("viewport", None)
                    if has_display:
                        # Use no_viewport=True on Windows 7/10/11 so webpage fills the real maximized browser window
                        context = await self._browser.new_context(no_viewport=True, **ctx_kwargs)
                    else:
                        # On headless Linux live servers, use full HD 1920x1080 viewport
                        context = await self._browser.new_context(viewport={"width": 1920, "height": 1080}, **ctx_kwargs)
                    page = await context.new_page()

                    # Invisible zero-width space marker in document.title so Win32 EnumWindows finds this exact Chrome window
                    title_marker_script = """
                        (() => {
                            const mark = () => {
                                if (document.title && !document.title.includes('\\u200b')) {
                                    document.title = document.title + '\\u200b';
                                } else if (!document.title) {
                                    document.title = 'Courier Tracking\\u200b';
                                }
                            };
                            mark();
                            setInterval(mark, 100);
                        })();
                    """
                    await page.add_init_script(title_marker_script)
                    try:
                        await page.evaluate(title_marker_script)
                    except Exception:
                        pass

                    # Maximize window via CDP and bring to front
                    try:
                        cdp = await context.new_cdp_session(page)
                        win = await cdp.send("Browser.getWindowForTarget")
                        await cdp.send("Browser.setWindowBounds", {
                            "windowId": win["windowId"],
                            "bounds": {"windowState": "maximized"}
                        })
                    except Exception:
                        pass

                    try:
                        await page.bring_to_front()
                    except Exception:
                        pass

                    # Force OS window to TOPMOST + Foreground above localhost:8000
                    try:
                        from services.desktop_frame_service import DesktopFrameService
                        DesktopFrameService.bring_tracking_window_to_front()
                    except Exception:
                        pass

                    await page.evaluate("() => 1")
                    return page
                except Exception as e:
                    print(f"PlaywrightManager new_page exception (attempt {attempt+1}): {e}")
                    if attempt == 0:
                        try:
                            if self._browser:
                                await self._browser.close()
                        except Exception:
                            pass
                        self._browser = None
                        try:
                            if self._playwright:
                                await self._playwright.stop()
                        except Exception:
                            pass
                        self._playwright = None
                    else:
                        raise e

    async def close_browser(self):
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

# Global instance helper
playwright_manager = PlaywrightManager()
