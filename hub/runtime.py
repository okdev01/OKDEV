"""Native WebView2 prerequisite checks without creating a browser window.

Uses Microsoft's GetAvailableCoreWebView2BrowserVersionString contract and frees
its result with CoTaskMemFree. No runtime is downloaded or installed by OKDEV.
https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution
"""
import ctypes
from functools import lru_cache
from pathlib import Path
import sys
import webbrowser

RUNTIME_URL = 'https://developer.microsoft.com/en-us/microsoft-edge/webview2/'
MISSING_MESSAGE = ('Mod Merkezi için Microsoft Edge WebView2 Runtime gerekiyor.\n\n'
                   'Microsoft’un resmi sayfasından Evergreen Runtime kurup OKDEV’i yeniden aç. '
                   'Modların ve ayarların korunur.\n\nResmi indirme sayfası açılsın mı?')


@lru_cache(maxsize=1)
def _native_functions():
    from webview.util import interop_dll_path
    # OKDEV release builds target x64. Keep the source probe usable on x86.
    architecture = 'win-x64' if ctypes.sizeof(ctypes.c_void_p) == 8 else 'win-x86'
    loader = ctypes.WinDLL(str(Path(interop_dll_path(architecture)) / 'WebView2Loader.dll'))
    get_version = loader.GetAvailableCoreWebView2BrowserVersionString
    get_version.argtypes = (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))
    get_version.restype = ctypes.c_long
    free = ctypes.WinDLL('ole32').CoTaskMemFree
    free.argtypes = (ctypes.c_void_p,)
    free.restype = None
    return get_version, free


def available_version():
    if sys.platform != 'win32':
        return None
    try:
        get_version, free = _native_functions()
        pointer = ctypes.c_void_p()
        try:
            result = get_version(None, ctypes.byref(pointer))
            if result != 0 or not pointer.value:
                return None
            return ctypes.wstring_at(pointer.value)[:100]
        finally:
            if pointer.value:
                free(pointer)
    except (OSError, AttributeError, ImportError):
        return None


def _message(text, flags):
    if sys.platform != 'win32':
        return 0
    function = ctypes.WinDLL('user32').MessageBoxW
    function.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint)
    function.restype = ctypes.c_int
    return function(None, text, 'OKDEV • Mod Merkezi', flags)


def show_missing_runtime():
    if _message(MISSING_MESSAGE, 0x10 | 0x04) == 6:  # MB_ICONERROR | MB_YESNO, IDYES
        webbrowser.open(RUNTIME_URL)


def show_startup_error():
    _message('Mod Merkezi başlatılamadı.\n\nOKDEV’i yeniden açmayı dene. Sorun sürerse '
             'WebView2 Runtime kurulumunu ve OKDEV klasöründeki dosyaları kontrol et. '
             'Mevcut kurulum klasörüne Setup çalıştırarak uygulama dosyalarını onarabilirsin.', 0x10)
