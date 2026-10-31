#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tools Manager
Handles CSLOL tools detection and validation
"""

from pathlib import Path
from typing import Dict, Optional

from utils.core.logging import get_logger

log = get_logger()

from .patcher import LTK_PATCHER_DLL, LTK_PATCHER_HOST


class ToolsManager:
    """Manages CSLOL tools detection and validation"""
    
    def __init__(self, tools_dir: Path, game_exe: Optional[Path] = None):
        self.tools_dir = tools_dir
        self.game_exe = game_exe
    
    def check_tools_available(self) -> bool:
        """Check if the runtime injection tool is present."""
        required_tools = [
            "mod-tools.exe",
            "cslol-dll.dll",  # OKDEV's stand-in; mod-tools.exe will not start without it
        ]
        missing_tools = []
        if not self.detect_ltk_patcher():
            missing_tools.extend([LTK_PATCHER_HOST, LTK_PATCHER_DLL])
        for tool in required_tools:
            if not (self.tools_dir / tool).exists():
                missing_tools.append(tool)
        
        if missing_tools:
            log.warning(f"Missing runtime injection dependencies: {missing_tools}")
            log.warning("Please place the missing files in injection/tools/")
            return False
        
        return True
    
    def detect_tools(self) -> Dict[str, Path]:
        """Detect runtime injection tools."""
        tools = {
            "modtools": self.tools_dir / "mod-tools.exe",
        }
        for name, exe in tools.items():
            if not exe.exists():
                log.error(f"[INJECTOR] Missing tool: {exe}")
        return tools

    def detect_ltk_patcher(self) -> Optional[Path]:
        """Return the LTK patcher host if it is installed next to its hook DLL.

        The LTK Manager patcher (ltk_patcher_host.exe + ltk_patcher_dll.dll)
        serves the overlay built by mkoverlay. Users provide their own copy.
        """
        from okdev_ltk_delivery import resolve_patcher_dir
        directory = resolve_patcher_dir(self.tools_dir, self.game_exe)
        host = directory / LTK_PATCHER_HOST
        if host.exists() and (directory / LTK_PATCHER_DLL).exists():
            return host
        return None

