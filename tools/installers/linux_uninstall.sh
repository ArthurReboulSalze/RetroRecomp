#!/usr/bin/env bash
# Remove managed application files. Games, settings and discoveries are always
# kept. On request the build tools and compiler caches the converter installed
# beside itself (datas/tools, .deps, .build) are removed too.
set -euo pipefail
purge=0
while (($#)); do
    case "$1" in
        --purge-tools) purge=1; shift ;;
        --help) echo 'Usage: uninstall.sh [--purge-tools]'
                echo 'Removes Retro-Recomp. Your games, settings and discoveries are always kept.'
                echo '--purge-tools also removes the build tools and compiler caches (datas/tools, .deps, .build);'
                echo 'without it, a terminal session is asked, and a script keeps them.'
                exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
prefix=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
marker="$prefix/.retro-recomp-install"
[[ -f $marker && ! -L $marker && -O $prefix ]] || { echo 'Installation marker missing or not owned by you.' >&2; exit 1; }
mapfile -t record < "$marker"
[[ ${record[0]:-} == 'Retro-Recomp per-user installation v1' ]] || { echo 'Unknown installation marker.' >&2; exit 1; }
desktop=${record[2]:-}
escaped=${prefix//\\/\\\\}

# The three folders, relative to the installation. Only real folders qualify: a
# symbolic link (or a link in the way) is never followed and never removed.
tool_folders=(datas/tools .deps .build)
present_tools() {
    local relative path
    for relative in "${tool_folders[@]}"; do
        path="$prefix/$relative"
        [[ -d $path && ! -L $path ]] || continue
        [[ $relative != datas/* || ( -d $prefix/datas && ! -L $prefix/datas ) ]] || continue
        [[ $(realpath -- "$path") == "$prefix/$relative" ]] || continue
        printf '%s\n' "$relative"
    done
}
tools_size() {
    # Apparent size in KiB, without following links.
    local total=0 relative kib
    for relative in "$@"; do
        kib=$(du -sk --apparent-size -P -- "$prefix/$relative" 2>/dev/null | awk '{ print $1 }') || kib=0
        total=$((total + ${kib:-0}))
    done
    awk -v kib="$total" 'BEGIN { if (kib >= 1048576) printf "%.1f GB", kib / 1048576; else printf "%d MB", (kib + 1023) / 1024 }'
}
mapfile -t tools < <(present_tools)
if ((${#tools[@]} && ! purge)) && [[ -t 0 && -t 1 ]]; then
    read -r -p "Also remove the build tools and compiler caches ($(tools_size "${tools[@]}"))? Your games, settings and discoveries are kept. [y/N] " answer || answer=
    [[ $answer == y || $answer == Y ]] && purge=1
fi

if [[ $desktop == /*/io.github.ArthurReboulSalze.RetroRecomp.desktop && -f $desktop && ! -L $desktop ]] && \
    grep -Fqx -- "X-RetroRecomp-InstallRoot=$escaped" "$desktop"; then
    rm -f -- "$desktop"
    if command -v update-desktop-database >/dev/null; then update-desktop-database "${desktop%/*}" >/dev/null 2>&1 || true; fi
fi
for file in Retro-Recomp Retro-Recomp.png LICENSE.txt THIRD_PARTY_NOTICES.md INSTALL.txt .retro-recomp-install uninstall.sh; do
    [[ ! -d $prefix/$file ]] || { echo "Managed file became a directory: $file" >&2; exit 1; }
done
for file in Retro-Recomp Retro-Recomp.png LICENSE.txt THIRD_PARTY_NOTICES.md INSTALL.txt uninstall.sh; do
    rm -f -- "$prefix/$file"
done
removed_tools=0
if ((purge && ${#tools[@]})); then
    failed=0
    for relative in "${tools[@]}"; do
        # rm unlinks a link met inside without following it; read-only folders
        # (Git checkouts) are made writable first. Nothing outside $prefix.
        chmod -R u+rwX -- "$prefix/$relative" 2>/dev/null || true
        if rm -rf --one-file-system -- "$prefix/$relative"; then :; else failed=1; fi
    done
    # An empty datas folder is not worth keeping; one with settings stays.
    rmdir -- "$prefix/datas" 2>/dev/null || true
    if ((failed)); then
        echo "Some build tools or caches could not be removed; delete them by hand in: $prefix" >&2
    else
        removed_tools=1
    fi
fi
# Retain ownership of a data-containing installation folder for a later reinstall.
shopt -s nullglob dotglob
remaining=("$prefix"/*)
if ((${#remaining[@]} == 1)) && [[ ${remaining[0]} == "$marker" ]]; then
    rm -f -- "$marker"
    rmdir -- "$prefix" 2>/dev/null || true
fi
if ((removed_tools)); then
    echo "Retro-Recomp uninstalled, with its build tools and compiler caches. Your games, settings and discoveries remain in: $prefix"
elif ((${#tools[@]})); then
    echo "Retro-Recomp uninstalled. Your games, settings, discoveries, build tools and compiler caches remain in: $prefix"
    echo "To free that space, delete the folders datas/tools, .deps and .build in $prefix (or run uninstall.sh --purge-tools next time)."
else
    echo "Retro-Recomp uninstalled. Your games, settings and any other files remain in: $prefix"
fi
