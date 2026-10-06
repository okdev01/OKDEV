# Vendored Pengu Loader sources

Upstream: https://github.com/PenguLoader/PenguLoader
Tag: v1.1.6; commit: 4d641f52bc5d70aac4c09dfa1fa7a043a9069aff.
CEF headers: https://github.com/PenguLoader/cef-headers
Pinned commit: b85f32a2b40a6dbc50ef4c0bacee4ec681d4884f (CEF 108).

The core, loader and embedded frontend are built from source. MIT licenses are retained.
OKDEV modifications: branding/icons, owned update channel, CLI activation adapter,
registry API handling, LOCALAPPDATA/OKDEV/config.ini loader path and disabled flag,
null command-line guard. Embedded component update checks are disabled: the
application launcher manages the complete package as a unit.

Third-party identifiers such as window.Pengu and the Pengu Loader executable name
remain API integration names, not Rose dependencies. The old precompiled Rose core
is not used by scripts/build_pyinstaller.py.
