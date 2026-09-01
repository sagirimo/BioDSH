"""BioDSH 控制指示层：让用户一眼看出"电脑正在被 BioDSH 控制"，但要好看、不碍事。

Windows：两个分层窗口（per-pixel alpha，真半透明 + 抗锯齿）——
  · 顶部正中一枚深色毛玻璃胶囊：蓝色呼吸点 + 「BioDSH 正在控制电脑」+ 灰字提示
  · 跟随光标的柔光环：淡蓝辉光 + 细环缓慢呼吸，不遮住光标本身
其他系统：退回 tkinter 简版。
由 control.py 在动作前自动拉起（沙盒外，经资源管理器）；每个动作刷新心跳文件，心跳停 IDLE_EXIT 秒后自动退出。
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
import time

IDLE_EXIT = 25.0
# 状态目录由 control.py 通过第一个参数传入（工作区下的 .biodsh_control），沙盒内外都能读写
STATE_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "biodsh-desktop-control")
os.makedirs(STATE_DIR, exist_ok=True)
HEARTBEAT = os.path.join(STATE_DIR, "heartbeat")
LOCK = os.path.join(STATE_DIR, "overlay.pid")
IS_WIN = sys.platform.startswith("win")
ACCENT = (10, 132, 255)
zh = (os.environ.get("BIODSH_LANG", "") or "zh").lower().startswith("zh")
TITLE = "BioDSH 正在控制电脑" if zh else "BioDSH is controlling this computer"
HINT = "甩鼠标到屏幕角落可中止" if zh else "slam the mouse into a corner to abort"


def _should_exit(t0: float) -> bool:
    now = time.time()
    try:
        return now - os.path.getmtime(HEARTBEAT) > IDLE_EXIT
    except OSError:
        return now - t0 > IDLE_EXIT


# ---------------------------------------------------------------------------
# Windows：分层窗口
# ---------------------------------------------------------------------------
def run_win() -> None:
    import ctypes
    from ctypes import wintypes

    import win32api, win32con, win32gui  # type: ignore
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

    user32 = ctypes.windll.user32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2 → 用物理像素，文字不会被系统放大成模糊
    except Exception:
        user32.SetProcessDPIAware()
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    try:
        DPI = user32.GetDpiForSystem() / 96.0
    except Exception:
        DPI = 1.0
    SS = 2  # 2 倍超采样再缩回：边缘和文字更细腻
    S = DPI * SS

    def px(v: float) -> int:
        return int(round(v * S))

    def font(size: int, bold: bool = False):
        for name in (("msyhbd.ttc" if bold else "msyh.ttc"), "msyh.ttc", "segoeui.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name), size)
            except OSError:
                continue
        return ImageFont.load_default()

    class LayeredWindow:
        def __init__(self, w: int, h: int, x: int, y: int):
            self.w, self.h, self.x, self.y = w, h, x, y
            hinst = win32api.GetModuleHandle(None)
            cls = win32gui.WNDCLASS()
            cls.lpszClassName = f"BioDSHOverlay{id(self)}"
            cls.hInstance = hinst
            cls.lpfnWndProc = {win32con.WM_DESTROY: lambda *_: win32gui.PostQuitMessage(0)}
            atom = win32gui.RegisterClass(cls)
            ex = win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE
            self.hwnd = win32gui.CreateWindowEx(ex, atom, "", win32con.WS_POPUP, x, y, w, h, 0, 0, hinst, None)
            win32gui.ShowWindow(self.hwnd, win32con.SW_SHOWNOACTIVATE)

        def paint(self, img: "Image.Image", x: int | None = None, y: int | None = None) -> None:
            if x is not None: self.x = x
            if y is not None: self.y = y
            w, h = img.size
            hdc = win32gui.GetDC(0)
            mem = win32gui.CreateCompatibleDC(hdc)
            # 32bpp 预乘 alpha 的 DIB
            bmi = ctypes.create_string_buffer(40)
            ctypes.memmove(bmi, (ctypes.c_uint32 * 10)(40, w, -h, 1 | (32 << 16), 0, 0, 0, 0, 0, 0), 40)
            bits = ctypes.c_void_p()
            hbmp = ctypes.windll.gdi32.CreateDIBSection(hdc, bmi, 0, ctypes.byref(bits), None, 0)
            r, g, b, a = img.convert("RGBA").split()
            # 预乘 alpha（UpdateLayeredWindow 要求），用 ImageChops 一次算完
            pre = Image.merge("RGBA", (ImageChops.multiply(b, a), ImageChops.multiply(g, a), ImageChops.multiply(r, a), a))  # BGRA
            data = pre.tobytes()
            ctypes.memmove(bits, data, len(data))
            old = win32gui.SelectObject(mem, hbmp)
            blend = (ctypes.c_ubyte * 4)(0, 0, 255, 1)  # AC_SRC_OVER, flags, alpha, AC_SRC_ALPHA
            pt_src = wintypes.POINT(0, 0); size = wintypes.SIZE(w, h); pt_dst = wintypes.POINT(self.x, self.y)
            ctypes.windll.user32.UpdateLayeredWindow(self.hwnd, hdc, ctypes.byref(pt_dst), ctypes.byref(size), mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), 2)
            win32gui.SelectObject(mem, old)
            ctypes.windll.gdi32.DeleteObject(hbmp)
            win32gui.DeleteDC(mem)
            win32gui.ReleaseDC(0, hdc)

    # ---- 胶囊横幅（静态底 + 呼吸点动画）
    f_t, f_h = font(px(14), True), font(px(11.5))
    pad = px(16)
    tw = int(ImageDraw.Draw(Image.new("RGBA", (10, 10))).textlength(TITLE, font=f_t))
    hw = int(ImageDraw.Draw(Image.new("RGBA", (10, 10))).textlength(HINT, font=f_h))
    bw, bh = pad + px(14) + px(10) + tw + px(14) + hw + pad, px(40)
    shadow = px(14)
    W, H = bw + shadow * 2, bh + shadow * 2
    OW, OH = W // SS, H // SS  # 实际窗口尺寸

    def banner_frame(t: float, alpha: float) -> "Image.Image":
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        # 柔和阴影
        sh_im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh_im).rounded_rectangle((shadow, shadow + px(4), shadow + bw, shadow + bh + px(4)), radius=bh // 2, fill=(0, 0, 0, 90))
        sh_im = sh_im.filter(ImageFilter.GaussianBlur(px(9)))
        im.alpha_composite(sh_im)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((shadow, shadow, shadow + bw, shadow + bh), radius=bh // 2, fill=(28, 28, 30, 216), outline=(255, 255, 255, 40), width=max(1, px(0.75)))
        # 呼吸点
        p = 0.5 + 0.5 * math.sin(t * 2.4)
        cx, cy = shadow + pad + px(7), shadow + bh // 2
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((cx - px(9), cy - px(9), cx + px(9), cy + px(9)), fill=(*ACCENT, int(90 + 90 * p)))
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(px(5))))
        d.ellipse((cx - px(4), cy - px(4), cx + px(4), cy + px(4)), fill=(*ACCENT, 255))
        x = shadow + pad + px(14) + px(10)
        d.text((x, shadow + bh // 2), TITLE, font=f_t, fill=(245, 245, 247, 242), anchor="lm")
        d.text((x + tw + px(14), shadow + bh // 2 + px(1)), HINT, font=f_h, fill=(186, 186, 192, 205), anchor="lm")
        im = im.resize((OW, OH), Image.LANCZOS)
        if alpha < 1.0:
            im.putalpha(im.split()[3].point(lambda v: int(v * alpha)))
        return im

    # ---- 光标柔光环
    OR_ = int(round(52 * DPI))  # 实际窗口半边
    R = OR_ * SS

    def ring_frame(t: float, alpha: float) -> "Image.Image":
        im = Image.new("RGBA", (R * 2, R * 2), (0, 0, 0, 0))
        p = 0.5 + 0.5 * math.sin(t * 2.0)
        glow = Image.new("RGBA", (R * 2, R * 2), (0, 0, 0, 0))
        gr = px(21 + 5 * p)
        ImageDraw.Draw(glow).ellipse((R - gr, R - gr, R + gr, R + gr), fill=(*ACCENT, int(70 + 40 * p)))
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(px(8))))
        d = ImageDraw.Draw(im)
        rr = px(14 + 3.5 * p)
        d.ellipse((R - rr, R - rr, R + rr, R + rr), outline=(*ACCENT, int(205 + 40 * p)), width=max(2, px(1.6)))
        im = im.resize((OR_ * 2, OR_ * 2), Image.LANCZOS)
        if alpha < 1.0:
            im.putalpha(im.split()[3].point(lambda v: int(v * alpha)))
        return im

    banner = LayeredWindow(OW, OH, (sw - OW) // 2, int(8 * DPI))
    ring = LayeredWindow(OR_ * 2, OR_ * 2, 0, 0)
    open(LOCK, "w").write(str(os.getpid()))
    t0 = time.time()
    last_banner = 0.0
    try:
        while True:
            win32gui.PumpWaitingMessages()
            now = time.time()
            if _should_exit(t0):
                break
            fade = min(1.0, (now - t0) / 0.35)
            if now - last_banner > 0.05:
                banner.paint(banner_frame(now, fade)); last_banner = now
            if int(now * 2) != int((now - 0.016) * 2):  # 每 0.5 s 重新压到最顶层，别被后开的窗口盖住
                for h in (banner.hwnd, ring.hwnd):
                    win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            x, y = win32gui.GetCursorPos()
            ring.paint(ring_frame(now, fade), x - OR_, y - OR_)
            time.sleep(0.016)
    finally:
        try:
            win32gui.DestroyWindow(ring.hwnd); win32gui.DestroyWindow(banner.hwnd)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 其他系统：tkinter 简版
# ---------------------------------------------------------------------------
def run_tk() -> None:
    import tkinter as tk
    KEY = "#010203"
    root = tk.Tk(); root.overrideredirect(True); root.attributes("-topmost", True)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{sw}x{sh}+0+0"); root.configure(bg=KEY)
    try:
        root.attributes("-transparent", True); root.configure(bg="systemTransparent")
    except Exception:
        root.attributes("-alpha", 0.35)
    cv = tk.Canvas(root, width=sw, height=sh, bg=KEY, highlightthickness=0, bd=0); cv.pack()
    bw = 420; bx = (sw - bw) // 2
    cv.create_rectangle(bx, 14, bx + bw, 54, fill="#1c1c1e", outline="")
    cv.create_text(sw // 2, 34, text=f"●  {TITLE}   {HINT}", fill="#f5f5f7", font=("Helvetica", 12, "bold"))
    ring = cv.create_oval(0, 0, 0, 0, outline="#0a84ff", width=2)
    t0 = time.time()
    open(LOCK, "w").write(str(os.getpid()))

    def tick():
        if _should_exit(t0):
            root.destroy(); return
        x, y = root.winfo_pointerx(), root.winfo_pointery()
        rr = 15 + 4 * (0.5 + 0.5 * math.sin(time.time() * 2.0))
        cv.coords(ring, x - rr, y - rr, x + rr, y + rr)
        root.after(16, tick)

    tick(); root.mainloop()


def main() -> None:
    try:
        if IS_WIN:
            run_win()
        else:
            run_tk()
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


if __name__ == "__main__":
    main()
