#!/usr/bin/env python3
"""desktop-control: let a text-only LLM agent see and drive the user's desktop.

Every subcommand prints ONE JSON object to stdout. On failure the exit code is 1
and the JSON is {"ok": false, "error": "..."}; some errors carry a "hint".

Optional packages are imported lazily inside each subcommand so that `windows`,
`focus`, `open`, `wait` and `clipboard` keep working when the GUI packages are
missing.  Packages: pyautogui, pywinauto (Windows), mss, pyperclip, pillow,
rapidocr-onnxruntime (for --ocr), pandas (for paste-table).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import time

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WIN and not IS_MAC

ACTION_PAUSE = 0.25  # seconds between pyautogui actions
DEFAULT_SHOT_DIR = "desktop_control"


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
class ControlError(Exception):
    def __init__(self, message: str, hint: str | None = None, **extra):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.extra = extra


def emit(payload: dict) -> None:
    payload.setdefault("ok", True)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def fail(message: str, hint: str | None = None, **extra) -> None:
    payload = {"ok": False, "error": message}
    if hint:
        payload["hint"] = hint
    payload.update(extra)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()
    sys.exit(1)


def _set_dpi_aware() -> None:
    """Make this process DPI aware so every coordinate we report/use is a physical pixel."""
    if not IS_WIN:
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v1
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _need(module: str, pip_name: str | None = None):
    """Import an optional module or raise a ControlError with an install hint."""
    try:
        return __import__(module)
    except ImportError as exc:  # pragma: no cover
        pip_name = pip_name or module
        raise ControlError(
            f"Python package '{module}' is not installed ({exc})",
            hint=f"Run: uv pip install {pip_name}   (or install the BioDSH env pack '电脑控制')",
        )


def _pyautogui():
    pg = _need("pyautogui")
    pg.FAILSAFE = True  # slam the mouse into a screen corner to abort
    pg.PAUSE = ACTION_PAUSE
    return pg


def _mod_key() -> str:
    return "command" if IS_MAC else "ctrl"


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _rect_center(rect) -> tuple[int, int]:
    l, t, r, b = rect
    return int((l + r) / 2), int((t + b) / 2)


# ----------------------------------------------------------------------------
# window enumeration (per platform)
# ----------------------------------------------------------------------------
def _win_list_windows() -> list[dict]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    try:
        dwmapi = ctypes.windll.dwmapi
    except Exception:
        dwmapi = None

    fg = user32.GetForegroundWindow()
    result: list[dict] = []

    def proc_name(pid: int) -> str:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
            return ""
        finally:
            kernel32.CloseHandle(h)

    def is_cloaked(hwnd) -> bool:
        if dwmapi is None:
            return False
        cloaked = ctypes.c_int(0)
        DWMWA_CLOAKED = 14
        try:
            dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        except Exception:
            return False
        return cloaked.value != 0

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title or is_cloaked(hwnd):
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        result.append(
            {
                "hwnd": int(hwnd),
                "title": title,
                "pid": int(pid.value),
                "process": proc_name(pid.value),
                "rect": [rect.left, rect.top, rect.right, rect.bottom],
                "minimized": bool(user32.IsIconic(hwnd)),
                "foreground": int(hwnd) == int(fg),
            }
        )
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return result


def _mac_list_windows() -> list[dict]:
    script = r'''
set AppleScript's text item delimiters to ","
set out to ""
tell application "System Events"
    set fgName to name of first process whose frontmost is true
    repeat with p in (every process whose visible is true)
        set pname to name of p
        set upid to unix id of p
        try
            repeat with w in (every window of p)
                set pos to position of w
                set sz to size of w
                set out to out & upid & tab & pname & tab & (name of w) & tab & (pos as text) & tab & (sz as text) & tab & (pname is fgName) & linefeed
            end repeat
        end try
    end repeat
end tell
return out
'''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ControlError(
            "osascript failed: " + proc.stderr.strip(),
            hint="Grant Accessibility permission to the terminal/BioDSH in System Settings > Privacy & Security > Accessibility.",
        )
    rows = []
    for i, line in enumerate(proc.stdout.splitlines()):
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        pid, pname, title, pos, size, is_fg = parts[:6]
        try:
            x, y = [int(float(v)) for v in pos.split(",")]
            w, h = [int(float(v)) for v in size.split(",")]
        except ValueError:
            x = y = w = h = 0
        rows.append(
            {
                "hwnd": i,
                "title": title.strip(),
                "pid": int(pid) if pid.isdigit() else None,
                "process": pname,
                "rect": [x, y, x + w, y + h],
                "minimized": False,
                "foreground": is_fg.strip() == "true",
            }
        )
    return rows


def _linux_list_windows() -> list[dict]:
    if not shutil.which("wmctrl"):
        raise ControlError("wmctrl is not installed", hint="sudo apt install wmctrl (X11 only)")
    proc = subprocess.run(["wmctrl", "-lpG"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ControlError("wmctrl failed: " + proc.stderr.strip())
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        wid, _desk, pid, x, y, w, h, _host, title = parts
        pname = ""
        try:
            with open(f"/proc/{pid}/comm") as fh:
                pname = fh.read().strip()
        except OSError:
            pass
        rows.append(
            {
                "hwnd": int(wid, 16),
                "title": title.strip(),
                "pid": int(pid),
                "process": pname,
                "rect": [int(x), int(y), int(x) + int(w), int(y) + int(h)],
                "minimized": False,
                "foreground": False,
            }
        )
    return rows


def list_windows() -> list[dict]:
    if IS_WIN:
        return _win_list_windows()
    if IS_MAC:
        return _mac_list_windows()
    return _linux_list_windows()


def find_window(substring: str) -> dict:
    """Return the window whose title contains `substring` (case-insensitive).

    Ranking: exact title, then title starting with the substring, then the
    foreground window, then non-minimized windows.  `other_matches` lists the
    remaining candidate titles so the agent can disambiguate.
    """
    needle = substring.lower()
    if needle.startswith("process:"):  # 按进程名选窗口：多个程序标题同名时（例如项目名）用它消歧
        pname = needle[len("process:"):].strip()
        matches = [w for w in list_windows() if (w.get("process") or "").lower() == pname or (w.get("process") or "").lower() == pname + ".exe"]
    else:
        matches = [w for w in list_windows() if needle in w["title"].lower()]
    if not matches:
        raise ControlError(
            f"no visible window whose title contains {substring!r}",
            hint="Run `windows` to list titles; the app may still be starting - try `wait 2` and retry.",
        )
    matches.sort(
        key=lambda w: (
            w["title"].lower() != needle,  # exact title first
            not w["title"].lower().startswith(needle),  # then titles that start with it
            not w["foreground"],
            w["minimized"],
        )
    )
    best = dict(matches[0])
    best["other_matches"] = [w["title"] for w in matches[1:6]]
    return best


def foreground_window() -> dict | None:
    for w in list_windows():
        if w.get("foreground"):
            return w
    return None


# ----------------------------------------------------------------------------
# focus
# ----------------------------------------------------------------------------
def _win_focus(win: dict) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = win["hwnd"]
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # Windows refuses SetForegroundWindow from a background process unless the
    # process recently received input; a harmless ALT tap satisfies that rule.
    KEYEVENTF_KEYUP = 0x0002
    VK_MENU = 0x12
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    if user32.GetForegroundWindow() != hwnd:
        try:
            from pywinauto import Desktop

            Desktop(backend="win32").window(handle=hwnd).set_focus()
            time.sleep(0.2)
        except Exception:
            pass
    if user32.GetForegroundWindow() != hwnd:
        raise ControlError(
            f"could not bring window {win['title']!r} to the foreground",
            hint="A modal dialog or UAC prompt may be blocking; inspect `windows` and close it, or click the window once.",
        )


def focus_window(win: dict) -> None:
    if IS_WIN:
        _win_focus(win)
    elif IS_MAC:
        script = (
            'tell application "System Events"\n'
            f'  set p to first process whose unix id is {win["pid"]}\n'
            "  set frontmost of p to true\n"
            "end tell"
        )
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if proc.returncode != 0:
            raise ControlError("osascript focus failed: " + proc.stderr.strip())
    else:
        subprocess.run(["wmctrl", "-i", "-a", hex(win["hwnd"])], check=False)


# ----------------------------------------------------------------------------
# UI Automation inspection (Windows)
# ----------------------------------------------------------------------------
UNSUPPORTED_INSPECT = {
    "unsupported": True,
    "reason": "UI Automation inspection is only available on Windows (pywinauto uia backend)",
    "hint": "Use `screenshot --ocr` (optionally with --window) to read the screen as text with coordinates.",
}


def _uia_root(win: dict):
    pywinauto = _need("pywinauto")
    return pywinauto.Desktop(backend="uia").window(handle=win["hwnd"])


def _control_record(info, depth: int, index: int, with_value: bool = True) -> dict:
    rect = info.rectangle
    r = [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)]
    cx, cy = _rect_center(r)
    rec = {
        "i": index,
        "depth": depth,
        "name": info.name or "",
        "control_type": info.control_type or "",
        "auto_id": info.automation_id or "",
        "class_name": info.class_name or "",
        "x": cx,
        "y": cy,
        "rect": r,
        "enabled": bool(info.enabled),
        "visible": bool(info.visible),
    }
    if with_value and rec["control_type"] in ("Edit", "ComboBox", "Document", "Spinner"):
        try:
            from pywinauto.controls.uiawrapper import UIAWrapper

            iface = UIAWrapper(info).iface_value
            if iface is not None:
                val = iface.CurrentValue
                if val:
                    rec["value"] = str(val)[:200]
        except Exception:
            pass
    return rec


def inspect_window(win: dict, depth: int, max_controls: int, include_all: bool, name_filter: str | None) -> dict:
    root = _uia_root(win)
    root_info = root.element_info
    controls: list[dict] = []
    visited = 0
    visit_cap = max(max_controls * 20, 2000)
    truncated = False
    needle = name_filter.lower() if name_filter else None

    def keep(rec: dict) -> bool:
        if needle and needle not in rec["name"].lower() and needle not in rec["auto_id"].lower():
            return False
        if include_all:
            return True
        if not rec["visible"]:
            return False
        return bool(rec["name"] or rec["auto_id"])

    def walk(info, level: int) -> None:
        nonlocal visited, truncated
        if truncated or level > depth:
            return
        try:
            children = info.children()
        except Exception:
            return
        for child in children:
            visited += 1
            if len(controls) >= max_controls or visited >= visit_cap:
                truncated = True
                return
            try:
                rec = _control_record(child, level, len(controls))
            except Exception:
                continue
            if keep(rec):
                controls.append(rec)
            walk(child, level + 1)

    walk(root_info, 1)
    out = {
        "window": {
            "title": win["title"],
            "hwnd": win["hwnd"],
            "pid": win["pid"],
            "process": win.get("process", ""),
            "rect": win["rect"],
            "minimized": win.get("minimized", False),
            "other_matches": win.get("other_matches", []),
        },
        "count": len(controls),
        "truncated": truncated,
        "depth": depth,
        "controls": controls,
    }
    if win.get("minimized"):
        out["hint"] = "window is minimized, so coordinates are off-screen; run `focus --window ...` then inspect again before clicking"
    return out


def uia_find_text(win: dict, text: str, limit: int = 20) -> list[dict]:
    root = _uia_root(win)
    needle = text.lower()
    hits: list[dict] = []
    try:
        infos = root.element_info.descendants()
    except Exception as exc:
        raise ControlError(f"UIA descendants failed: {exc}")
    for idx, info in enumerate(infos):
        name = info.name or ""
        if not name or needle not in name.lower():
            continue
        rec = _control_record(info, -1, idx, with_value=False)
        if not rec["visible"]:
            continue
        rec["exact"] = name.strip().lower() == needle
        hits.append(rec)
        if len(hits) >= limit:
            break
    hits.sort(key=lambda h: (not h["exact"], h["y"], h["x"]))
    return hits


# ----------------------------------------------------------------------------
# screenshots and OCR
# ----------------------------------------------------------------------------
def take_screenshot(out: str | None, region: list[int] | None) -> dict:
    mss = _need("mss")
    import mss.tools  # noqa: F401

    if out is None:
        os.makedirs(DEFAULT_SHOT_DIR, exist_ok=True)
        out = os.path.join(DEFAULT_SHOT_DIR, f"screen-{_timestamp()}.png")
    else:
        parent = os.path.dirname(os.path.abspath(out))
        os.makedirs(parent, exist_ok=True)
    with mss.mss() as sct:
        if region:
            x, y, w, h = region
            mon = {"left": x, "top": y, "width": w, "height": h}
            offset = (x, y)
        else:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            offset = (mon["left"], mon["top"])
        shot = sct.grab(mon)
        mss.tools.to_png(shot.rgb, shot.size, output=out)
    return {"path": os.path.abspath(out), "width": shot.size.width, "height": shot.size.height, "offset": list(offset)}


def run_ocr(png_path: str, offset=(0, 0), min_score: float = 0.5) -> list[dict]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise ControlError(
            "rapidocr_onnxruntime is not installed",
            hint="Run: uv pip install rapidocr-onnxruntime   (or install the BioDSH env pack '电脑控制')",
        )
    engine = RapidOCR()
    result, _elapse = engine(png_path)
    lines: list[dict] = []
    ox, oy = offset
    for item in result or []:
        box, text, score = item[0], item[1], float(item[2])
        if score < min_score or not str(text).strip():
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        l, t, r, b = int(min(xs)) + ox, int(min(ys)) + oy, int(max(xs)) + ox, int(max(ys)) + oy
        cx, cy = _rect_center((l, t, r, b))
        lines.append({"text": str(text), "x": cx, "y": cy, "rect": [l, t, r, b], "score": round(score, 3)})
    lines.sort(key=lambda d: (round(d["y"] / 12), d["x"]))
    return lines


def _window_region(win: dict) -> list[int]:
    # 副屏可能在负坐标（左边/上面）；mss 支持负 left/top，不能把它裁成 0，否则副屏上的窗口截不全
    l, t, r, b = win["rect"]
    return [l, t, max(r - l, 1), max(b - t, 1)]


def _primary_bounds() -> tuple[int, int]:
    import ctypes
    u = ctypes.windll.user32
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def bring_to_primary(win: dict) -> bool:
    """窗口大部分在主屏之外（副屏）就挪到主屏：模型"看"的是主屏，副屏上的窗口它对不准坐标。"""
    if not IS_WIN:
        return False
    import ctypes
    l, t, r, b = win["rect"]
    if l <= -30000 or t <= -30000 or win.get("minimized"):  # 最小化窗口的坐标是 -32000，交给 focus 还原，不要挪
        return False
    sw, sh = _primary_bounds()
    cx, cy = (l + r) // 2, (t + b) // 2
    if 0 <= cx < sw and 0 <= cy < sh and l >= -8 and t >= -8:
        return False
    w, h = min(r - l, sw - 80), min(b - t, sh - 80)
    u = ctypes.windll.user32
    if u.IsZoomed(win["hwnd"]):
        u.ShowWindow(win["hwnd"], 9)  # SW_RESTORE，先取消最大化才能挪
    u.SetWindowPos(win["hwnd"], 0, 40, 40, max(w, 400), max(h, 300), 0x0004 | 0x0010)  # SWP_NOZORDER | SWP_NOACTIVATE
    time.sleep(0.2)
    win["rect"] = [40, 40, 40 + max(w, 400), 40 + max(h, 300)]
    win["moved_to_primary"] = True
    return True


def ocr_screen(region: list[int] | None, keep_png: bool = False) -> tuple[list[dict], str]:
    shot = take_screenshot(None, region)
    try:
        lines = run_ocr(shot["path"], offset=tuple(shot["offset"]))
    finally:
        if not keep_png:
            try:
                os.remove(shot["path"])
            except OSError:
                pass
    return lines, shot["path"]


def find_text(text: str, ocr_only: bool, window_sub: str | None) -> dict:
    needle = text.lower()
    win = None
    if window_sub:
        win = find_window(window_sub)
    else:
        try:
            win = foreground_window()
        except ControlError:
            win = None

    payload: dict = {"query": text, "window": win["title"] if win else None, "matches": [], "method": None}

    if IS_WIN and not ocr_only and win is not None:
        try:
            hits = uia_find_text(win, text)
        except ControlError:
            hits = []
        if hits:
            payload["method"] = "uia"
            payload["matches"] = hits
            payload["best"] = {"x": hits[0]["x"], "y": hits[0]["y"], "name": hits[0]["name"], "control_type": hits[0]["control_type"]}
            return payload

    region = _window_region(win) if win and not win.get("minimized") else None
    lines, _ = ocr_screen(region)
    hits = []
    for ln in lines:
        if needle in ln["text"].lower():
            ln = dict(ln)
            ln["exact"] = ln["text"].strip().lower() == needle
            hits.append(ln)
    hits.sort(key=lambda h: (not h["exact"], h["y"], h["x"]))
    payload["method"] = "ocr"
    payload["matches"] = hits
    if hits:
        payload["best"] = {"x": hits[0]["x"], "y": hits[0]["y"], "text": hits[0]["text"]}
    else:
        raise ControlError(
            f"text {text!r} not found on screen" + (f" in window {win['title']!r}" if win else ""),
            hint="Run `inspect --window ...` or `screenshot --ocr` to see what is actually visible; check spelling/case and that the right window is focused.",
            **payload,
        )
    return payload


# ----------------------------------------------------------------------------
# clipboard / open
# ----------------------------------------------------------------------------
def clipboard_get() -> str:
    pyperclip = _need("pyperclip")
    return pyperclip.paste()


def clipboard_set(text: str) -> None:
    pyperclip = _need("pyperclip")
    pyperclip.copy(text)


WIN_ALIASES = {
    "excel": ["excel.exe", r"%ProgramFiles%\Microsoft Office\root\Office16\EXCEL.EXE", r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\EXCEL.EXE", r"%ProgramFiles%\Microsoft Office\Office16\EXCEL.EXE"],
    "word": ["winword.exe", r"%ProgramFiles%\Microsoft Office\root\Office16\WINWORD.EXE", r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\WINWORD.EXE"],
    "powerpoint": ["powerpnt.exe", r"%ProgramFiles%\Microsoft Office\root\Office16\POWERPNT.EXE", r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\POWERPNT.EXE"],
    "ppt": ["powerpnt.exe"],
    "notepad": ["notepad.exe"],
    "calc": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "zotero": ["zotero.exe", r"%LOCALAPPDATA%\Zotero\zotero.exe", r"%ProgramFiles%\Zotero\zotero.exe", r"%ProgramFiles(x86)%\Zotero\zotero.exe"],
    "prism": ["prism.exe", r"%ProgramFiles%\GraphPad\Prism *\prism.exe", r"%ProgramFiles(x86)%\GraphPad\Prism *\prism.exe"],
    "graphpad": ["prism.exe", r"%ProgramFiles%\GraphPad\Prism *\prism.exe", r"%ProgramFiles(x86)%\GraphPad\Prism *\prism.exe"],
    "spss": ["stats.exe", r"%ProgramFiles%\IBM\SPSS Statistics\*\stats.exe", r"%ProgramFiles%\IBM\SPSS\Statistics\*\stats.exe"],
    "chrome": ["chrome.exe", r"%ProgramFiles%\Google\Chrome\Application\chrome.exe", r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"],
    "edge": ["msedge.exe", r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe", r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"],
    "wps": ["wps.exe", r"%LOCALAPPDATA%\Kingsoft\WPS Office\ksolaunch.exe"],
    "rstudio": ["rstudio.exe", r"%ProgramFiles%\RStudio\rstudio.exe", r"%ProgramFiles%\RStudio\bin\rstudio.exe"],
    "code": ["code.exe", r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"],
    "vscode": ["code.exe", r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"],
}

MAC_ALIASES = {
    "excel": "Microsoft Excel",
    "word": "Microsoft Word",
    "powerpoint": "Microsoft PowerPoint",
    "ppt": "Microsoft PowerPoint",
    "notepad": "TextEdit",
    "textedit": "TextEdit",
    "zotero": "Zotero",
    "prism": "Prism",
    "graphpad": "Prism",
    "spss": "SPSS Statistics",
    "chrome": "Google Chrome",
    "safari": "Safari",
    "finder": "Finder",
    "rstudio": "RStudio",
    "code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
}

LINUX_ALIASES = {
    "excel": ["libreoffice", "--calc"],
    "word": ["libreoffice", "--writer"],
    "powerpoint": ["libreoffice", "--impress"],
    "notepad": ["gedit"],
    "zotero": ["zotero"],
    "chrome": ["google-chrome"],
    "rstudio": ["rstudio"],
    "code": ["code"],
}


def _win_app_paths(exe: str) -> str | None:
    try:
        import winreg
    except ImportError:
        return None
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}")
            val, _ = winreg.QueryValueEx(key, None)
            val = os.path.expandvars(val.strip('"'))
            if os.path.exists(val):
                return val
        except OSError:
            continue
    return None


def _win_resolve_alias(name: str) -> str | None:
    key = name.lower().strip()
    if key not in WIN_ALIASES:
        return None
    for cand in WIN_ALIASES[key]:
        cand = os.path.expandvars(cand)
        if "*" in cand:
            hits = sorted(glob.glob(cand), reverse=True)
            if hits:
                return hits[0]
        elif os.sep in cand or "/" in cand:
            if os.path.exists(cand):
                return cand
        else:
            found = shutil.which(cand) or _win_app_paths(cand)
            if found:
                return found
    return None


def open_target(target: str, args: list[str]) -> dict:
    is_url = target.lower().startswith(("http://", "https://", "file://", "mailto:"))
    exists = os.path.exists(target)
    if IS_WIN:
        # BioDSH runs this script inside dsh's write-restricted sandbox, and the sandbox also
        # terminates descendants when the tool call ends. A GUI app started directly from here
        # would inherit the restricted token (Excel then reports "内存或磁盘空间不足" on save)
        # and die a few seconds later. Handing the launch to the already-running Explorer shell
        # (`explorer.exe <target>`) starts the app with the user's normal token, outside the
        # sandbox's process tree, so it behaves exactly as if the user had double-clicked it.
        def _via_explorer(what: str) -> dict:
            subprocess.Popen(["explorer.exe", what], close_fds=True)
            return {"opened": what, "method": "explorer", "note": "launched by the Windows shell (outside the sandbox); allow 3-10 s before looking for its window"}

        if exists or is_url:
            if not args:
                return _via_explorer(os.path.abspath(target) if exists else target)
            subprocess.Popen([target, *args], close_fds=True)
            return {"opened": target, "method": "popen", "warning": "started inside the sandbox because arguments were given; it may be write-restricted"}
        resolved = _win_resolve_alias(target)
        found = resolved or shutil.which(target) or _win_app_paths(target if target.lower().endswith(".exe") else target + ".exe")
        if found:
            if not args:
                return _via_explorer(found)
            subprocess.Popen([found, *args], close_fds=True)
            return {"opened": found, "method": "popen", "warning": "started inside the sandbox because arguments were given; it may be write-restricted"}
        cmd = f'start "" "{target}"' + ("".join(f' "{a}"' for a in args))
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ControlError(
                f"could not open {target!r}: {proc.stderr.strip() or 'start failed'}",
                hint="Give a full .exe path, a file path, a URL, or one of the aliases: " + ", ".join(sorted(WIN_ALIASES)),
            )
        return {"opened": target, "method": "start"}
    if IS_MAC:
        if exists or is_url:
            cmd = ["open", target, *args]
        else:
            app = MAC_ALIASES.get(target.lower().strip(), target)
            cmd = ["open", "-a", app, *args]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ControlError(f"open failed: {proc.stderr.strip()}", hint="Aliases: " + ", ".join(sorted(MAC_ALIASES)))
        return {"opened": cmd[-1] if not args else cmd[1], "method": "open"}
    # linux
    if exists or is_url:
        subprocess.Popen(["xdg-open", target])
        return {"opened": target, "method": "xdg-open"}
    cmd = LINUX_ALIASES.get(target.lower().strip(), [target])
    if not shutil.which(cmd[0]):
        raise ControlError(f"executable {cmd[0]!r} not found on PATH")
    subprocess.Popen([*cmd, *args])
    return {"opened": cmd[0], "method": "exec"}


# ----------------------------------------------------------------------------
# subcommand handlers
# ----------------------------------------------------------------------------
def cmd_info(_a) -> dict:
    pkgs = {}
    for mod, pip in (("pyautogui", "pyautogui"), ("pywinauto", "pywinauto"), ("mss", "mss"), ("pyperclip", "pyperclip"), ("PIL", "pillow"), ("rapidocr_onnxruntime", "rapidocr-onnxruntime"), ("pandas", "pandas")):
        try:
            __import__(mod)
            pkgs[pip] = True
        except Exception:
            pkgs[pip] = False
    out: dict = {"platform": platform.system(), "python": platform.python_version(), "packages": pkgs, "cwd": os.getcwd()}
    try:
        pg = _pyautogui()
        w, h = pg.size()
        mx, my = pg.position()
        out["screen"] = {"width": int(w), "height": int(h)}
        out["mouse"] = {"x": int(mx), "y": int(my)}
    except ControlError as exc:
        out["screen_error"] = exc.message
    out["inspect_supported"] = IS_WIN
    return out


def cmd_windows(a) -> dict:
    wins = list_windows()
    if a.filter:
        needle = a.filter.lower()
        wins = [w for w in wins if needle in w["title"].lower() or needle in (w.get("process") or "").lower()]
    return {"count": len(wins), "windows": wins}


def _foreground_title() -> str:
    if not IS_WIN:
        return ""
    try:
        import ctypes
        h = ctypes.windll.user32.GetForegroundWindow()
        n = ctypes.windll.user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        ctypes.windll.user32.GetWindowTextW(h, buf, n + 1)
        return buf.value
    except Exception:
        return ""


def _ensure_front(a) -> dict | None:
    """动作前把目标窗口带到最前（--window）；没带 --window 就把当前前台窗口名一起返回，模型能看出点到了谁。"""
    sub = getattr(a, "window", None)
    if not sub:
        return {"foreground": _foreground_title(), "warning": "no --window given: the action goes to whatever window is in front"}
    win = find_window(sub)
    focus_window(win)
    bring_to_primary(win)
    time.sleep(0.25)
    if IS_WIN:
        import ctypes
        if ctypes.windll.user32.GetForegroundWindow() != win.get("hwnd"):
            focus_window(win); time.sleep(0.4)
            if ctypes.windll.user32.GetForegroundWindow() != win.get("hwnd"):
                raise ControlError(f"could not bring window {win.get('title')!r} to the front (foreground is {_foreground_title()!r}); a dialog or another topmost window may be blocking it", hint="close the blocking dialog first (inspect/screenshot it), or use `focus` and retry")
    return {"foreground": win.get("title")}


def cmd_focus(a) -> dict:
    win = find_window(a.window)
    focus_window(win)
    moved = bring_to_primary(win)
    return {"focused": win, "moved_to_primary": moved}


def cmd_inspect(a) -> dict:
    if not IS_WIN:
        return dict(UNSUPPORTED_INSPECT)
    win = find_window(a.window)
    return inspect_window(win, depth=a.depth, max_controls=a.max, include_all=a.all, name_filter=a.name)


def cmd_screenshot(a) -> dict:
    region = a.region
    if a.window:
        region = _window_region(find_window(a.window))
    shot = take_screenshot(a.out, region)
    out = {"screenshot": shot["path"], "width": shot["width"], "height": shot["height"], "offset": shot["offset"]}
    if a.ocr:
        lines = run_ocr(shot["path"], offset=tuple(shot["offset"]))
        out["ocr"] = lines
        out["ocr_count"] = len(lines)
    return out


def cmd_find_text(a) -> dict:
    return find_text(a.text, ocr_only=a.ocr, window_sub=a.window)




# ---------------------------------------------------------------------------
# 让用户看得见：平滑移动 + 控制指示层（overlay.py）
# ---------------------------------------------------------------------------
# 状态文件放在工作区（cwd）下：dsh 沙盒里的进程只能写工作区，而指示层在沙盒外运行，两边都要能读写同一处。
# （之前放在 %TEMP%：沙盒把 TEMP 重定向到私有目录，指示层永远收不到心跳、也无法拉起。）
STATE_DIR = os.environ.get("BIODSH_CONTROL_STATE") or os.path.join(os.getcwd(), ".biodsh_control")
HEARTBEAT = os.path.join(STATE_DIR, "heartbeat")
OVERLAY_LOCK = os.path.join(STATE_DIR, "overlay.pid")


def _overlay_alive() -> bool:
    try:
        pid = int(open(OVERLAY_LOCK).read().strip())
    except Exception:
        return False
    if IS_WIN:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _touch_heartbeat() -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(HEARTBEAT, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def ensure_overlay() -> None:
    """每个会动鼠标/键盘的命令都先调用：拉起（或续命）指示层。BIODSH_NO_OVERLAY=1 可关闭。"""
    if os.environ.get("BIODSH_NO_OVERLAY"):
        return
    _touch_heartbeat()
    if _overlay_alive():
        return
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlay.py")
    if not os.path.exists(script):
        return
    # 刚刚已经在拉起（tkinter 还没来得及写 pid 锁）就不要再拉一个
    starting = OVERLAY_LOCK + ".starting"
    try:
        if time.time() - os.path.getmtime(starting) < 4.0:
            return
    except OSError:
        pass
    try:
        with open(starting, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass
    kw: dict = {"close_fds": True, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if IS_WIN:
        # dsh 的沙盒会在工具调用结束时清掉派生进程——直接 spawn 的指示层活不过一次调用。
        # 所以写一个 .vbs（无窗口地启动 pythonw overlay.py），再交给资源管理器在沙盒外执行（和 open 一样的原理）。
        exe = sys.executable
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        launcher = os.path.join(STATE_DIR, "overlay.vbs")  # 技能目录在沙盒里不可写，启动器也放工作区
        vbs = 'CreateObject("WScript.Shell").Run """%s"" ""%s"" ""%s""", 0, False\r\n' % (pyw if os.path.exists(pyw) else exe, script, STATE_DIR)
        try:
            cur = open(launcher, encoding="utf-8").read() if os.path.exists(launcher) else ""
            if cur != vbs:
                with open(launcher, "w", encoding="utf-8") as f:
                    f.write(vbs)
        except OSError:
            pass
        subprocess.Popen(["explorer.exe", launcher], **kw)
    else:
        kw["start_new_session"] = True
        subprocess.Popen([sys.executable, script], **kw)
    time.sleep(0.8)


def glide(pg, x: int, y: int) -> None:
    """平滑移动到目标：时长随距离 0.25–0.9 s，缓入缓出，让人看得清鼠标去了哪。"""
    try:
        cx, cy = pg.position()
    except Exception:
        cx, cy = x, y
    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    dur = min(0.9, max(0.25, dist / 1400.0))
    pg.moveTo(x, y, duration=dur, tween=getattr(pg, "easeInOutQuad", None) or (lambda t: t))
    time.sleep(0.08)

def cmd_click(a) -> dict:
    ensure_overlay()
    front = _ensure_front(a)
    pg = _pyautogui()
    clicks = 2 if a.double else 1
    glide(pg, a.x, a.y)
    pg.click(clicks=clicks, button=a.button)
    return {"clicked": {"x": a.x, "y": a.y}, "button": a.button, "double": a.double, **(front or {})}


def cmd_click_text(a) -> dict:
    found = find_text(a.text, ocr_only=a.ocr, window_sub=a.window)
    best = found["best"]
    ensure_overlay()
    front = _ensure_front(a)
    pg = _pyautogui()
    clicks = 2 if a.double else 1
    glide(pg, best["x"], best["y"])
    pg.click(clicks=clicks, button=a.button)
    return {"clicked": {"x": best["x"], "y": best["y"]}, "method": found["method"], "target": best, "button": a.button, "double": a.double, **(front or {})}


def cmd_move(a) -> dict:
    ensure_overlay()
    front = _ensure_front(a)
    pg = _pyautogui()
    glide(pg, a.x, a.y)
    return {"mouse": {"x": a.x, "y": a.y}, **(front or {})}


def cmd_scroll(a) -> dict:
    ensure_overlay()
    front = _ensure_front(a)
    pg = _pyautogui()
    kwargs = {}
    if a.x is not None and a.y is not None:
        kwargs = {"x": a.x, "y": a.y}
    pg.scroll(a.amount, **kwargs)
    return {"scrolled": a.amount, **kwargs, **(front or {})}


def _type_text(text: str) -> str:
    pg = _pyautogui()
    if text.isascii():
        pg.write(text, interval=0.01)
        return "keyboard"
    clipboard_set(text)
    time.sleep(0.1)
    pg.hotkey(_mod_key(), "v")
    time.sleep(0.2)
    return "clipboard"


def cmd_type(a) -> dict:
    ensure_overlay()
    front = _ensure_front(a)
    text = a.text
    method = _type_text(text)
    if a.enter:
        _pyautogui().press("enter")
    return {"typed_chars": len(text), "method": method, "enter": a.enter, **(front or {})}


def _normalize_keys(keys: list[str]) -> list[str]:
    if len(keys) == 1 and "+" in keys[0] and keys[0] != "+":
        keys = keys[0].split("+")
    mapping = {"cmd": "command", "win": "winleft", "super": "winleft", "control": "ctrl", "return": "enter", "escape": "esc", "opt": "option"}
    return [mapping.get(k.lower(), k.lower()) for k in keys if k]



# pyautogui's SendInput modifier combos are ignored by some apps (Excel dropped Ctrl+V / Ctrl+N in the
# BioDSH sandbox while plain characters arrived). pywinauto's keyboard.send_keys goes through the same
# Win32 path the user's keyboard uses and worked reliably, so on Windows hotkeys prefer it.
_WIN_NAMED = {"enter": "{ENTER}", "return": "{ENTER}", "tab": "{TAB}", "esc": "{ESC}", "escape": "{ESC}", "space": "{SPACE}",
    "backspace": "{BACKSPACE}", "delete": "{DELETE}", "del": "{DELETE}", "insert": "{INSERT}", "home": "{HOME}", "end": "{END}",
    "pageup": "{PGUP}", "pagedown": "{PGDN}", "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
    "capslock": "{CAPSLOCK}", "numlock": "{NUMLOCK}", "printscreen": "{PRTSC}", "scrolllock": "{SCROLLLOCK}", "pause": "{BREAK}",
    **{f"f{i}": f"{{F{i}}}" for i in range(1, 25)}}
_WIN_MODS = {"ctrl": "^", "control": "^", "alt": "%", "shift": "+"}

def _win_send_keys(keys: list[str], presses: int = 1) -> bool:
    """Send a key combo via pywinauto (Windows only). Returns False when unavailable so callers fall back."""
    if not IS_WIN:
        return False
    try:
        from pywinauto import keyboard  # type: ignore
    except Exception:
        return False
    mods = "".join(_WIN_MODS[k] for k in keys if k in _WIN_MODS)
    rest = [k for k in keys if k not in _WIN_MODS]
    if any(k in ("win", "winleft", "winright", "command", "cmd") for k in keys):
        return False  # no Win-key support in send_keys; let pyautogui handle it
    tokens = []
    for k in rest:
        if k in _WIN_NAMED:
            tokens.append(_WIN_NAMED[k])
        elif len(k) == 1:
            tokens.append("{" + k + "}" if k in "+^%~(){}[]" else k)
        else:
            return False
    body = "".join(tokens)
    seq = mods + ("(" + body + ")" if mods and len(tokens) > 1 else body)
    for _ in range(max(1, presses)):
        keyboard.send_keys(seq, pause=0.02, with_spaces=True, with_tabs=True, with_newlines=True)
        time.sleep(0.05)
    return True

def cmd_hotkey(a) -> dict:
    ensure_overlay()
    front = _ensure_front(a)
    keys = _normalize_keys(a.keys)
    if _win_send_keys(keys):
        return {"hotkey": keys, "method": "pywinauto", **(front or {})}
    pg = _pyautogui()
    pg.hotkey(*keys)
    return {"hotkey": keys, "method": "pyautogui", **(front or {})}


def cmd_press(a) -> dict:
    ensure_overlay()
    front = _ensure_front(a)
    keys = _normalize_keys([a.key])
    if _win_send_keys(keys, presses=a.times):
        return {"pressed": keys[0], "times": a.times, "method": "pywinauto", **(front or {})}
    pg = _pyautogui()
    pg.press(keys[0], presses=a.times, interval=0.05)
    return {"pressed": keys[0], "times": a.times, "method": "pyautogui", **(front or {})}


def cmd_open(a) -> dict:
    return open_target(a.target, a.args)


def cmd_batch(a) -> dict:
    """一次调用执行多步（减少模型往返）：batch '[["focus","--window","Excel"],["hotkey","ctrl","home"],["paste-table","table.csv"],["screenshot","--ocr","--window","Excel"]]'
    每步的结果按顺序返回；某一步失败即停止（除非 --continue-on-error）。"""
    raw = a.steps
    if raw.startswith("@"):  # 从文件读（shell 引号最保险）
        try:
            raw = open(raw[1:], encoding="utf-8").read()
        except OSError as e:
            raise ControlError(f"cannot read steps file: {e}")
    try:
        steps = json.loads(raw)
        assert isinstance(steps, list)
    except Exception as e:
        raise ControlError(f"batch expects a JSON array of argv arrays (write it to a file and pass @steps.json to avoid shell quoting): {e}")
    parser = build_parser()
    results = []
    for i, argv in enumerate(steps):
        if not isinstance(argv, list) or not argv:
            results.append({"step": i, "ok": False, "error": "each step must be a non-empty argv array"}); break
        if argv[0] == "batch":
            results.append({"step": i, "ok": False, "error": "nested batch not allowed"}); break
        try:
            ns = parser.parse_args([str(x) for x in argv])
            out = ns.fn(ns)
            results.append({"step": i, "cmd": argv[0], "ok": True, "result": out})
        except SystemExit:
            results.append({"step": i, "cmd": argv[0], "ok": False, "error": "bad arguments"}); break
        except ControlError as e:
            results.append({"step": i, "cmd": argv[0], "ok": False, "error": str(e), "hint": getattr(e, "hint", None)})
            if not a.continue_on_error: break
        except Exception as e:  # noqa: BLE001
            results.append({"step": i, "cmd": argv[0], "ok": False, "error": f"{type(e).__name__}: {e}"})
            if not a.continue_on_error: break
        if a.pause and i < len(steps) - 1:
            time.sleep(a.pause)
    return {"steps": len(steps), "completed": sum(1 for r in results if r.get("ok")), "results": results}


def cmd_overlay(a) -> dict:
    """只显示控制指示层（不动鼠标）：开始一段操作前调用，让用户知道接下来电脑会被控制。"""
    ensure_overlay()
    time.sleep(1.0)
    return {"overlay": "shown" if _overlay_alive() else "starting", "hint": "it hides itself ~25 s after the last action"}


def cmd_wait(a) -> dict:
    time.sleep(a.seconds)
    return {"waited": a.seconds}


def cmd_clipboard(a) -> dict:
    if a.set is not None:
        clipboard_set(a.set)
        return {"clipboard_set_chars": len(a.set)}
    text = clipboard_get()
    return {"clipboard": text, "chars": len(text)}


def cmd_paste_table(a) -> dict:
    ensure_overlay()
    front = _ensure_front(a)
    pd = _need("pandas")
    path = a.path
    if not os.path.exists(path):
        raise ControlError(f"file not found: {path}")
    sep = a.sep
    if sep is None:
        sep = "\t" if path.lower().endswith((".tsv", ".txt")) else ","
    if sep == "auto":
        df = pd.read_csv(path, sep=None, engine="python", header=None if a.no_header else "infer")
    else:
        df = pd.read_csv(path, sep=sep, header=None if a.no_header else "infer")
    text = df.to_csv(sep="\t", index=False, header=not a.no_header, lineterminator="\n")
    clipboard_set(text)
    time.sleep(0.1)
    if not a.no_paste:
        if not _win_send_keys([_mod_key(), "v"]):
            (_win_send_keys([_mod_key(), "v"]) or _pyautogui().hotkey(_mod_key(), "v"))
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "header": [str(c) for c in df.columns] if not a.no_header else None,
        "pasted": not a.no_paste,
        "clipboard_chars": len(text),
        **(front or {}),
    }


# ----------------------------------------------------------------------------
# argparse
# ----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="control.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="platform, screen size, mouse position, installed packages")
    s.set_defaults(fn=cmd_info)

    s = sub.add_parser("windows", help="list top-level visible windows")
    s.add_argument("--filter", help="only titles/process names containing this substring")
    s.set_defaults(fn=cmd_windows)

    s = sub.add_parser("focus", help="bring a window to the front")
    s.add_argument("--window", required=True, help="substring of the window title (case-insensitive)")
    s.set_defaults(fn=cmd_focus)

    s = sub.add_parser("inspect", help="dump the UI Automation control tree of a window (Windows)")
    s.add_argument("--window", required=True, help="substring of the window title")
    s.add_argument("--depth", type=int, default=12, help="max tree depth (default 12)")
    s.add_argument("--max", type=int, default=300, help="max controls to return (default 300)")
    s.add_argument("--name", help="only controls whose name/auto_id contains this substring")
    s.add_argument("--all", action="store_true", help="include unnamed and invisible controls")
    s.set_defaults(fn=cmd_inspect)

    s = sub.add_parser("screenshot", help="save a PNG of the screen; --ocr returns text lines with coordinates")
    s.add_argument("--out", help="output PNG path (default ./desktop_control/screen-<timestamp>.png)")
    s.add_argument("--ocr", action="store_true", help="run OCR (rapidocr-onnxruntime) on the screenshot")
    s.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"), help="capture only this region")
    s.add_argument("--window", help="capture only the window whose title contains this substring")
    s.set_defaults(fn=cmd_screenshot)

    s = sub.add_parser("find-text", help="locate text on screen (UIA names first, then OCR)")
    s.add_argument("text")
    s.add_argument("--ocr", action="store_true", help="skip UIA and use OCR only")
    s.add_argument("--window", help="search this window instead of the foreground window")
    s.set_defaults(fn=cmd_find_text)

    s = sub.add_parser("click", help="click at screen coordinates")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s.add_argument("--button", choices=["left", "right", "middle"], default="left")
    s.add_argument("--double", action="store_true")
    s.add_argument("--window", help="bring this window (title substring) to the front first - always pass it")
    s.set_defaults(fn=cmd_click)

    s = sub.add_parser("click-text", help="find text on screen and click its center")
    s.add_argument("text")
    s.add_argument("--ocr", action="store_true", help="skip UIA and use OCR only")
    s.add_argument("--window", help="search this window instead of the foreground window")
    s.add_argument("--button", choices=["left", "right", "middle"], default="left")
    s.add_argument("--double", action="store_true")
    s.set_defaults(fn=cmd_click_text)

    s = sub.add_parser("move", help="move the mouse")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s.add_argument("--window", help="bring this window (title substring) to the front first - always pass it")
    s.set_defaults(fn=cmd_move)

    s = sub.add_parser("scroll", help="scroll the wheel; positive = up, negative = down")
    s.add_argument("amount", type=int)
    s.add_argument("--x", type=int)
    s.add_argument("--y", type=int)
    s.add_argument("--window", help="bring this window (title substring) to the front first - always pass it")
    s.set_defaults(fn=cmd_scroll)

    s = sub.add_parser("type", help="type text into the focused control (CJK goes via clipboard paste)")
    s.add_argument("text")
    s.add_argument("--enter", action="store_true", help="press Enter afterwards")
    s.add_argument("--window", help="bring this window (title substring) to the front first - always pass it")
    s.set_defaults(fn=cmd_type)

    s = sub.add_parser("hotkey", help="press a key combination, e.g. `hotkey ctrl s` or `hotkey ctrl+shift+s`")
    s.add_argument("keys", nargs="+")
    s.add_argument("--window", help="bring this window (title substring) to the front first - always pass it")
    s.set_defaults(fn=cmd_hotkey)

    s = sub.add_parser("press", help="press a single key, e.g. enter, tab, esc, down, f2")
    s.add_argument("key")
    s.add_argument("--times", type=int, default=1)
    s.add_argument("--window", help="bring this window (title substring) to the front first - always pass it")
    s.set_defaults(fn=cmd_press)

    s = sub.add_parser("open", help="open an app (alias like excel/zotero/prism), a file path, or a URL")
    s.add_argument("target")
    s.add_argument("args", nargs="*", help="extra arguments for the app (e.g. a file to open)")
    s.set_defaults(fn=cmd_open)

    s = sub.add_parser("batch", help="run several commands in one call: batch '[[\"focus\",\"--window\",\"Excel\"],[\"hotkey\",\"ctrl\",\"s\"]]'")
    s.add_argument("steps", help="JSON array of argv arrays")
    s.add_argument("--pause", type=float, default=0.4, help="seconds to wait between steps (default 0.4)")
    s.add_argument("--continue-on-error", action="store_true")
    s.set_defaults(fn=cmd_batch)

    s = sub.add_parser("overlay", help="show the 'BioDSH is controlling this computer' overlay (no mouse action)")
    s.set_defaults(fn=cmd_overlay)

    s = sub.add_parser("wait", help="sleep N seconds")
    s.add_argument("seconds", type=float)
    s.set_defaults(fn=cmd_wait)

    s = sub.add_parser("clipboard", help="read the clipboard, or set it with --set")
    s.add_argument("--set", help="text to put on the clipboard")
    s.set_defaults(fn=cmd_clipboard)

    s = sub.add_parser("paste-table", help="put a CSV/TSV on the clipboard as tab-separated text and press Ctrl+V")
    s.add_argument("path")
    s.add_argument("--sep", help="input separator (default: tab for .tsv/.txt, comma otherwise; 'auto' to sniff)")
    s.add_argument("--no-header", action="store_true", help="the file has no header row")
    s.add_argument("--no-paste", action="store_true", help="only load the clipboard; do not press Ctrl+V")
    s.add_argument("--window", help="bring this window (title substring) to the front first - always pass it")
    s.set_defaults(fn=cmd_paste_table)
    return p


def main(argv: list[str] | None = None) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    _set_dpi_aware()
    args = build_parser().parse_args(argv)
    try:
        # 任何会"看"或"动"电脑的命令都先亮起指示层（info / clipboard 读取除外），让用户从第一步就知道 BioDSH 在控制
        if args.fn not in (cmd_info, cmd_clipboard) and not os.environ.get("BIODSH_NO_OVERLAY"):
            try:
                ensure_overlay()
            except Exception:
                pass
        emit(args.fn(args))
    except ControlError as exc:
        fail(exc.message, exc.hint, **exc.extra)
    except KeyboardInterrupt:
        fail("interrupted")
    except Exception as exc:  # pyautogui.FailSafeException and everything else
        name = type(exc).__name__
        hint = None
        if name == "FailSafeException":
            hint = "The user moved the mouse to a screen corner to abort. Stop and ask the user before continuing."
        fail(f"{name}: {exc}", hint)


if __name__ == "__main__":
    main()
