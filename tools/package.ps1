param([switch]$NoInstall)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location -LiteralPath $projectRoot
try {
    $creditsAudio = python tools/build_credits_audio.py
    if ($LASTEXITCODE -ne 0) { throw 'La compilation du lecteur MOD a échoué.' }
    $playerGamepad = python -B tools/build_player_gamepad.py
    if ($LASTEXITCODE -ne 0) { throw 'La compilation du contrôleur a échoué.' }
    python -X utf8 tools/prepare_logo.py
    if ($LASTEXITCODE -ne 0) { throw 'La préparation du logo a échoué.' }
    python -c "from pathlib import Path; from smsrecomp.metadata import write_converter_version; write_converter_version(Path('.build/converter-version.txt'))"
    if ($LASTEXITCODE -ne 0) { throw 'Les métadonnées Windows sont indisponibles.' }
    # Bundle declared resources only; local game profiles and old logos stay local.
    $resourcePaths = @(python -c "from tools.prepare_publication import BUNDLED_FILES; print(chr(10).join(sorted(BUNDLED_FILES)))")
    if ($LASTEXITCODE -ne 0) { throw 'La liste des ressources est indisponible.' }
    $resourceArguments = @()
    foreach ($resourcePath in $resourcePaths) {
        $resourceArguments += '--add-data'
        $resourceDestination = [System.IO.Path]::GetDirectoryName($resourcePath)
        if ([string]::IsNullOrEmpty($resourceDestination)) { $resourceDestination = '.' }
        $resourceDestination = $resourceDestination.Replace('\', '/')
        $resourceArguments += ((Join-Path $projectRoot $resourcePath) + ';' + $resourceDestination)
    }
    # Public modules no application path imports yet must still be frozen:
    # a generated hook lists them (too many for the command line).
    python -c "from pathlib import Path; from tools.prepare_publication import write_module_hook; write_module_hook(Path('.build/packaging-hooks'))"
    if ($LASTEXITCODE -ne 0) { throw 'La liste des modules est indisponible.' }
    $resourceArguments += '--additional-hooks-dir'
    $resourceArguments += (Join-Path $projectRoot '.build\packaging-hooks')
    python -m PyInstaller --noconfirm --onefile --windowed --name Retro-Recomp `
        --icon "$projectRoot\assets\Retro-Recomp.ico" `
        --version-file "$projectRoot\.build\converter-version.txt" `
        --add-binary "$creditsAudio;credits-runtime" `
        --add-binary "$playerGamepad;player-runtime" `
        --exclude-module numpy `
        --distpath .build/packaged --workpath .build/packaging --specpath .build `
        @resourceArguments RetroRecomp.py
    if ($LASTEXITCODE -ne 0) { throw 'La compilation de Retro-Recomp.exe a échoué.' }
    # -NoInstall leaves Export untouched (checks of the packaged build only).
    if ($NoInstall) {
        Write-Output (Join-Path $projectRoot '.build\packaged\Retro-Recomp.exe')
        return
    }
    python -X utf8 tools/install_converter.py "$projectRoot\.build\packaged\Retro-Recomp.exe" "$projectRoot\Export\Retro-Recomp.exe"
    if ($LASTEXITCODE -ne 0) { throw "L'installation de Retro-Recomp.exe a échoué." }
    Write-Output (Join-Path $projectRoot 'Export\Retro-Recomp.exe')
} finally {
    Pop-Location
}
