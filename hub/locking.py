"""Cross-process serialization for preferences shared by desktop and client."""
import ctypes
import hashlib
import os
from contextlib import contextmanager


@contextmanager
def settings_lock(path):
    if os.name != 'nt':
        import fcntl
        with path.with_suffix('.lock').open('a+b') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    identity = hashlib.sha256(str(path.resolve()).casefold().encode('utf-8')).hexdigest()[:24]
    handle = kernel.CreateMutexW(None, False, 'Local\\OKDEV-Preferences-' + identity)
    if not handle:
        raise ValueError('Ayarlar şu anda kaydedilemiyor. Birazdan tekrar dene.')
    acquired = False
    try:
        acquired = kernel.WaitForSingleObject(handle, 5000) in (0, 0x80)
        if not acquired:
            raise ValueError('Başka bir ayar kaydediliyor. Birazdan tekrar dene.')
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)
