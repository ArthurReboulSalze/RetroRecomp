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

Game Gear coverage is new and has had only targeted automated conversion
checks. Matching the reference CPU and shared VDP on a short scenario does not
establish complete game compatibility or hardware fidelity. Native code
coverage, CPU agreement, hardware fidelity, gameplay and physical latency
remain separate measures.
