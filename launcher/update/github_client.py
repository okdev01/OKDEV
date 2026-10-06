"""
GitHub Client
Handles GitHub API interactions for release checking
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse
import re

import requests

from utils.core.logging import get_logger

log = get_logger()

GITHUB_RELEASE_API = "https://api.github.com/repos/okdev01/OKDEV/releases/latest"


class GitHubClient:
    """Client for interacting with GitHub API"""
    
    def __init__(self, timeout: int = 20):
        self.timeout = timeout
    
    def get_latest_release(self) -> Optional[dict]:
        """Get the latest release information from GitHub
        
        Returns:
            Release data dictionary or None if failed
        """
        try:
            response = requests.get(GITHUB_RELEASE_API, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            log.warning("Update check failed while fetching latest release: %s", e)
            return None
    
    def get_release_version(self, release: dict) -> str:
        """Extract version string from release data"""
        return release.get("tag_name") or release.get("name") or ""
    
    def get_zip_asset(self, release: dict) -> Optional[dict]:
        """Get the ZIP asset from release data"""
        version = self.get_release_version(release).removeprefix("v")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            return None
        expected = f"OKDEV_Update_{version}.zip"
        return next((a for a in release.get("assets", [])
                     if a.get("name") == expected and self.is_release_url(a.get("browser_download_url", ""))), None)

    @staticmethod
    def is_release_url(url):
        parsed = urlparse(url)
        return (parsed.scheme == "https" and parsed.netloc == "github.com"
                and parsed.path.startswith("/okdev01/OKDEV/releases/download/"))

    def get_hash_asset(self, release: dict) -> Optional[dict]:
        """Get the hash file asset from release data"""
        assets = release.get("assets", [])
        return next((a for a in assets if a.get("name", "").lower() == "hashes.game.txt"), None)

