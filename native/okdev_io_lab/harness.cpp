#include "okdev_io_lab.h"
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <iostream>
#include <bcrypt.h>
#include <array>
#include <algorithm>

namespace fs=std::filesystem;

void check(bool condition,const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void write(const fs::path& path,const std::string& content) {
    std::ofstream output(path,std::ios::binary);
    output << content;
    check(output.good(),"fixture write failed");
}

std::string read_w(const fs::path& path) {
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                            nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return "<failed>";
    char buffer[128]={}; DWORD count=0;
    BOOL success=ReadFile(file,buffer,sizeof(buffer),&count,nullptr);
    CloseHandle(file);
    return success?std::string(buffer,count):"<failed>";
}

std::string read_a(const fs::path& path) {
    std::string name=path.string();
    HANDLE file=CreateFileA(name.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                            nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return "<failed>";
    char buffer[128]={}; DWORD count=0;
    BOOL success=ReadFile(file,buffer,sizeof(buffer),&count,nullptr);
    CloseHandle(file);
    return success?std::string(buffer,count):"<failed>";
}

bool same_file(HANDLE left,HANDLE right) {
    BY_HANDLE_FILE_INFORMATION a{},b{};
    return GetFileInformationByHandle(left,&a) && GetFileInformationByHandle(right,&b) &&
           a.dwVolumeSerialNumber==b.dwVolumeSerialNumber &&
           a.nFileIndexHigh==b.nFileIndexHigh && a.nFileIndexLow==b.nFileIndexLow;
}

std::string hash_file(const fs::path& path,bool ansi=false,bool mapped=false) {
    struct Resources {
        HANDLE file=INVALID_HANDLE_VALUE,mapping=nullptr;
        void* view=nullptr;
        BCRYPT_ALG_HANDLE algorithm=nullptr;
        BCRYPT_HASH_HANDLE hash=nullptr;
        ~Resources() {
            if (hash) BCryptDestroyHash(hash);
            if (algorithm) BCryptCloseAlgorithmProvider(algorithm,0);
            if (view) UnmapViewOfFile(view);
            if (mapping) CloseHandle(mapping);
            if (file!=INVALID_HANDLE_VALUE) CloseHandle(file);
        }
    } resources;
    resources.file=ansi?CreateFileA(path.string().c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                                   nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr):
                        CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                                   nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    check(resources.file!=INVALID_HANDLE_VALUE,"hash file open failed");
    check(BCryptOpenAlgorithmProvider(&resources.algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,"SHA256 provider failed");
    check(BCryptCreateHash(resources.algorithm,&resources.hash,nullptr,0,nullptr,0,0)>=0,"SHA256 create failed");
    LARGE_INTEGER size{};
    check(GetFileSizeEx(resources.file,&size) && size.QuadPart>0 && size.QuadPart<=2LL*1024*1024*1024,"invalid hash file size");
    if (mapped) {
        resources.mapping=CreateFileMappingW(resources.file,nullptr,PAGE_READONLY,0,0,nullptr);
        check(resources.mapping!=nullptr,"file mapping failed");
        resources.view=MapViewOfFile(resources.mapping,FILE_MAP_READ,0,0,0);
        check(resources.view!=nullptr,"map view failed");
        auto* bytes=static_cast<unsigned char*>(resources.view);
        for (LONGLONG offset=0;offset<size.QuadPart;) {
            ULONG count=static_cast<ULONG>((std::min)(size.QuadPart-offset,1024LL*1024));
            check(BCryptHashData(resources.hash,bytes+offset,count,0)>=0,"mapped SHA256 update failed");
            offset+=count;
        }
    } else {
        std::vector<unsigned char> buffer(1024*1024);
        DWORD count=0;
        for (;;) {
            check(ReadFile(resources.file,buffer.data(),static_cast<DWORD>(buffer.size()),&count,nullptr)!=0,"hash read failed");
            if (!count) break;
            check(BCryptHashData(resources.hash,buffer.data(),count,0)>=0,"SHA256 update failed");
        }
    }
    std::array<unsigned char,32> digest{};
    check(BCryptFinishHash(resources.hash,digest.data(),static_cast<ULONG>(digest.size()),0)>=0,"SHA256 finish failed");
    const char* digits="0123456789abcdef";
    std::string result;
    for (unsigned char byte:digest) { result+=digits[byte>>4]; result+=digits[byte&15]; }
    return result;
}

int wmain(int argc,wchar_t** argv) {
    try {
        check(argc==3 || argc==4 || argc==6,"expected DLL and fixture directory");
        fs::path root=fs::absolute(argv[2]);
        fs::create_directories(root);
        auto original=root/L"Kayn.wad.client";
        auto replacement=root/L"Kayn.modified.wad.client";
        auto other=root/L"Other.wad.client";
        auto lookalike=root/L"xKayn.wad.client";
        auto unicode=root/L"Kayn\u00e7.wad.client";
        auto unicode_replacement=root/L"\u00fc\u00e7.wad.client";
        write(original,"base"); write(replacement,"modified"); write(other,"other");
        write(lookalike,"lookalike"); write(unicode,"unicode-base");
        write(unicode_replacement,"unicode-modified");
        check(read_w(original)=="base","baseline original");
        HMODULE dll=LoadLibraryW(fs::absolute(argv[1]).c_str());
        check(dll!=nullptr,"LoadLibrary failed");
        auto install=reinterpret_cast<InstallRoutes>(GetProcAddress(dll,"OKDEV_InstallForHarness"));
        auto remove=reinterpret_cast<RemoveRoutes>(GetProcAddress(dll,"OKDEV_RemoveFromHarness"));
        check(install && remove,"exports missing");
        if (argc==6) {
            check(std::wstring(argv[3])==L"--wad","unknown real-file mode");
            auto real_original=root/L"Real.wad.client";
            auto real_replacement=root/L"Real.modified.wad.client";
            fs::copy_file(argv[4],real_original,fs::copy_options::overwrite_existing);
            fs::copy_file(argv[5],real_replacement,fs::copy_options::overwrite_existing);
            std::string before=hash_file(real_original),expected=hash_file(real_replacement);
            check(before!=expected,"real WAD fixture has no modifications");
            std::wstring original_name=real_original.wstring(),replacement_name=real_replacement.wstring();
            OkdevRoute route[]={{original_name.c_str(),replacement_name.c_str()}};
            check(install(route,1)==ERROR_SUCCESS,"real WAD install failed");
            check(hash_file(real_original)==expected,"wide WAD hash mismatch");
            check(hash_file(real_original,true)==expected,"ANSI WAD hash mismatch");
            check(hash_file(real_original,false,true)==expected,"memory-mapped WAD hash mismatch");
            check(remove()==ERROR_SUCCESS,"real WAD remove failed");
            check(hash_file(real_original)==before,"real WAD source changed");
            check(FreeLibrary(dll)!=0,"real WAD FreeLibrary failed");
            std::cout << "{\"scope\":\"own_process_copied_wad\",\"wide\":true,\"ansi\":true,\"memory_mapped\":true,"
                         "\"source_unchanged\":true,\"original_sha256\":\"" << before << "\",\"redirected_sha256\":\"" << expected <<
                         "\",\"game_runtime_available\":false}\n";
            return 0;
        }
        std::wstring a=original.wstring(),b=replacement.wstring();
        std::wstring u=unicode.wstring(),v=unicode_replacement.wstring();
        OkdevRoute routes[]={{a.c_str(),b.c_str()},{u.c_str(),v.c_str()}};
        if (argc==4 && std::wstring(argv[3])==L"--rollback") {
            check(install(routes,2)==ERROR_ACCESS_DENIED,"second patch fault did not occur");
            check(read_w(original)=="base" && read_a(original)=="base","partial install was not rolled back");
            HANDLE unlocked=CreateFileW(replacement.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                                       nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
            check(unlocked!=INVALID_HANDLE_VALUE,"failed installation retained an artifact lock");
            CloseHandle(unlocked);
            check(install(routes,2)==ERROR_SUCCESS,"retry after rollback failed");
            check(read_w(original)=="modified","retry route failed");
            check(remove()==ERROR_SUCCESS,"retry cleanup failed");
            check(FreeLibrary(dll)!=0,"rollback FreeLibrary failed");
            std::cout << "{\"scope\":\"own_process_only\",\"partial_install_rolled_back\":true,"
                         "\"retry_verified\":true,\"game_runtime_available\":false}\n";
            return 0;
        }
        if (argc==4 && std::wstring(argv[3])==L"--reload") {
            check(FreeLibrary(dll)!=0,"initial reload unload failed");
            DWORD before=0,after=0;
            check(GetProcessHandleCount(GetCurrentProcess(),&before)!=0,"reload handle count failed");
            for (unsigned cycle=0;cycle<100;++cycle) {
                HMODULE loaded=LoadLibraryW(fs::absolute(argv[1]).c_str());
                check(loaded!=nullptr,"reload LoadLibrary failed");
                auto start=reinterpret_cast<InstallRoutes>(GetProcAddress(loaded,"OKDEV_InstallForHarness"));
                auto stop=reinterpret_cast<RemoveRoutes>(GetProcAddress(loaded,"OKDEV_RemoveFromHarness"));
                check(start && stop && start(routes,2)==ERROR_SUCCESS,"reload install failed");
                check(read_w(original)=="modified","reload content incorrect");
                check(stop()==ERROR_SUCCESS,"reload remove failed");
                check(FreeLibrary(loaded)!=0,"reload FreeLibrary failed");
                check(read_w(original)=="base","reload original not restored");
            }
            check(GetProcessHandleCount(GetCurrentProcess(),&after)!=0 && before==after,"DLL reload leaked handles");
            std::cout << "{\"scope\":\"own_process_only\",\"dll_reload_cycles\":100,\"handle_leaks\":0,"
                         "\"game_runtime_available\":false}\n";
            return 0;
        }
        if (argc==4) {
            check(install(routes,2)==ERROR_ACCESS_DENIED,"non-harness process was not rejected");
            check(read_w(original)=="base","rejected process changed reads");
            FreeLibrary(dll);
            std::cout << "{\"scope\":\"own_process_only\",\"non_harness_rejected\":true,\"game_runtime_available\":false}\n";
            return 0;
        }
        check(install(nullptr,0)==ERROR_INVALID_PARAMETER,"invalid count accepted");
        OkdevRoute duplicate[]={{a.c_str(),b.c_str()},{a.c_str(),v.c_str()}};
        check(install(duplicate,2)==ERROR_DUP_NAME,"duplicate accepted");
        OkdevRoute identical[]={{a.c_str(),a.c_str()}};
        check(install(identical,1)==ERROR_INVALID_PARAMETER,"identity accepted");
        HANDLE base=CreateFileW(original.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                               nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        check(base!=INVALID_HANDLE_VALUE,"baseline handle failed");
        DWORD status=install(routes,2);
        if (status) std::cerr << "install error " << status << '\n';
        check(status==ERROR_SUCCESS,"install failed");
        check(install(routes,2)==ERROR_ALREADY_EXISTS,"double install accepted");
        check(read_w(original)=="modified","wide read not redirected");
        check(read_a(original)=="modified","ANSI read not redirected");
        check(read_w(unicode)=="unicode-modified","Unicode read not redirected");
        check(read_w(root/L"kAyN.WAD.CLIENT")=="modified","case-insensitive path not redirected");
        auto previous_directory=fs::current_path();
        fs::current_path(root);
        check(read_w(L"Kayn.wad.client")=="modified","relative path not redirected");
        check(read_a(L"Kayn.wad.client")=="modified","relative ANSI path not redirected");
        fs::current_path(previous_directory);
        check(read_w(other)=="other","unmapped read changed");
        check(read_w(lookalike)=="lookalike","suffix collision redirected");
        auto dotted=root/L".."/root.filename()/L"Kayn.wad.client";
        check(read_w(dotted)=="modified","normalized absolute path not redirected");
        HANDLE writer=CreateFileW(original.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                                 nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        check(writer!=INVALID_HANDLE_VALUE && same_file(base,writer),"write request redirected");
        DWORD written=0;
        check(WriteFile(writer,"base",4,&written,nullptr) && written==4,"fixture write failed");
        CloseHandle(writer);
        HANDLE creator=CreateFileW(original.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                                  nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
        check(creator!=INVALID_HANDLE_VALUE && same_file(base,creator),"creation request redirected");
        CloseHandle(creator);
        HANDLE asynchronous=CreateFileW(original.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                                       nullptr,OPEN_EXISTING,FILE_FLAG_OVERLAPPED,nullptr);
        check(asynchronous!=INVALID_HANDLE_VALUE,"overlapped handle open failed");
        OVERLAPPED request{};
        request.hEvent=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        check(request.hEvent!=nullptr,"overlapped event failed");
        char asynchronous_data[32]={}; DWORD asynchronous_size=0;
        BOOL immediate=ReadFile(asynchronous,asynchronous_data,sizeof(asynchronous_data),nullptr,&request);
        check(immediate || GetLastError()==ERROR_IO_PENDING,"overlapped request failed");
        check(GetOverlappedResult(asynchronous,&request,&asynchronous_size,TRUE)!=0 &&
              std::string(asynchronous_data,asynchronous_size)=="modified","overlapped content incorrect");
        CloseHandle(request.hEvent); CloseHandle(asynchronous);
        std::atomic<unsigned> failures{0};
        std::vector<std::thread> workers;
        for (unsigned thread=0;thread<8;++thread) {
            workers.emplace_back([&] {
                for (unsigned index=0;index<2000;++index) {
                    if (read_w(original)!="modified" || read_a(original)!="modified" || read_w(other)!="other")
                        ++failures;
                }
            });
        }
        for (auto& worker:workers) worker.join();
        check(failures.load()==0,"parallel routing failed");
        check(DeleteFileW(replacement.c_str())==0 && GetLastError()==ERROR_SHARING_VIOLATION,
              "active artifact was not protected against deletion");
        HANDLE modifier=CreateFileW(replacement.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                                   nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        check(modifier==INVALID_HANDLE_VALUE && GetLastError()==ERROR_SHARING_VIOLATION,
              "active artifact was not protected against writes");
        HANDLE retained=CreateFileW(original.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                                   nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        check(retained!=INVALID_HANDLE_VALUE,"retained handle failed");
        check(remove()==ERROR_SUCCESS,"remove failed");
        check(read_w(original)=="base","original read not restored");
        check(read_a(original)=="base","original ANSI read not restored");
        check(read_w(unicode)=="unicode-base","original Unicode read not restored");
        char retained_data[32]={}; DWORD retained_size=0;
        check(ReadFile(retained,retained_data,sizeof(retained_data),&retained_size,nullptr)!=0 &&
              std::string(retained_data,retained_size)=="modified","existing handle semantics changed");
        CloseHandle(retained);
        write(replacement,"modified");
        DWORD handles_before=0,handles_after=0;
        check(GetProcessHandleCount(GetCurrentProcess(),&handles_before)!=0,"handle count unavailable");
        for (unsigned cycle=0;cycle<100;++cycle) {
            check(install(routes,2)==ERROR_SUCCESS,"repeat install failed");
            check(read_w(original)=="modified","repeat route failed");
            check(remove()==ERROR_SUCCESS,"repeat remove failed");
            check(read_w(original)=="base","repeat restore failed");
        }
        check(GetProcessHandleCount(GetCurrentProcess(),&handles_after)!=0 && handles_after==handles_before,
              "install/remove leaked handles");
        CloseHandle(base);
        check(FreeLibrary(dll)!=0,"FreeLibrary failed");
        std::cout << "{\"scope\":\"own_process_only\",\"parallel_reads\":48000,\"failures\":0,"
                     "\"wide\":true,\"ansi\":true,\"unicode\":true,\"writes_not_redirected\":true,"
                     "\"restored\":true,\"artifact_pinned\":true,\"existing_handles_preserved\":true,"
                     "\"install_remove_cycles\":100,\"relative_paths\":true,\"overlapped_reads\":true,"
                     "\"handle_leaks\":0,\"game_runtime_available\":false}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
