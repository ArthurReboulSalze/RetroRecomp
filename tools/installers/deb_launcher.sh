#!/bin/sh
# Retro-Recomp system launcher (Debian package).
# The application keeps its settings, games and caches beside its executable
# and updates itself, so each user runs a private copy in
# ~/.local/opt/Retro-Recomp (the same place as the per-user .run installer).
# This script creates that copy on first start and refreshes it when the
# package brings another version. A copy installed by the .run installer is
# left as it is. Nothing here touches the user's games or data.
set -eu
system=/opt/retro-recomp
prefix="${HOME:?}/.local/opt/Retro-Recomp"
marker="$prefix/.retro-recomp-install"
stamp="$prefix/.retro-recomp-deb"
version=$(cat "$system/VERSION")

refresh=0
if [ ! -e "$prefix/Retro-Recomp" ]; then
    refresh=1
elif [ -f "$stamp" ] && [ "$(cat "$stamp")" != "$version" ]; then
    refresh=1
fi

if [ "$refresh" = 1 ]; then
    if [ -e "$prefix" ] && [ ! -f "$marker" ]; then
        echo "Retro-Recomp: $prefix exists without an installation marker; it is left untouched." >&2
        exit 1
    fi
    mkdir -p "$prefix"
    for file in Retro-Recomp Retro-Recomp.png LICENSE.txt THIRD_PARTY_NOTICES.md INSTALL.txt; do
        cp -f "$system/$file" "$prefix/.$file.new"
        mv -f "$prefix/.$file.new" "$prefix/$file"
    done
    chmod 755 "$prefix/Retro-Recomp"
    printf '%s\n' 'Retro-Recomp per-user installation v1' "$version" '' > "$marker"
    printf '%s\n' "$version" > "$stamp"
fi
exec "$prefix/Retro-Recomp" "$@"
