# Runtime investigation — 2026-10-31

## What is actually missing

The installed game does not automatically read arbitrary WAD files from an
OKDEV output folder. Producing those files is separate from getting the game
to use them. Our independent writer deliberately emits unsigned artifacts;
copying them into the installation is not a supported runtime solution.

The existing production path uses mod-tools for preparation and LTK's
host/DLL for application. The local `native/cslol_stub` is only a loader stub:
its exports return errors, so it cannot serve as an alternative game runtime.

The publicly available CSLOL Windows wrapper also calls a separately supplied
DLL. Building that wrapper would not provide an independent implementation of
the game-facing code. There is still no replacement game runtime. A separate
original native prototype under `native/okdev_io_lab` now redirects reads in
our own controlled fixture executable only; it deliberately refuses the game.

## Directly observed evidence

1. Existing OKDEV launch: `host verification failed, refusing overlay`,
   `VRF00000008`.
2. Official LTK 1.32.0 with the same HEARTSTEEL Kayn carrier: DLL attached,
   then `overlay verification failed, disabling overlay`; base-skin check
   reported another Kayn skin's mesh. The incident verdict was
   `SkinhackDetected`; LTK explicitly stated no mods were applied.
3. The independent archive pipeline built the carrier without invoking LTK.
   That demonstrates preparation only, not runtime application.

## Acceptance criteria before claiming the requested app works

- Start from the existing normal champion-select choice; preserve skin/chroma ID.
- Prepare against the current installed game and reject stale requests.
- Apply using an independently implemented, compatible runtime.
- Verify the selected appearance in a practice game, including game restarts.
- Confirm original installation files remain unchanged and failures reach the UI.
- Only then build and publish a playable update.

## Primary sources consulted

- WAD format implementation reference:
  https://github.com/CommunityDragon/CDTB/blob/master/cdtb/wad.py
- Public Windows wrapper (calls a separate DLL):
  https://github.com/LeagueToolkit/cslol-manager/blob/master/cslol-tools/lib/lol/patcher/patcher_win32.cpp
- Overlay preparation versus runtime explanation:
  https://github.com/LeagueToolkit/docs/blob/main/How-Patching-Works.md
- Separate LTK binary license:
  https://github.com/LeagueToolkit/ltk-manager/blob/main/LTK-PATCHER-LICENSE.md

These references do not establish that our independent runtime is implemented
or that unsigned artifacts can be loaded into the current game.

## Second development session

An original Windows IAT-routing DLL and owned-process harness were compiled
with MSVC /W4 /WX. Real WAD data is read through wide, ANSI and memory-mapped
paths with matching SHA-256. Artifact locks, partial-install rollback,
unsupported import handling, relative paths, overlapped reads and handle
lifecycle were exercised. Reports remain explicitly marked not game-ready.
No code was loaded into League. A read-only process-policy query is not proof
that a DLL would be accepted by the game or its protection software.
