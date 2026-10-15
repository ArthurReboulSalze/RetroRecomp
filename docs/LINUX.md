# Retro-Recomp on Linux

This first native package targets **Linux x86-64, built on Debian 13
(glibc 2.41)**. Older distributions and ARM64 are not qualified yet. It uses the
same console implementations and verified compilation knowledge as Windows.

Extract the archive into a writable local folder. Run `./Retro-Recomp` (or make
it executable with `chmod +x Retro-Recomp`). Python is included; no virtual
environment is needed to open the converter. To create or refresh a local
launcher with its icon after moving the folder, run
`./Retro-Recomp _install-launcher`. Dolphin may ask you to trust that launcher.
Generated games have their own cover launchers beside their native executables.

Conversion still requires the native build tools: `build-essential`, `cmake`,
`ninja-build`, `git`, `pkg-config`, `curl`, Rust/Cargo and the SDL2 development
dependencies used by the selected console. See [BUILDING.md](BUILDING.md).
Keep Linux and Windows compiler caches separate. The package contains no ROM
or BIOS. Supply your own game files and, for Neo Geo, your BIOS.

Drag ROMs or folders into the main window, including filenames with spaces or
accents. The converter identifies consoles automatically and ignores duplicate
queue entries. Drops do not change a conversion already in progress.
The main window can shrink to 640 pixels high; the ROM list and log shrink with
it, while the action buttons remain accessible.

Cover downloads use the same front-cover preference, cache and curated links
as Windows. Public downloads need no account. Optional API credentials in
Options use the desktop's **Secret Service keyring** (for example GNOME Keyring
or a compatible KWallet service). Open and unlock that keyring first. If it is
unavailable, credentials are not saved as plaintext. The settings file holds
only a random keyring reference. API access requirements of each provider
still apply; Arcade Italia has no credential fields.

Use **Check for updates** to request a GitHub update. There is no startup check.
Only the Linux x86-64 asset is selected; its size, SHA-256, ELF architecture and
reported version are checked before installation. A temporary helper waits for
the converter to close, replaces it and restarts it. Installation failure rolls
back to the previous converter. `datas`, generated games and the local
compilation library are preserved.
In-game visual quality, gameplay, controller behavior and physical latency must
be checked on the target machine; compilation validation is a separate check.

## Build the package

Use native Linux Python 3.13 with Tk installed. In a virtual environment, install
`requirements.txt` and `PyInstaller==6.22.3`, then run
`python tools/package_linux.py`. The build audits allowlisted resources and all
compiled Retro-Recomp Python modules before replacing `Export/Retro-Recomp`.
The `.build/linux-package/audit.json` report records the executable hash and
build platform. The tarball contains only the converter and two usage/build guides.
