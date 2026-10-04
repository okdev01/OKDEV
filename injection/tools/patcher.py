#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LTK patcher binaries (ltk_patcher_host.exe + ltk_patcher_dll.dll).

Users provide their own copy (e.g. from an LTK Manager install); Rose does
not ship or pin them. The DLL refuses game builds newer than its built-in
end-of-life date, so we read that date to fail early instead of silently
injecting nothing.
"""

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LTK_PATCHER_HOST = "ltk_patcher_host.exe"
LTK_PATCHER_DLL = "ltk_patcher_dll.dll"

# Log line the DLL prints when the game build is newer than its EOL date
_EOL_MESSAGE = b"end of life reached, please update: "
# How far before the message reference to look for the EOL comparison
_EOL_SEARCH_WINDOW = 0x100


@dataclass
class LtkPatcherStatus:
    host: Path
    dll: Path
    missing: list
    eol: Optional[int]  # Unix timestamp, None if it could not be read
    game_build: Optional[int] = None

    @property
    def expired(self) -> bool:
        # The native DLL compares the game's PE timestamp, not the wall clock.
        # If the game cannot be inspected yet, let the DLL check it at launch.
        return (self.eol is not None and self.game_build is not None
                and self.game_build > self.eol)


def check_ltk_patcher(tools_dir: Path, game_exe: Optional[Path] = None) -> LtkPatcherStatus:
    """Report which LTK patcher files are missing and the DLL's EOL date."""
    host = tools_dir / LTK_PATCHER_HOST
    dll = tools_dir / LTK_PATCHER_DLL
    missing = [p.name for p in (host, dll) if not p.is_file()]
    eol = read_dll_eol(dll) if dll.is_file() else None
    game_build = read_game_build(game_exe) if game_exe is not None else None
    return LtkPatcherStatus(host=host, dll=dll, missing=missing, eol=eol,
                            game_build=game_build)


def read_game_build(game_exe: Path) -> Optional[int]:
    """Read the COFF TimeDateStamp used by the native patcher compatibility check."""
    try:
        with game_exe.open('rb') as stream:
            if stream.read(2) != b'MZ':
                return None
            stream.seek(0x3C)
            pe_offset = struct.unpack('<I', stream.read(4))[0]
            if pe_offset < 0x40:
                return None
            stream.seek(pe_offset)
            header = stream.read(12)
            if header[:4] != b'PE\0\0':
                return None
            return struct.unpack_from('<I', header, 8)[0]
    except (OSError, ValueError, struct.error):
        return None


def read_dll_eol(dll_path: Path) -> Optional[int]:
    """Return the EOL timestamp compiled into the LTK patcher DLL.

    The DLL compares the game executable's PE build timestamp against a
    constant (``cmp eax, imm32; jbe``) right before referencing the
    "end of life reached" message. We locate that message, find the code that
    loads it, and read the nearest preceding comparison constant.
    """
    try:
        data = dll_path.read_bytes()
        sections = _parse_sections(data)
    except (OSError, ValueError, struct.error):
        return None

    msg_offset = data.find(_EOL_MESSAGE)
    if msg_offset < 0:
        return None
    msg_rva = _offset_to_rva(sections, msg_offset)
    text = next((s for s in sections if s[0] == b".text"), None)
    if msg_rva is None or text is None:
        return None

    _, text_rva, text_size, text_raw = text
    code = data[text_raw:text_raw + text_size]
    for i in range(len(code) - 7):
        # lea r64, [rip + disp32]
        if code[i] not in (0x48, 0x4C) or code[i + 1] != 0x8D or (code[i + 2] & 0xC7) != 0x05:
            continue
        disp = struct.unpack_from("<i", code, i + 3)[0]
        # Newer Rust format templates prefix the text with its length
        if not 0 <= msg_rva - (text_rva + i + 7 + disp) <= 16:
            continue
        eol = _find_eol_compare(code, i)
        if eol is not None:
            return eol
    return None


def _find_eol_compare(code: bytes, lea_index: int) -> Optional[int]:
    """Find the closest ``cmp eax, imm32; jbe rel32`` before the message load."""
    start = max(0, lea_index - _EOL_SEARCH_WINDOW)
    for j in range(lea_index - 11, start - 1, -1):
        if code[j] == 0x3D and code[j + 5] == 0x0F and code[j + 6] == 0x86:
            return struct.unpack_from("<I", code, j + 1)[0]
    return None


def _parse_sections(data: bytes):
    """Return (name, rva, raw_size, raw_offset) for each PE section."""
    if data[:2] != b"MZ":
        raise ValueError("not a PE file")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + opt_size
    sections = []
    for k in range(count):
        entry = table + k * 40
        name = data[entry:entry + 8].rstrip(b"\0")
        rva, raw_size, raw_offset = struct.unpack_from("<III", data, entry + 12)
        sections.append((name, rva, raw_size, raw_offset))
    return sections


def _offset_to_rva(sections, offset: int) -> Optional[int]:
    for _, rva, raw_size, raw_offset in sections:
        if raw_offset <= offset < raw_offset + raw_size:
            return offset - raw_offset + rva
    return None
