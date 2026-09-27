param()
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location -LiteralPath $projectRoot
try {
    python -X utf8 tools/prepare_logo.py
    if ($LASTEXITCODE -ne 0) { throw 'La préparation du logo a échoué.' }
    python -m PyInstaller --noconfirm --onefile --windowed --name Retro-Recomp `
        --icon "$projectRoot\assets\Retro-Recomp.ico" `
        --exclude-module numpy `
        --distpath .build/packaged --workpath .build/packaging --specpath .build `
        --add-data "$projectRoot\native;native" --add-data "$projectRoot\profiles;profiles" `
        --add-data "$projectRoot\assets;assets" RetroRecomp.py
    if ($LASTEXITCODE -ne 0) { throw 'La compilation de Retro-Recomp.exe a échoué.' }
    python -X utf8 tools/install_converter.py "$projectRoot\.build\packaged\Retro-Recomp.exe" "$projectRoot\Export\Retro-Recomp.exe"
    if ($LASTEXITCODE -ne 0) { throw "L'installation de Retro-Recomp.exe a échoué." }
    Write-Output (Join-Path $projectRoot 'Export\Retro-Recomp.exe')
} finally {
    Pop-Location
}
