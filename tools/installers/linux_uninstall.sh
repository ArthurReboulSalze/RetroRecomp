#!/usr/bin/env bash
# Remove managed application files only. All generated/user data are retained.
set -euo pipefail
prefix=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
marker="$prefix/.retro-recomp-install"
[[ -f $marker && ! -L $marker && -O $prefix ]] || { echo 'Installation marker missing or not owned by you.' >&2; exit 1; }
mapfile -t record < "$marker"
[[ ${record[0]:-} == 'Retro-Recomp per-user installation v1' ]] || { echo 'Unknown installation marker.' >&2; exit 1; }
desktop=${record[2]:-}
escaped=${prefix//\\/\\\\}
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
# Retain ownership of a data-containing installation folder for a later reinstall.
shopt -s nullglob dotglob
remaining=("$prefix"/*)
if ((${#remaining[@]} == 1)) && [[ ${remaining[0]} == "$marker" ]]; then
    rm -f -- "$marker"
    rmdir -- "$prefix" 2>/dev/null || true
fi
echo "Retro-Recomp uninstalled. Your games, datas, compiler caches and any other files remain in: $prefix"
