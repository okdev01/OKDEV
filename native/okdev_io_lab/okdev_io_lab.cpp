// Original OKDEV file-I/O experiment. No external-process injection, signature
// manipulation, game support, drivers or dependency on LTK/CSLOL.
#include "okdev_io_lab.h"
#include <string>
#include <vector>
#include <shared_mutex>
#include <mutex>
#include <algorithm>
#include <cstring>
#include <memory>
#ifdef OKDEV_IO_TEST_FAULT
#include <atomic>
#endif

namespace {
using OpenWide = decltype(&CreateFileW);
using OpenAnsi = decltype(&CreateFileA);
OpenWide real_w = &CreateFileW;
OpenAnsi real_a = &CreateFileA;
std::shared_mutex routes_mutex;
std::mutex install_mutex;
std::vector<std::pair<std::wstring,std::wstring>> routes;
std::vector<std::shared_ptr<void>> pinned_files;
struct Slot { void** address; void* previous; void* replacement; };
std::vector<Slot> patched;

bool canonical(const wchar_t* path, std::wstring& result,bool allow_relative=false) {
    if (!path) return false;
    size_t length=wcsnlen(path,32761);
    if (length>32760 || !length) return false;
    if (length>=2 && (path[0]==L'\\' || path[0]==L'/') &&
        (path[1]==L'\\' || path[1]==L'/')) return false; // no UNC/devices
    bool absolute=length>=3 && path[1]==L':' && (path[2]==L'\\' || path[2]==L'/');
    if (!allow_relative && !absolute) return false;
    if (length>=2 && path[1]==L':' && !absolute) return false; // no drive-relative paths
    DWORD count = GetFullPathNameW(path,0,nullptr,nullptr);
    if (!count || count>32767) return false;
    std::wstring buffer(count,L'\0');
    DWORD written=GetFullPathNameW(path,count,buffer.data(),nullptr);
    if (!written || written>=count) return false;
    buffer.resize(written);
    std::replace(buffer.begin(),buffer.end(),L'/',L'\\');
    if (buffer.size()<3 || buffer[1]!=L':' || buffer.find(L':',2)!=std::wstring::npos) return false;
    result=std::move(buffer);
    return true;
}

bool equal(const std::wstring& left,const std::wstring& right) {
    return CompareStringOrdinal(left.c_str(),-1,right.c_str(),-1,TRUE)==CSTR_EQUAL;
}

bool redirect(const wchar_t* path,DWORD access,DWORD disposition,DWORD flags,std::wstring& target) {
    const DWORD writes=GENERIC_WRITE|GENERIC_ALL|MAXIMUM_ALLOWED|DELETE|WRITE_DAC|WRITE_OWNER|
        FILE_WRITE_DATA|FILE_APPEND_DATA|FILE_WRITE_EA|FILE_WRITE_ATTRIBUTES;
    if ((access&writes) || disposition!=OPEN_EXISTING || (flags&FILE_FLAG_DELETE_ON_CLOSE)) return false;
    std::wstring normalized;
    if (!canonical(path,normalized,true)) return false;
    std::shared_lock lock(routes_mutex);
    for (const auto& route:routes) {
        if (equal(normalized,route.first)) { target=route.second; return true; }
    }
    return false;
}

HANDLE WINAPI open_w(LPCWSTR path,DWORD access,DWORD share,LPSECURITY_ATTRIBUTES security,
                    DWORD disposition,DWORD flags,HANDLE template_file) noexcept {
    const DWORD incoming=GetLastError();
    try {
        std::wstring target;
        bool mapped=redirect(path,access,disposition,flags,target);
        SetLastError(incoming);
        return real_w(mapped?target.c_str():path,access,share,security,disposition,flags,template_file);
    } catch (...) { SetLastError(incoming); return real_w(path,access,share,security,disposition,flags,template_file); }
}

HANDLE WINAPI open_a(LPCSTR path,DWORD access,DWORD share,LPSECURITY_ATTRIBUTES security,
                    DWORD disposition,DWORD flags,HANDLE template_file) noexcept {
    const DWORD incoming=GetLastError();
    try {
        if (path) {
            int count=MultiByteToWideChar(CP_ACP,0,path,-1,nullptr,0);
            if (count>0 && count<32768) {
                std::wstring wide(static_cast<size_t>(count),L'\0');
                if (MultiByteToWideChar(CP_ACP,0,path,-1,wide.data(),count)) {
                    std::wstring target;
                    if (redirect(wide.c_str(),access,disposition,flags,target)) {
                        SetLastError(incoming);
                        return real_w(target.c_str(),access,share,security,disposition,flags,template_file);
                    }
                }
            }
        }
    } catch (...) {}
    SetLastError(incoming);
    return real_a(path,access,share,security,disposition,flags,template_file);
}

DWORD exchange(void** slot,void* value,void** previous) {
#ifdef OKDEV_IO_TEST_FAULT
    static std::atomic<unsigned> installations{0};
    if ((value==reinterpret_cast<void*>(&open_w) || value==reinterpret_cast<void*>(&open_a)) &&
        ++installations==2) return ERROR_ACCESS_DENIED;
#endif
    DWORD protection=0;
    if (!VirtualProtect(slot,sizeof(void*),PAGE_READWRITE,&protection)) return GetLastError();
    void* old=InterlockedExchangePointer(reinterpret_cast<PVOID volatile*>(slot),value);
    DWORD ignored=0;
    BOOL restored=VirtualProtect(slot,sizeof(void*),protection,&ignored);
    if (previous) *previous=old;
    return restored?ERROR_SUCCESS:GetLastError();
}

bool harness_process() {
    wchar_t executable[32768];
    DWORD size=GetModuleFileNameW(nullptr,executable,32768);
    if (!size || size>=32768) return false;
    const wchar_t* name=wcsrchr(executable,L'\\');
    return _wcsicmp(name?name+1:executable,L"OKDEV_Engine_Harness.exe")==0;
}

DWORD remove_slots() {
    DWORD result=ERROR_SUCCESS;
    for (auto iterator=patched.rbegin();iterator!=patched.rend();++iterator) {
        // Do not overwrite a third party's later modification of this slot.
        if (*iterator->address==iterator->previous) continue;
        if (*iterator->address!=iterator->replacement) { result=ERROR_BUSY; continue; }
        DWORD error=exchange(iterator->address,iterator->previous,nullptr);
        if (error) result=error;
    }
    if (!result) patched.clear();
    return result;
}
}

extern "C" __declspec(dllexport) DWORD __cdecl OKDEV_InstallForHarness(const OkdevRoute* input,size_t count) noexcept {
    try {
        std::lock_guard install(install_mutex);
        if (!harness_process()) return ERROR_ACCESS_DENIED;
        if (!patched.empty()) return ERROR_ALREADY_EXISTS;
        if (!input || !count || count>64) return ERROR_INVALID_PARAMETER;
        std::vector<std::pair<std::wstring,std::wstring>> prepared;
        std::vector<std::shared_ptr<void>> prepared_pins;
        for (size_t index=0;index<count;++index) {
            std::wstring original,replacement;
            if (!canonical(input[index].original,original) || !canonical(input[index].replacement,replacement)
                || equal(original,replacement)) return ERROR_INVALID_PARAMETER;
            if (original.size()<11 || _wcsicmp(original.c_str()+original.size()-11,L".wad.client")!=0)
                return ERROR_INVALID_PARAMETER;
            DWORD attributes=GetFileAttributesW(replacement.c_str());
            if (attributes==INVALID_FILE_ATTRIBUTES || (attributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)))
                return ERROR_FILE_NOT_FOUND;
            for (const auto& route:prepared) if (equal(route.first,original)) return ERROR_DUP_NAME;
            // Keep immutable inputs pinned while routing is active. The shared
            // read-only handle prevents writers/deletion replacing the artifact.
            HANDLE pinned=CreateFileW(replacement.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,
                                      OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
            if (pinned==INVALID_HANDLE_VALUE) return GetLastError();
            prepared_pins.emplace_back(pinned,[](void* handle){CloseHandle(handle);});
            prepared.emplace_back(std::move(original),std::move(replacement));
        }
        auto* module=reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
        auto* dos=reinterpret_cast<IMAGE_DOS_HEADER*>(module);
        if (dos->e_magic!=IMAGE_DOS_SIGNATURE || dos->e_lfanew<=0) return ERROR_BAD_EXE_FORMAT;
        auto* nt=reinterpret_cast<IMAGE_NT_HEADERS*>(module+dos->e_lfanew);
        if (nt->Signature!=IMAGE_NT_SIGNATURE) return ERROR_BAD_EXE_FORMAT;
        DWORD rva=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
        if (!rva) return ERROR_PROC_NOT_FOUND;
        std::vector<std::pair<void**,void*>> changes;
        for (auto* descriptor=reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(module+rva);descriptor->Name;++descriptor) {
            if (!descriptor->OriginalFirstThunk) continue;
            auto* names=reinterpret_cast<IMAGE_THUNK_DATA*>(module+descriptor->OriginalFirstThunk);
            auto* slots=reinterpret_cast<IMAGE_THUNK_DATA*>(module+descriptor->FirstThunk);
            for (;names->u1.AddressOfData;++names,++slots) {
                if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal)) continue;
                auto* imported=reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(module+names->u1.AddressOfData);
                if (!strcmp(reinterpret_cast<char*>(imported->Name),"CreateFileW")) {
                    real_w=reinterpret_cast<OpenWide>(slots->u1.Function);
                    changes.emplace_back(reinterpret_cast<void**>(&slots->u1.Function),reinterpret_cast<void*>(&open_w));
                } else if (!strcmp(reinterpret_cast<char*>(imported->Name),"CreateFileA")) {
                    real_a=reinterpret_cast<OpenAnsi>(slots->u1.Function);
                    changes.emplace_back(reinterpret_cast<void**>(&slots->u1.Function),reinterpret_cast<void*>(&open_a));
                }
            }
        }
        if (changes.size()!=2) return ERROR_PROC_NOT_FOUND;
        // Allocate before changing any pointers: an allocation failure must
        // never leave an untracked live hook behind.
        patched.reserve(changes.size());
        { std::unique_lock lock(routes_mutex); routes=std::move(prepared); pinned_files=std::move(prepared_pins); }
        for (const auto& change:changes) {
            void* previous=nullptr;
            DWORD error=exchange(change.first,change.second,&previous);
            // Even a protection-restore failure may already have exchanged it.
            if (previous) patched.push_back({change.first,previous,change.second});
            if (error) {
                if (!remove_slots()) {
                    std::unique_lock lock(routes_mutex);
                    routes.clear(); pinned_files.clear();
                }
                return error;
            }
        }
        return ERROR_SUCCESS;
    } catch (...) { return ERROR_NOT_ENOUGH_MEMORY; }
}

extern "C" __declspec(dllexport) DWORD __cdecl OKDEV_RemoveFromHarness() noexcept {
    try {
        std::lock_guard install(install_mutex);
        if (!harness_process()) return ERROR_ACCESS_DENIED;
        DWORD result=remove_slots();
        if (!result) { std::unique_lock lock(routes_mutex); routes.clear(); pinned_files.clear(); }
        return result;
    } catch (...) { return ERROR_NOT_ENOUGH_MEMORY; }
}
