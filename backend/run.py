import os
import sys
import asyncio

def ensure_default_desktop():
    """
    Ensure the server runs on WinSta0\\Default so that Playwright's real Chrome window
    pops up visibly on the user's screen and PIL.ImageGrab captures the real desktop.
    """
    if sys.platform != "win32" or "--on-default-desktop" in sys.argv:
        return

    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        hd = u32.GetThreadDesktop(k32.GetCurrentThreadId())
        buf = ctypes.create_unicode_buffer(256)
        u32.GetUserObjectInformationW(hd, 2, buf, 512, None)
        desktop_name = buf.value or ""

        if desktop_name.lower() != "default":
            class STARTUPINFOW(ctypes.Structure):
                _fields_ = [
                    ('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR),
                    ('lpDesktop', wintypes.LPWSTR), ('lpTitle', wintypes.LPWSTR),
                    ('dwX', wintypes.DWORD), ('dwY', wintypes.DWORD),
                    ('dwXSize', wintypes.DWORD), ('dwYSize', wintypes.DWORD),
                    ('dwXCountChars', wintypes.DWORD), ('dwYCountChars', wintypes.DWORD),
                    ('dwFillAttribute', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                    ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD),
                    ('lpReserved2', ctypes.POINTER(wintypes.BYTE)),
                    ('hStdInput', wintypes.HANDLE), ('hStdOutput', wintypes.HANDLE),
                    ('hStdError', wintypes.HANDLE)
                ]

            class PROCESS_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE),
                    ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)
                ]

            si = STARTUPINFOW()
            si.cb = ctypes.sizeof(si)
            si.lpDesktop = "WinSta0\\Default"
            pi = PROCESS_INFORMATION()

            script_path = os.path.abspath(__file__)
            cwd_path = os.path.dirname(script_path)
            cmd = f'"{sys.executable}" -X utf8 "{script_path}" --on-default-desktop'
            CREATE_NO_WINDOW = 0x08000000

            res = k32.CreateProcessW(
                None,
                ctypes.create_unicode_buffer(cmd),
                None,
                None,
                False,
                CREATE_NO_WINDOW,
                None,
                cwd_path,
                ctypes.byref(si),
                ctypes.byref(pi)
            )
            if res:
                print(f"[run.py] Started server on interactive WinSta0\\Default desktop (PID: {pi.dwProcessId})")
                try:
                    while k32.WaitForSingleObject(pi.hProcess, 1000) == 0x00000102:  # WAIT_TIMEOUT
                        pass
                except KeyboardInterrupt:
                    k32.TerminateProcess(pi.hProcess, 0)
                sys.exit(0)
    except Exception as e:
        print(f"[run.py] Desktop switch note: {e}")

# Configure Windows event loop policy and UTF-8 stdout before importing or running uvicorn
if sys.platform == 'win32':
    ensure_default_desktop()
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host=host, port=port, reload=False)
