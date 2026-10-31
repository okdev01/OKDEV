#pragma once
#include <windows.h>
#include <stddef.h>

struct OkdevRoute {
    const wchar_t* original;
    const wchar_t* replacement;
};

// Deliberately restricted to our own harness executable, in this process.
using InstallRoutes = DWORD (__cdecl*)(const OkdevRoute*, size_t);
using RemoveRoutes = DWORD (__cdecl*)();
