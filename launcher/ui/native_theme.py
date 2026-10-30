"""Small owned GDI resources for the startup window; no GUI framework required."""
import ctypes
from ctypes import wintypes

from utils.system.win32_base import gdi32, user32


def color(value):
    value=value.lstrip('#')
    r,g,b=(int(value[n:n+2],16) for n in (0,2,4))
    return r | g << 8 | b << 16


class NativeTheme:
    background=color('#0b1019')
    text=color('#edf2fa')
    muted=color('#a6b5ca')
    accent=color('#c0a7ff')
    track=color('#243146')

    def __init__(self, scale=1):
        self.scale=scale
        gdi32.CreateSolidBrush.argtypes=[wintypes.DWORD]
        gdi32.CreateSolidBrush.restype=wintypes.HBRUSH
        gdi32.DeleteObject.argtypes=[wintypes.HANDLE]
        gdi32.DeleteObject.restype=wintypes.BOOL
        gdi32.SetTextColor.argtypes=[wintypes.HDC,wintypes.DWORD]
        gdi32.SetBkColor.argtypes=[wintypes.HDC,wintypes.DWORD]
        user32.FillRect.argtypes=[wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.HBRUSH]
        gdi32.CreateFontW.argtypes=[ctypes.c_int]*5+[wintypes.DWORD]*8+[wintypes.LPCWSTR]
        gdi32.CreateFontW.restype=wintypes.HANDLE
        self.brush=gdi32.CreateSolidBrush(self.background)
        self.fonts=[]
        self.body=self.font(14,400)
        self.heading=self.font(17,600)
        self.brand=self.font(27,700)

    def font(self,height,weight):
        handle=gdi32.CreateFontW(-round(height*self.scale),0,0,0,weight,0,0,0,1,0,0,5,0,'Segoe UI')
        if not handle: raise ctypes.WinError()
        self.fonts.append(handle)
        return handle

    def paint(self,hwnd,hdc):
        rect=wintypes.RECT()
        user32.GetClientRect(hwnd,ctypes.byref(rect))
        user32.FillRect(hdc,ctypes.byref(rect),self.brush)

    def text_brush(self,hdc,foreground):
        gdi32.SetTextColor(hdc,foreground)
        gdi32.SetBkColor(hdc,self.background)
        return self.brush

    def close(self):
        for handle in self.fonts:
            gdi32.DeleteObject(handle)
        self.fonts.clear()
        if self.brush:
            gdi32.DeleteObject(self.brush)
            self.brush=None

    @staticmethod
    def titlebar(hwnd):
        try:
            function=ctypes.windll.dwmapi.DwmSetWindowAttribute
            function.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
            enabled=wintypes.BOOL(True)
            function(hwnd,20,ctypes.byref(enabled),ctypes.sizeof(enabled))
        except (AttributeError,OSError):
            pass  # Older Windows keeps its system title bar.
