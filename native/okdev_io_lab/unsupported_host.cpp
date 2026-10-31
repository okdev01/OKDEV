// A controlled host with only one of the required imports. Installation must
// fail without changing its reads or retaining locks on the prepared artifact.
#include "okdev_io_lab.h"
#include <filesystem>
#include <fstream>
#include <iostream>

int wmain(int argc,wchar_t** argv) {
    if (argc!=3) return 1;
    namespace fs=std::filesystem;
    fs::path root=fs::absolute(argv[2]);
    fs::create_directories(root);
    auto original=root/L"Original.wad.client",replacement=root/L"Replacement.wad.client";
    { std::ofstream file(original); file << "base"; }
    { std::ofstream file(replacement); file << "modified"; }
    HMODULE dll=LoadLibraryW(fs::absolute(argv[1]).c_str());
    if (!dll) return 2;
    auto install=reinterpret_cast<InstallRoutes>(GetProcAddress(dll,"OKDEV_InstallForHarness"));
    if (!install) return 3;
    std::wstring a=original.wstring(),b=replacement.wstring();
    OkdevRoute route[]={{a.c_str(),b.c_str()}};
    if (install(route,1)!=ERROR_PROC_NOT_FOUND) return 4;
    HANDLE file=CreateFileW(original.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
    if (file==INVALID_HANDLE_VALUE) return 5;
    char data[16]={}; DWORD count=0;
    BOOL read=ReadFile(file,data,sizeof(data),&count,nullptr);
    CloseHandle(file);
    if (!read || std::string(data,count)!="base") return 6;
    file=CreateFileW(replacement.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
    if (file==INVALID_HANDLE_VALUE) return 7;
    CloseHandle(file);
    FreeLibrary(dll);
    std::cout << "{\"scope\":\"own_process_only\",\"unsupported_imports_rejected\":true,"
                 "\"reads_unchanged\":true,\"locks_released\":true,\"game_runtime_available\":false}\n";
    return 0;
}
