"""Start a child with the interactive user's token, including from elevated OKDEV."""
import ctypes
from ctypes import wintypes as w
import io
import msvcrt
import os
import subprocess
import threading


class STARTUPINFO(ctypes.Structure):
    _fields_ = [('cb', w.DWORD), ('lpReserved', w.LPWSTR), ('lpDesktop', w.LPWSTR),
                ('lpTitle', w.LPWSTR), ('dwX', w.DWORD), ('dwY', w.DWORD),
                ('dwXSize', w.DWORD), ('dwYSize', w.DWORD), ('dwXCountChars', w.DWORD),
                ('dwYCountChars', w.DWORD), ('dwFillAttribute', w.DWORD),
                ('dwFlags', w.DWORD), ('wShowWindow', w.WORD), ('cbReserved2', w.WORD),
                ('lpReserved2', ctypes.c_void_p), ('hStdInput', w.HANDLE),
                ('hStdOutput', w.HANDLE), ('hStdError', w.HANDLE)]


class PROCESSINFO(ctypes.Structure):
    _fields_ = [('hProcess', w.HANDLE), ('hThread', w.HANDLE),
                ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD)]


kernel = ctypes.WinDLL('kernel32', use_last_error=True)
advapi = ctypes.WinDLL('advapi32', use_last_error=True)
user = ctypes.WinDLL('user32', use_last_error=True)
kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel.OpenProcess.restype = w.HANDLE
kernel.CloseHandle.argtypes = [w.HANDLE]
kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
kernel.WaitForSingleObject.restype = w.DWORD
kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
user.GetShellWindow.restype = w.HWND
user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
advapi.DuplicateTokenEx.argtypes = [w.HANDLE, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(w.HANDLE)]
advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
advapi.CreateProcessWithTokenW.argtypes = [w.HANDLE, w.DWORD, w.LPCWSTR, w.LPWSTR,
                                        w.DWORD, ctypes.c_void_p, w.LPCWSTR,
                                        ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESSINFO)]


class UserProcess:
    """The Popen subset used by the patcher's existing line protocol."""
    def __init__(self, args, cwd=None):
        self.args, self.returncode = args, None
        self._handle = None
        self._lock = threading.Lock()
        pid = w.DWORD()
        hwnd = user.GetShellWindow()
        if not hwnd or not user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            raise OSError('Windows kullanıcı oturumu bulunamadı.')
        process = kernel.OpenProcess(0x1000, False, pid.value)
        token, primary = w.HANDLE(), w.HANDLE()
        fds = []
        try:
            if not process or not advapi.OpenProcessToken(process, 0x000B, ctypes.byref(token)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not advapi.DuplicateTokenEx(token, 0x02000000, None, 2, 1, ctypes.byref(primary)):
                raise ctypes.WinError(ctypes.get_last_error())
            elevated, size = w.DWORD(), w.DWORD()
            if not advapi.GetTokenInformation(primary, 20, ctypes.byref(elevated), ctypes.sizeof(elevated), ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            if elevated.value:
                raise RuntimeError('LTK için yönetici olmayan Windows oturumu gerekiyor.')
            read_in, write_in = os.pipe(); fds.extend([read_in, write_in])
            read_out, write_out = os.pipe(); fds.extend([read_out, write_out])
            for fd in (read_in, write_out):
                os.set_inheritable(fd, True)
            info = STARTUPINFO(cb=ctypes.sizeof(STARTUPINFO), dwFlags=0x101, wShowWindow=0,
                               hStdInput=msvcrt.get_osfhandle(read_in),
                               hStdOutput=msvcrt.get_osfhandle(write_out),
                               hStdError=msvcrt.get_osfhandle(write_out))
            result = PROCESSINFO()
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(x) for x in args]))
            if not advapi.CreateProcessWithTokenW(primary, 0, str(args[0]), command,
                                                  0x08000000, None, str(cwd) if cwd else None,
                                                  ctypes.byref(info), ctypes.byref(result)):
                raise ctypes.WinError(ctypes.get_last_error())
            kernel.CloseHandle(result.hThread)
            self._handle, self.pid = result.hProcess, result.dwProcessId
            os.close(read_in); fds.remove(read_in)
            os.close(write_out); fds.remove(write_out)
            self.stdin = io.open(write_in, 'w', encoding='utf-8', errors='replace', buffering=1)
            fds.remove(write_in)
            self.stdout = io.open(read_out, 'r', encoding='utf-8', errors='replace')
            fds.remove(read_out)
        finally:
            for fd in fds:
                os.close(fd)
            for handle in (primary, token, process):
                if handle:
                    kernel.CloseHandle(handle)

    def poll(self):
        with self._lock:
            if self.returncode is None and kernel.WaitForSingleObject(self._handle, 0) == 0:
                result = w.DWORD()
                if not kernel.GetExitCodeProcess(self._handle, ctypes.byref(result)):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.returncode = result.value
            return self.returncode

    def wait(self, timeout=None):
        if kernel.WaitForSingleObject(self._handle, 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))) == 258:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return self.poll()

    def terminate(self):
        if self.poll() is None and not kernel.TerminateProcess(self._handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    kill = terminate

    def __del__(self):
        if getattr(self, '_handle', None):
            kernel.CloseHandle(self._handle)
            self._handle = None


def popen(args, cwd=None):
    if ctypes.windll.shell32.IsUserAnAdmin():
        return UserProcess(args, cwd)
    return subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW,
                            text=True, encoding='utf-8', errors='replace', bufsize=1)
