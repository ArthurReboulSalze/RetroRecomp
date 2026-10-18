# Final local review — 18 October 2026

This pass follows the development after 1.1.2. It does not publish a release,
scan a game collection, or change the qualified knowledge snapshot. Tests use
authored data and compiler fixtures; there are no new commercial-game runs.

## Findings by console

| Profile | Review and changes |
| --- | --- |
| Master System | Existing exact-cartridge learning and guarded entries retained. Shared export naming now terminates for colliding long titles; ownership recovery uses bounded buffers. No additional CPU, audio or video shortcut introduced. |
| Game Gear | Same shared fixes as Master System, with its own console namespace preserved. The preceding qualified Game Gear observations are unchanged. |
| Game Boy | Concurrent learning writes merge under an OS lock. A checked backup preserves the previous trace if the manifest commit is interrupted; it is removed after a successful commit. Repeated observations do not rewrite the trace. No individual cartridge debugging or SM83 translation change. |
| NES | ROM entries and guarded RAM variants are merged with the latest library under a lock, then replaced atomically. A finishing conversion no longer overwrites discoveries made by another conversion. Source/checksum reads use bounded buffers. |
| Mega Drive | Adapter fingerprints use canonical code content in both source and packaged runs. Temporary paths and differences in constant sharing cannot invalidate identical generated-code caches. The prior invalid-bank feedback bound remains. Further Sonic performance work stays paused. |
| Super Nintendo | The same canonical fingerprints stabilize source/packaged adapter and state identities. Existing SPC knowledge compaction, runtime checks and state-layout guards remain. This does not authorize loading arbitrary older save-state formats. |
| Neo Geo | Canonical adapter identities and bounded export-ownership reads help large exports. Cartridge/BIOS identity, board checks, native guards and validation routes remain unchanged. No new cartridge campaign. |

## Shared Windows and Linux behavior

- Long filenames reserve the numeric collision suffix before truncation.
  Linux names respect a UTF-8 byte budget; Windows names also account for UTF-16
  surrogate pairs. Existing unrelated exports remain protected.
- The library lock has a real timeout on Linux as well as Windows. A busy
  library produces an error instead of waiting indefinitely; lock release is
  checked with a separate process.
- Ownership detection retains the exact marker/ambiguity rules, including
  markers split across read buffers. Legacy SHA scanning runs only when needed.
- Several corrupted French batch messages have their accents restored.
- These changes do not shorten reference checks, disable fallback reporting,
  remove runtime byte guards, or alter guest CPU clocks, PCM or pixels.

## Evidence and limits

On an authored **64 MiB file**, the Python temporary peak for export identity
recovery falls from **67,116,150 to 3,284,749 bytes**. NES source hashing falls
from **67,109,661 to 395,169 bytes**, with the same SHA-256. These are converter
working-set measurements, not game framerate or physical-latency measurements.

The **519-test Python suite passes** on Windows (one platform-specific skip)
and Debian (14 skips). Dedicated cases cover eight concurrent GB/NES writers,
interrupted GB manifest commits, failed atomic replacement, cross-process lock
timeouts, long Unicode filenames and source/loaded-code identity. The actual
native fallback recorder is checked separately for exit-only writes and merging.

Both local converter packages build and pass the embedded-content audit: **271
bundled resources have identical hashes** and the same 99 application modules
are present on Windows and Linux. All seven profile fingerprints match their
source build on two consecutive packaged launches. A separate check compares
15 actual packaged adapter code objects with their source identities on each OS.
These are private development previews, not a published release or an update
installed over the user's exports.

The snapshot remains **1,105 exact identities**, including the same 606 Game Boy
records. No observations are promoted by these authored tests. Local evidence is
under `.build/final-review-20261018`; Debian evidence uses
`evidence/final-review-20261018`.

Runtime save-state compatibility still requires the same cartridge, region and
supported runtime ABI. No cross-version save-state migration is inferred from
stable compiler fingerprints. This review does not qualify full gameplay,
real-world framerate, physical latency, other Linux distributions or ARM64.
