# Install the data skill and these skills on Windows, step by step.
#
#   powershell -ExecutionPolicy Bypass -File skills\install.ps1 [-Ref <commit on main>] [-Rules <new folder>]
#
#   Step 1  Git                                   (winget, if missing)
#   Step 2  uv, which brings Python 3.12          (uv's installer, if missing)
#   Step 3  Visual Studio C++ build tools         (winget, if missing; Rust links with them)
#   Step 4  Rust                                  (rustup, if missing; the engine is Rust)
#   Step 5  edgartools-data at -Ref               (uv tool install from GitHub; builds the engine, a few minutes)
#   Step 6  the skills into ~\.agents\skills and ~\.claude\skills (edgar-warehouse skill install)
#
# A step whose tool is already there keeps it. Run it again after a failed step: finished steps are skipped.
param([string]$Ref = "main", [string]$Rules = "")
$ErrorActionPreference = "Stop"

function Step([int]$Number, [string]$Text) { Write-Host "`nStep $Number of 6: $Text" -ForegroundColor Cyan }
function Kept([string]$Text) { Write-Host "  already installed: $Text" }

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") +
        ";$env:USERPROFILE\.cargo\bin;$env:USERPROFILE\.local\bin"
}

function Winget-Install([string]$Id, [string[]]$Extra = @()) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw "winget is missing: install App Installer from the Microsoft Store, then run this again" }
    winget install --exact --id $Id --silent --accept-source-agreements --accept-package-agreements @Extra
    if ($LASTEXITCODE -ne 0) { throw "winget could not install $Id" }
}

Step 1 "Git"
if (Get-Command git -ErrorAction SilentlyContinue) { Kept (git --version) } else { Winget-Install "Git.Git" }

Step 2 "uv (it installs Python 3.12 in step 5)"
if (Get-Command uv -ErrorAction SilentlyContinue) { Kept (uv --version) } else { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression }

Step 3 "Visual Studio C++ build tools"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$cpp = if (Test-Path $vswhere) { & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath } else { "" }
if ($cpp) { Kept $cpp } else {
    Winget-Install "Microsoft.VisualStudio.2022.BuildTools" @("--override", "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended")
}

Step 4 "Rust"
Refresh-Path
if (Get-Command cargo -ErrorAction SilentlyContinue) { Kept (cargo --version) } else {
    $rustup = Join-Path $env:TEMP "rustup-init.exe"
    Invoke-WebRequest https://win.rustup.rs/x86_64 -OutFile $rustup
    & $rustup -y --profile minimal
    if ($LASTEXITCODE -ne 0) { throw "rustup could not install Rust" }
}
Refresh-Path

Step 5 "edgartools-data at $Ref (builds the engine: a few minutes)"
$repo = "git+https://github.com/paulananth/edgartools-platform@$Ref"
uv tool install --force --python 3.12 "edgartools-data @ $repo#subdirectory=packages/data-skill" `
    --with "edgartools-bookkeeping @ $repo#subdirectory=packages/bookkeeping" `
    --with "edgartools-change-journal @ $repo#subdirectory=packages/change-journal" `
    --with "edgartools-control-core @ $repo#subdirectory=crates/control-contract" `
    --with "source-contract @ $repo#subdirectory=crates/source-contract"
if ($LASTEXITCODE -ne 0) { throw "uv could not install edgartools-data at $Ref" }
Refresh-Path

Step 6 "the skills"
$install = @("skill", "install")
if ($Rules) { $install += @("--rules", $Rules) }
edgar-warehouse @install
if ($LASTEXITCODE -ne 0) { throw "edgar-warehouse could not install the skills (it names any skill folder it will not replace)" }

Write-Host "`nDone. Open a new terminal (the PATH changed), then run: edgar-warehouse doctor" -ForegroundColor Green
