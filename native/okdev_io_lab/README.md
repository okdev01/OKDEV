# Original OKDEV Windows file-I/O experiment

This is an independently written prototype, not LTK, CSLOL, a game injector,
or a playable skin runtime. It patches only the import table of our own
`OKDEV_Engine_Harness.exe` in the current process. Initialization refuses a
different process name. It has no external-process memory/thread API and does
not change signatures, cryptographic verification, anti-cheat or game files.

## What was tested

- Actual `CreateFileW` and `CreateFileA` calls redirect exact configured paths.
- Absolute, relative, case-insensitive and Unicode paths work in the fixture.
- Read-only opens redirect; write/creation requests retain ordinary behavior.
- Replacement files are pinned read-only while routes are active.
- Asynchronous/overlapped reads and memory-mapped reads work in our process.
- 48,000 parallel fixture reads complete without incorrect contents.
- 100 install/remove cycles leave the process handle count unchanged.
- A deliberately failed second patch rolls back the first and permits retry.
- A host missing a required import is rejected without changing reads or
  retaining artifact locks.
- A real Kayn archive and independently generated replacement were copied to
  a fixture. Redirected W/A/mapped SHA-256 matched the prepared artifact; the
  original installation archive's SHA-256 remained unchanged.

## Lifecycle and limits

The caller must stop/join its reading threads before removing routes and
unloading this DLL. Removing routes affects future opens; already opened
replacement handles keep their normal Windows lifetime and file contents.
This does not intercept arbitrary modules, dynamically resolved functions,
direct system calls, file verification, or the game's archive loader.
UNC/device paths, alternate streams and drive-relative paths are unsupported.
Configuration paths must be absolute. All paths and buffers are trusted caller
inputs; these exported C functions are not an untrusted IPC boundary.

## Build and run

Run `python scripts/build_io_lab.py` with MSVC x64 tools installed. A real-WAD
check additionally accepts `--original-wad PATH --replacement-wad PATH`.
Outputs and reports go under `output/io-lab` and `output/io-lab-validation.json`.
The test-only fault DLL under `output/io-lab/testing` is not a production build.

`python engine_cli.py native-check BUILD_DIRECTORY --game GAME_DIRECTORY
--lab-directory output/io-lab --report REPORT.json` validates an existing
prepared selection through the fixture. Enter the command on one line.
It validates archive/source hashes and returns `applied: false` and
`game_ready: false`, even when the fixture succeeds.

## Compatibility investigation

The installed game has static imports for both CreateFile variants. Read-only
Windows mitigation-policy queries succeeded and returned zero for the inspected
policies. Neither observation establishes game code loading, anti-cheat
compatibility, archive acceptance or successful skin rendering.

## Primary API references

- https://learn.microsoft.com/en-us/windows/win32/debug/pe-format
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
- https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect
- https://learn.microsoft.com/en-us/windows/win32/seccng/creating-a-hash-with-cng
