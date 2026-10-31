# OKDEV independent engine

The first component is an offline Fantome package inspector. It reads archive
metadata, checks path safety and resource limits, and inventories WAD payloads.
It does not extract files, load DLLs, modify the game, or invoke LTK/mod-tools.

Run: `.venv/Scripts/python.exe -m engine path/to/package.fantome`

The report explicitly marks runtime support unavailable and game compatibility
unchecked. Archive checks do not establish whether a skin works in game.

Implemented: WAD v3 indexing, bounded raw/gzip/Zstandard/subchunk reads,
offline override planning and archive generation, payload verification,
session-bound selection capture, nested chroma resolution and durable manifests.
There is currently **no independent in-game runtime implementation**.

## WAD inspection and override planning

`python -m engine.plan package.fantome original.wad.client` reads a WAD v3
table from both archives and reports matching and newly added path hashes.
It validates table bounds, payload ranges, duplicate hashes and compression
identifiers. It does not decompress payloads or certify their contents.
Format reference: https://github.com/CommunityDragon/CDTB/blob/master/cdtb/wad.py

Verified locally with the installed Kayn archive (3,031 entries) and the
HEARTSTEEL Live My Life Kayn package (one replacement, no added hashes).
This verifies file parsing and planning only, not skin application.

## Product contract

Keep the existing champion-select skin catalogue and selection UI. A selection
must retain champion ID, requested skin ID and game-session identity. Never
report application success merely because a package was prepared or a process
started. Independent runtime support must remain unavailable until verified in
a practice game; offline tooling must not be selected as a production runtime.

## Remaining dependencies

The production application still uses `injection/overlay/overlay_manager.py`
with mod-tools for overlay construction and the LTK host/DLL for application.
The modules in this directory do not yet replace that production path.
The independent writer currently produces unsigned offline artifacts, not
game-ready overlays. Runtime integration and game compatibility remain
unimplemented. Removing the old imports before those replacements work would
disable skin application entirely.

## Independent archive builder

`python -m engine.build package.fantome original.wad.client output.wad`
creates a separate, unsigned offline archive with replacements merged by path
hash. Existing destinations and source paths cannot be overwritten. Payloads
are copied in bounded blocks; the output table is checked after writing.
Compression and subchunk metadata are preserved without decompressing content.
Chunked replacements, redirects and changes to the known shared subchunk table
are rejected until normalization is implemented. Replacement payloads are
decompressed and checked before output; every stored output payload is compared
to its source. This does not establish game compatibility.

The local Kayn build produced 112,625,523 bytes and 3,031 entries. All output
payloads were compared by SHA-256 against the original or replacement source.
This artifact is **not game-ready**: its signature/checksum fields are zeroed,
and there is no runtime to apply it. Do not copy it into the game installation.

## Existing champion-select integration

The existing `SkinProcessor` captures the normal client's chosen skin into an
immutable `Selection` containing champion, skin and champion-select generation.
Leaving champion select or starting a new generation clears that request.
The original UI and production injection path remain in place. Capture alone
does not start a build or apply a skin; `engine.bridge.prepare_current` is an
explicit offline developer operation and rejects superseded results.

`python main.py --engine-prepare --session-id test --champion-id 141
--skin-id 141032 --library PATH_TO_SKINS --game PATH_TO_GAME --output OUTPUT`
runs preparation without starting the app UI, LTK or the game. Enter the command
on one line. Outputs must be outside the library and game directories.

Nested chroma packages are resolved by exact ID. Unavailable optional voice
locales are recorded in the manifest and skipped; missing non-locale archives
abort preparation. Original game fingerprints are checked before and after
building. `engine.validate.validate` rejects modified or superseded outputs and
can require the current game fingerprint and exact selection identity.

## Independent Windows developer build

`engine_cli.py` is packaged as `OKDEV_Engine_Experimental.exe`. It has commands
`status`, `inspect`, `plan`, `build`, `prepare`, `verify`, and `native-check`. The executable
does not bundle or call LTK or mod-tools. Its status explicitly reports
`runtime_available: false` and `game_ready: false`.

This is developer tooling, **not a replacement for the playable OKDEV app**.

The optional original DLL under `native/okdev_io_lab` redirects file reads only
in our own named fixture executable. `native-check` validates the requested
selection, the manifest and source fingerprints before and after that fixture.
It verifies native W/A and memory-mapped read hashes, but always returns
`applied: false`. It does not load the DLL into League. See that directory's
README for native tests and lifecycle restrictions.

## Local verification

- 9,096 local packages were audited. 9,094 complete-WAD packages passed index
  and decompression validation. Two loose-file Sett variants are unsupported.
- One supported carrier per champion was built and verified: 173/173 passed.
  Generated validation archives were removed after each case.
- The packaged Windows executable prepared and verified the real Kayn carrier.
- Unit tests cover malformed paths, table bounds, content corruption, compressed
  frame truncation, chromas, stale selections, game updates and incomplete builds.

Reports are under `output/independent-engine-*.json`; these checks are offline
and do not claim successful in-game application.
