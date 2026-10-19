#!/usr/bin/env bash
# Self-extracting per-user package. Generated constants and archive follow below.
set -euo pipefail
VERSION='@VERSION@'
PAYLOAD_SHA256='@PAYLOAD_SHA256@'
APP_ID='io.github.ArthurReboulSalze.RetroRecomp'
MARKER='Retro-Recomp per-user installation v1'
prefix="${HOME:?}/.local/opt/Retro-Recomp"
confirmed=0
while (($#)); do
    case "$1" in
        --yes) confirmed=1; shift ;;
        --prefix) (($# >= 2)) || { echo 'Missing --prefix directory.' >&2; exit 2; }; prefix=$2; shift 2 ;;
        --help) echo 'Usage: bash installer.run [--yes] [--prefix /absolute/writable/folder]'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
die() { echo "Retro-Recomp: $*" >&2; exit 1; }
[[ $(id -u) != 0 ]] || die 'Run this installer as your normal user, without sudo.'
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || die 'This package requires Linux x86-64.'
for utility in realpath sha256sum tar tail awk sort mktemp timeout; do
    command -v "$utility" >/dev/null || die "Required tool missing: $utility"
done
libc=$(getconf GNU_LIBC_VERSION 2>/dev/null) || die 'This package requires glibc 2.41 or newer.'
[[ $libc == glibc\ * ]] || die 'This package requires glibc.'
[[ $(printf '%s\n' 2.41 "${libc#glibc }" | sort -V | head -n 1) == 2.41 ]] || die 'glibc 2.41 or newer is required.'
[[ $prefix == /* && $prefix != *[$'\n\r\t=']* ]] || die 'Use an absolute directory without control characters or =.'
[[ ! -L $prefix ]] || die 'The installation directory must not be a symbolic link.'
prefix=$(realpath -m -- "$prefix")
case "$prefix" in
    /|/usr|/usr/*|/bin|/sbin|/lib|/lib64|/etc|/var|/opt|"$(realpath "$HOME")") die 'Choose a private application directory in your home folder.' ;;
esac
data_home=${XDG_DATA_HOME:-$HOME/.local/share}
[[ $data_home == /* && $data_home != *[$'\n\r\t']* ]] || die 'XDG_DATA_HOME must be an absolute directory without control characters.'
desktop="$data_home/applications/$APP_ID.desktop"
# Two escaping passes are required by the Desktop Entry specification.
value() { local v=$1; v=${v//\\/\\\\}; printf '%s' "$v"; }
argument() {
    local v=$1
    v=${v//%/%%}; v=${v//\\/\\\\}; v=${v//\"/\\\"}; v=${v//\$/\\\$}; v=${v//\`/\\\`}
    value "\"$v\""
}
if [[ -e $prefix ]]; then
    [[ -d $prefix && -O $prefix && -w $prefix ]] || die 'The installation folder must be writable and owned by you.'
    [[ -f $prefix/.retro-recomp-install && ! -L $prefix/.retro-recomp-install ]] || die 'The folder already exists without an installation marker; choose a new folder.'
    [[ $(head -n 1 -- "$prefix/.retro-recomp-install") == "$MARKER" ]] || die 'Unknown installation marker.'
fi
if [[ -e $desktop || -L $desktop ]]; then
    [[ -f $desktop && ! -L $desktop ]] || die 'The application launcher is not a regular file.'
    grep -Fqx -- "X-RetroRecomp-InstallRoot=$(value "$prefix")" "$desktop" || die 'An existing launcher belongs to another installation.'
fi
echo "Retro-Recomp $VERSION — Linux x86-64"
echo "Install in: $prefix"
echo 'Games, settings, covers and compilation knowledge are kept during updates and uninstall.'
echo 'No Python is required to open the app. Conversion still needs the native build tools.'
if (( ! confirmed )); then
    [[ -t 0 ]] || die 'Use --yes for unattended installation.'
    read -r -p 'Install? [y/N] ' answer
    [[ $answer == y || $answer == Y ]] || exit 0
fi
mkdir -p -- "$prefix"
[[ -O $prefix && -w $prefix ]] || die 'The installation directory is not writable by you.'
stage=$(mktemp -d "$prefix/.RetroRecomp-install-XXXXXXXX")
cleanup() {
    # Only these package files can ever be staged. Never recursively delete data.
    for file in payload.tar.gz Retro-Recomp Retro-Recomp.png uninstall.sh LICENSE.txt THIRD_PARTY_NOTICES.md INSTALL.txt .retro-recomp-install launcher.desktop; do
        rm -f -- "$stage/$file"
    done
    rmdir -- "$stage" 2>/dev/null || true
}
trap cleanup EXIT
line=$(awk '/^__ARCHIVE_BELOW__$/ { print NR + 1; exit }' "$0")
[[ $line =~ ^[0-9]+$ ]] || die 'Package archive marker is missing.'
tail -n +"$line" -- "$0" > "$stage/payload.tar.gz"
actual=$(sha256sum "$stage/payload.tar.gz"); actual=${actual%% *}
[[ $actual == "$PAYLOAD_SHA256" ]] || die 'Package checksum mismatch; download the installer again.'
expected=$(printf '%s\n' INSTALL.txt LICENSE.txt Retro-Recomp Retro-Recomp.png THIRD_PARTY_NOTICES.md uninstall.sh | sort)
[[ $(tar -tzf "$stage/payload.tar.gz" | sort) == "$expected" ]] || die 'Unexpected installer contents.'
tar -xzf "$stage/payload.tar.gz" --no-same-owner --no-same-permissions -C "$stage"
chmod 755 "$stage/Retro-Recomp" "$stage/uninstall.sh"
PYINSTALLER_RESET_ENVIRONMENT=1 timeout 45 "$stage/Retro-Recomp" _verify-update "$VERSION" || die 'The converter could not run on this system. Installation stopped.'
for file in Retro-Recomp Retro-Recomp.png uninstall.sh LICENSE.txt THIRD_PARTY_NOTICES.md INSTALL.txt .retro-recomp-install; do
    [[ ! -L $prefix/$file && ( ! -e $prefix/$file || -f $prefix/$file ) ]] || die "Cannot replace managed file: $file"
done
printf '%s\n' "$MARKER" "$VERSION" "$desktop" > "$stage/.retro-recomp-install"
printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Version=1.0' 'Name=Retro-Recomp' \
    "Exec=$(argument "$prefix/Retro-Recomp")" "Path=$(value "$prefix")" \
    "Icon=$(value "$prefix/Retro-Recomp.png")" 'Terminal=false' 'Categories=Game;Utility;' \
    'StartupNotify=false' "X-RetroRecomp-InstallRoot=$(value "$prefix")" > "$stage/launcher.desktop"
mkdir -p -- "${desktop%/*}"
# Commit only after the entire payload and native version have been checked.
for file in Retro-Recomp.png uninstall.sh LICENSE.txt THIRD_PARTY_NOTICES.md INSTALL.txt .retro-recomp-install Retro-Recomp; do
    mv -fT -- "$stage/$file" "$prefix/$file"
done
install -m 644 -- "$stage/launcher.desktop" "$desktop"
if command -v update-desktop-database >/dev/null; then update-desktop-database "${desktop%/*}" >/dev/null 2>&1 || true; fi
echo "Installed. Open Retro-Recomp from your applications menu, or run: $prefix/Retro-Recomp"
echo "Uninstall (keeps your data): $prefix/uninstall.sh"
exit 0
__ARCHIVE_BELOW__
