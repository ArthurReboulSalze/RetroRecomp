param()
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location -LiteralPath $projectRoot
try {
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
    python -m PyInstaller --noconfirm --onefile --windowed --name Retro-Recomp `
        --icon "$projectRoot\assets\Retro-Recomp.ico" `
        --version-file "$projectRoot\.build\converter-version.txt" `
        --exclude-module numpy `
        --distpath .build/packaged --workpath .build/packaging --specpath .build `
        @resourceArguments RetroRecomp.py
    if ($LASTEXITCODE -ne 0) { throw 'La compilation de Retro-Recomp.exe a échoué.' }
    python -X utf8 tools/install_converter.py "$projectRoot\.build\packaged\Retro-Recomp.exe" "$projectRoot\Export\Retro-Recomp.exe"
    if ($LASTEXITCODE -ne 0) { throw "L'installation de Retro-Recomp.exe a échoué." }
    Write-Output (Join-Path $projectRoot 'Export\Retro-Recomp.exe')
} finally {
    Pop-Location
}
