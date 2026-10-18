# Game Gear profile

RetroRecomp recognizes `.gg` cartridges and ZIP files containing exactly one
Game Gear cartridge. The original ROM is read without modification. Generated
games use the Game Gear's 12-bit CRAM colors, Start input, stereo port and one
controller. They are exported to `Export/Games/Game Gear`, with a separate
converter library and save-state machine ID from Master System games.

The displayed image is always the console's native **160 × 144 LCD window**.
The VDP works on a larger raster internally, but this version deliberately
does not reveal off-screen pixels or patch games. This avoids incomplete
graphics at the borders and keeps the result faithful to the handheld's
visible area. See the [Game Gear VDP technical reference](https://www.smspower.org/Development/GGVDP)
and [Sega's hardware documentation](https://www.smspower.org/Development/GGOfficialDocs).

The 18 October qualification, included in 1.1.3, adds twelve exact cartridges: Sonic,
Sonic 2, Tails Adventures, GG Aleste, Gunstar Heroes, Dynamite Headdy, OutRun,
Super Columns, Vampire / Master of Darkness, Wonder Boy: The Dragon's Trap,
Crystal Warriors and Streets of Rage II. Advanced conversions pass their
strict CPU/VDP gates. Replaying both 3,600-frame routes from every compressed
export gives 86,400 native/reference frame pairs with matching CPU, RAM, VDP
traces and final images, with no fallback on these routes. Source archives
are unchanged. Their numeric records extend the shared Game Gear bank from
one to thirteen exact revisions; they are not a cartridge allowlist.

These targeted automated checks do not
establish complete game compatibility or hardware fidelity. Native code
coverage, CPU agreement, hardware fidelity, gameplay and physical latency
remain separate measures.
