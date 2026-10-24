# Install Retro-Recomp

Installers and portable downloads contain the same converter. No ROM, BIOS,
downloaded cover, save or personal compilation library is included. Installing
the converter does not install the native development tools needed to compile
games; see [BUILDING.md](BUILDING.md). Exported games need no development tools.

## Windows x64

Download `Retro-Recomp-1.1.8-windows-x64-setup.exe` from the
[1.1.8 release](https://github.com/ArthurReboulSalze/RetroRecomp/releases/tag/v1.1.8).
Run the setup wizard. The default is a per-user installation in
`%LOCALAPPDATA%\Programs\Retro-Recomp`, with a Start menu shortcut and an optional
desktop shortcut. It requires no administrator password. Keep a directory your
account can write to, so the in-app updater can replace the converter.

The installer is not code-signed. Windows may show its usual downloaded-app
warning. Release checksums are provided in `SHA256SUMS.txt`.

Uninstall through Windows Settings or the Start menu entry. Games, `datas`,
compiler dependencies and build caches are kept. You can remove those separately
if you no longer need them. Installing again in the same location reuses them.

## Linux x86-64

**Debian, Ubuntu and derivatives (simplest):** download
`retro-recomp_<version>_amd64.deb` from the release and double-click it: the
software center installs it after asking for your password (or run
`sudo apt install ./retro-recomp_<version>_amd64.deb`). Retro-Recomp then
appears in your applications menu. The package puts the application in
`/opt/retro-recomp`; on first start, each user gets a private copy in
`~/.local/opt/Retro-Recomp`, where settings, games and compiler caches are
kept and where **Check for updates** keeps working without a password. A newer
package refreshes that copy on the next start. Removing the package
(`sudo apt remove retro-recomp`) keeps every user's copy and data.

**Any distribution (per-user `.run` installer):** download
`Retro-Recomp-<version>-linux-x86_64-install.run` from the same release. Browsers
remove the execute permission from downloads, so a double-click does nothing:
run it in a terminal as your normal desktop user, **without sudo** (the
installer refuses sudo, since it installs in your home folder):

```sh
bash Retro-Recomp-1.1.8-linux-x86_64-install.run
```

Confirm installation in `~/.local/opt/Retro-Recomp`. The installer checks its
payload and the native converter before installing, then adds **Retro-Recomp**
to your applications menu with its icon. To choose another new, writable folder:

```sh
bash Retro-Recomp-1.1.8-linux-x86_64-install.run --prefix "$HOME/Applications/Retro-Recomp"
```

`--yes` skips the confirmation for unattended installation. Re-running the
installer in its existing installation folder keeps your data. A folder without
the installation marker is refused to avoid taking over an unrelated directory.
The installer needs Bash, the usual GNU utilities and **glibc 2.41 or newer**;
the native application is checked on **Debian 13 x86-64**. Other distribution
baselines and ARM64 remain unqualified. Python is included in the converter.

To uninstall while keeping all games, settings and learning data:

```sh
"$HOME/.local/opt/Retro-Recomp/uninstall.sh"
```

Use your chosen prefix instead if you installed elsewhere. The uninstaller
removes only its managed program files and matching application-menu entry.
Close the converter and any conversions before installation or uninstall.

## Updates and existing portable data

Use **Check for updates** inside the installed application. When a newer
version exists, the dialog shows what changed since your version (the
published release notes of every skipped version, in English) before you
choose to download it. The Windows installer shows the same notes before
installing. The update downloads the
matching native converter, checks size, SHA-256, architecture and version, then
replaces only the application and restarts it. You do not need to download the
installer again for a converter update. The install location and shortcuts remain
unchanged. An installed current version offers no update to itself.

Settings, favorites, cards, downloaded covers and compilation observations stay
in `datas` in the installation folder; generated games default to `Games` there.
The installer and updater preserve these directories, including your private
compilation library. Uninstall also leaves them in place. Back them up if needed.

An existing portable installation is not imported automatically. You can keep
using it, or close both copies and copy its `datas` and `Games` into the new
installation before first use. Leave your ROMs where they are. Set per-console
ROM/export folders in Options; rescan games or repair paths after moving them.
Do not share compiler caches between Windows and Linux.

## Build installers

First build and audit the native converter for the target OS. The installer
builder copies only that binary, the app icon, notices and installation guide;
it never collects a directory of local exports or user data.

Windows uses [Inno Setup 6.7.3](https://jrsoftware.org/isdl.php), with
[`PrivilegesRequired=lowest`](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
for per-user installation. Run on Windows:

```powershell
python -B tools/package_installers.py --target windows --version 1.1.8 --executable Export/Retro-Recomp.exe --output .build/installers --iscc "path/to/ISCC.exe"
```

Build the Linux installer on Linux, using the already audited native binary:

```sh
python3 -B tools/package_installers.py --target linux --version 1.1.8 --executable Export/Retro-Recomp --output .build/installers
```

Launchers follow the [Desktop Entry specification](https://specifications.freedesktop.org/desktop-entry/latest-single/).
The `.audit.json` next to each built installer records its SHA-256 and each
payload file. Release checksums cover the installers as well as the portable
assets. Build tools and private audit receipts are not release assets.
