[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExecutablePath,

    [Parameter(Mandatory = $true)]
    [string]$ReleaseDir,

    [Parameter(Mandatory = $true)]
    [string]$WinDeployQt
)

$ErrorActionPreference = 'Stop'

function Get-NormalizedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Assert-FileExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Name does not exist: $Path"
    }
}

$scriptDir = Split-Path -Parent $PSCommandPath
$clientRoot = Get-NormalizedPath (Join-Path $scriptDir '..')
$expectedReleaseDir = Get-NormalizedPath (Join-Path $clientRoot 'release')
$releaseDirFull = Get-NormalizedPath $ReleaseDir
$executableFull = Get-NormalizedPath $ExecutablePath
$winDeployQtFull = Get-NormalizedPath $WinDeployQt

if ($releaseDirFull -ne $expectedReleaseDir) {
    throw "Refusing to package into unexpected release directory. Expected '$expectedReleaseDir', got '$releaseDirFull'."
}

Assert-FileExists -Path $executableFull -Name 'Built executable'
Assert-FileExists -Path $winDeployQtFull -Name 'windeployqt'

if (Test-Path -LiteralPath $releaseDirFull) {
    Remove-Item -LiteralPath $releaseDirFull -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseDirFull | Out-Null

$targetExe = Join-Path $releaseDirFull (Split-Path $executableFull -Leaf)
Copy-Item -LiteralPath $executableFull -Destination $targetExe -Force

& $winDeployQtFull --compiler-runtime --force --dir $releaseDirFull $targetExe
if ($LASTEXITCODE -ne 0) {
    throw "windeployqt failed with exit code $LASTEXITCODE."
}

$platformPlugin = Join-Path $releaseDirFull 'platforms/qwindows.dll'
Assert-FileExists -Path $targetExe -Name 'Packaged executable'
Assert-FileExists -Path $platformPlugin -Name 'Qt platform plugin'

Write-Host "Packaged qt_wan_chat release:"
Write-Host "  exe: $targetExe"
Write-Host "  dir: $releaseDirFull"
