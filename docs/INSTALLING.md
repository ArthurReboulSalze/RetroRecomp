# Install Retro-Recomp

Retro-Recomp turns the game files you own (cartridge dumps, arcade romsets, disk
images) into programs that start by themselves on your computer. This page
tells you which file to download, how to install it, and how to make your first
game. If you know nothing about it yet, read the first two sections and stop
there.

## Which file do I download?

Open the [latest release](https://github.com/ArthurReboulSalze/RetroRecomp/releases/latest)
and take the file that matches your computer:

| Your computer | File to download |
| --- | --- |
| Windows 10 or 11, 64-bit | `Retro-Recomp-<version>-windows-x64-setup.exe` |
| Debian, Ubuntu and derivatives | `retro-recomp_<version>_amd64.deb` (double-click it) |
| Another 64-bit Linux | `Retro-Recomp-<version>-linux-x86_64-install.run` (see [Linux](#linux-x86-64)) |

Portable downloads, which need no installation, are also on the release page.
Download Retro-Recomp only from [retro-recomp.com](https://retro-recomp.com) or
the project's GitHub releases. On Windows, the first launch may show a warning
about an unknown publisher: it is explained in
[Windows security warnings](#windows-security-warnings) and is not a virus
alert.

## Your first game

1. Start Retro-Recomp.
2. Add your ROMs or folders (you can drop them on the window), leave console
   detection on **Automatic**, and press Convert. Some machines need one extra
   file of your own: the Neo Geo a BIOS ZIP (**Options > Neo Geo**), the Sharp
   X68000 an IPL ROM and a font ROM, and a split CPS-1 clone the ZIP of its
   parent beside it. The machine pages say which ([Neo Geo](NEOGEO.md),
   [CPS-1](CPS1.md), [X68000](X68000.md)).
3. The first conversion offers to install the missing build tools itself (a
   portable Git and a portable compiler on Windows, without administrator
   rights; a few packages on Debian and Ubuntu), because every game is compiled
   on your computer. Accept, and wait a few minutes once. See
   [BUILDING.md](BUILDING.md).
4. Open the finished games in their console folders under **Games**, beside the
   application. The **Compiled Games** window lists them too
   ([COMPILED_GAMES.md](COMPILED_GAMES.md)); the keys are in
   [CONTROLS.md](CONTROLS.md).

Playing a converted game needs no development tools. ROMs and downloaded box art
are never included with Retro-Recomp: bring your own.

## What the installers contain

Installers and portable downloads contain the same converter. No ROM, BIOS,
downloaded cover, save or personal compilation library is included. Installing
the converter does not install the native development tools needed to compile
games; see [BUILDING.md](BUILDING.md). Exported games need no development tools.

## Windows x64

Download `Retro-Recomp-<version>-windows-x64-setup.exe` from the
[latest release](https://github.com/ArthurReboulSalze/RetroRecomp/releases/latest).
Run the setup wizard. The default is a per-user installation in
`%LOCALAPPDATA%\Programs\Retro-Recomp`, with a Start menu shortcut and an optional
desktop shortcut. It requires no administrator password. Keep a directory your
account can write to, so the in-app updater can replace the converter.

The installer is not code-signed. Windows may show its usual downloaded-app
warning (see below). Release checksums are provided in `SHA256SUMS.txt`.

### Windows security warnings

Retro-Recomp is not signed with a paid code-signing certificate yet. On first
launch Windows may show **"Windows protected your PC"**: it means *unknown
publisher*, not *virus found*. To continue, choose **More info > Run anyway**.
Everything can be checked: the full source code is public, every release lists
the SHA-256 of each file (`SHA256SUMS.txt`), and the executables are built from
the released source. Download Retro-Recomp only from
[retro-recomp.com](https://retro-recomp.com) or the project's
[GitHub releases](https://github.com/ArthurReboulSalze/RetroRecomp/releases).

The games you convert are compiled on your own computer, so they cannot carry
any publisher signature, ours included. On Windows 11 with **Smart App
Control** turned on, Windows may refuse to start them without offering to run
them anyway; Smart App Control has to be turned off (Windows Security > App &
browser control) to play them.

If your antivirus flags a file, please tell us: it is a false positive (often
caused by executable compression) that we will report to the vendor.

Uninstall through Windows Settings or the Start menu entry. Games, `datas`
(settings, library, discoveries, covers) are always kept. The uninstaller then
asks, with the size, whether to also remove the **build tools and compiler
caches** that Retro-Recomp installed beside itself (`datas\tools`, `.deps` and
`.build` in the installation folder, often several hundred megabytes). The
default answer is No: installing again in the same location then reuses them.
Answer Yes and only those three folders go; a link or junction is never
followed. A silent uninstall (`/SILENT`, `/VERYSILENT`) keeps them unless you
add `/PURGETOOLS`:

```bat
"%LOCALAPPDATA%\Programs\Retro-Recomp\uninstall\unins000.exe" /VERYSILENT /PURGETOOLS
```

The question comes with the uninstaller of a setup from version 1.5.2 or later;
an older installation gets it once you run the newer setup over it. If you
keep them and want the space back later, delete those three folders by hand or
use **Options > Common > Disk space > Remove build tools and caches** (below).
The next conversion offers to install the tools again.

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
(`sudo apt remove retro-recomp`) keeps every user's copy and data: a package
removal cannot ask questions and never touches home folders. To leave nothing
behind, first open **Options > Common > Disk space** in Retro-Recomp and use
**Remove build tools and caches** (see below), then remove the package; your
games, settings and discoveries stay in `~/.local/opt/Retro-Recomp`.

**Any distribution (per-user `.run` installer):** download
`Retro-Recomp-<version>-linux-x86_64-install.run` from the same release. Browsers
remove the execute permission from downloads, so a double-click does nothing:
run it in a terminal as your normal desktop user, **without sudo** (the
installer refuses sudo, since it installs in your home folder):

```sh
bash Retro-Recomp-<version>-linux-x86_64-install.run
```

Confirm installation in `~/.local/opt/Retro-Recomp`. The installer checks its
payload and the native converter before installing, then adds **Retro-Recomp**
to your applications menu with its icon. To choose another new, writable folder:

```sh
bash Retro-Recomp-<version>-linux-x86_64-install.run --prefix "$HOME/Applications/Retro-Recomp"
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
removes its managed program files and matching application-menu entry, and
keeps your games, settings and discoveries. In a terminal it also asks
`Also remove the build tools and compiler caches (size)? [y/N]` (default No):
Yes removes `datas/tools`, `.deps` and `.build` under the installation folder
and nothing else, and never follows a symbolic link. In a script, add
`--purge-tools` to remove them, otherwise they are kept:

```sh
"$HOME/.local/opt/Retro-Recomp/uninstall.sh" --purge-tools
```

Close the converter and any conversions before installation or uninstall.

### Removing the build tools and compiler caches from the application

Whatever the installer, **Options > Common > Disk space** has a second action,
**Remove build tools and caches (size)**, after the removal of leftover
per-game build folders. It asks for confirmation, then removes `datas/tools`
(portable compiler, CMake, Ninja and Git on Windows), `.deps` (engine sources,
SDL2, translators) and `.build` (shared caches, leftover projects) from the
installation folder, and keeps games, settings, discoveries and covers. It is
the way to free this space before removing the Debian package, and it is
offered only by an installed application (not by a copy run from a project's
`Export` folder or from the sources). The next conversion offers to install the
missing tools again, then prepares the shared pieces (a few minutes).

## Updates and existing portable data

Use **Check for updates** inside the installed application. When a newer
version exists, the dialog shows what changed since your version (the
published release notes of every skipped version, in English) before you
choose to download it. The Windows installer shows the same notes before
installing. When the window opens, the converter also looks quietly (at most every
6 hours, downloading nothing) for a new version and a new shared base, and shows a
dot on the button; **Options › Common › Check for updates at startup** turns that
off. The update downloads the
matching native converter, checks size, SHA-256, architecture and version, then
replaces the application and the base copy of the same release
(`Retro-Recomp-base.zip`, beside it) and restarts it. You do not need to download the
installer again for a converter update. The install location and shortcuts remain
unchanged. An installed current version offers no update to itself.

Settings, favorites, cards, downloaded covers and compilation observations stay
in `datas` in the installation folder; generated games default to `Games` there.
The installer and updater preserve these directories, including your private
compilation library. Uninstall also leaves them in place (only the build tools
and compiler caches can be removed with it, when you ask). Back them up if needed.

An existing portable installation is not imported automatically. You can keep
using it, or close both copies and copy its `datas` and `Games` into the new
installation before first use. Leave your ROMs where they are. Set per-console
ROM/export folders in Options (Reconvert also asks for a console's ROM folder
when it cannot find the original ROMs, and remembers it); rescan games or repair
paths after moving them.
Do not share compiler caches between Windows and Linux.

## Build installers

First build and audit the native converter for the target OS. The installer
builder copies only that binary, the app icon, notices and installation guide;
it never collects a directory of local exports or user data.

Windows uses [Inno Setup 6.7.3](https://jrsoftware.org/isdl.php), with
[`PrivilegesRequired=lowest`](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
for per-user installation. Run on Windows:

```powershell
python -B tools/package_installers.py --target windows --version <version> --executable Export/Retro-Recomp.exe --output .build/installers --iscc "path/to/ISCC.exe"
```

Build the Linux installer on Linux, using the already audited native binary:

```sh
python3 -B tools/package_installers.py --target linux --version <version> --executable Export/Retro-Recomp --output .build/installers
```

Launchers follow the [Desktop Entry specification](https://specifications.freedesktop.org/desktop-entry/latest-single/).
The `.audit.json` next to each built installer records its SHA-256 and each
payload file. Release checksums cover the installers as well as the portable
assets. Build tools and private audit receipts are not release assets.
