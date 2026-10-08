# tunza-adw installer for the Tunza PC (Windows, PowerShell).
#
# One line, in PowerShell:
#   irm https://raw.githubusercontent.com/tunza-labs/Tunza/main/tools/tunza-adw/install.ps1 | iex
#
# What it does, and nothing more:
#   1. Checks git, uv and the native Claude Code CLI; installs uv / Claude Code if missing.
#   2. Finds your Tunza checkout (or clones tunza-labs/Tunza to ~\code\Tunza).
#   3. Fast-forwards main if the checkout is clean and on main, so the tool is present.
#   4. Adds a `tunza-adw` command and a "Tunza ADW" desktop shortcut that opens the dashboard.
#   5. Runs `tunza-adw doctor`.
# It never pushes, never deletes, never touches training data.

$ErrorActionPreference = "Stop"
$Repo = "https://github.com/tunza-labs/Tunza.git"

function Say($msg) { Write-Host "tunza-adw: $msg" -ForegroundColor White }
function Warn($msg) { Write-Host "tunza-adw: $msg" -ForegroundColor Yellow }
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
              "$HOME\.local\bin"
}

# 1. Prerequisites -----------------------------------------------------------
Refresh-Path
if (-not (Have git)) {
  if (Have winget) {
    Say "installing Git"
    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
    $env:Path += ";C:\Program Files\Git\cmd"
  }
  if (-not (Have git)) { throw "Git is required. Install it (winget install Git.Git) and run this line again." }
}
if (-not (Have uv)) {
  Say "installing uv (Python runner)"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" | Out-Null
  Refresh-Path
  if (-not (Have uv)) { throw "uv did not install. See https://docs.astral.sh/uv/ and run this line again." }
}
if (-not (Have claude.exe)) {
  Say "installing the native Claude Code CLI"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex" | Out-Null
  Refresh-Path
  if (-not (Have claude)) { throw "Claude Code did not install. See https://claude.com/claude-code and run this line again." }
}

# 2. Find or clone the Tunza checkout --------------------------------------
function Is-Tunza($dir) {
  if (-not (Test-Path (Join-Path $dir ".git"))) { return $false }
  # Windows PowerShell 5.1 turns redirected native stderr into a terminating error under
  # ErrorActionPreference=Stop, so probe the remote with Continue.
  $saved = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  try { $url = git -C $dir remote get-url origin 2>&1 | Out-String } finally { $ErrorActionPreference = $saved }
  return ($url -match "tunza-labs/Tunza")
}
$candidates = @($env:TUNZA_ROOT, (Get-Location).Path, "$HOME\code\Tunza", "$HOME\Tunza",
                "$HOME\Documents\Tunza", "$HOME\Desktop\Tunza", "$HOME\source\repos\Tunza",
                "C:\code\Tunza", "D:\code\Tunza") | Where-Object { $_ }
$Root = $candidates | Where-Object { Is-Tunza $_ } | Select-Object -First 1
if (-not $Root) {
  $Root = "$HOME\code\Tunza"
  Say "cloning tunza-labs/Tunza into $Root"
  New-Item -ItemType Directory -Force -Path (Split-Path $Root) | Out-Null
  git clone $Repo $Root
}
Say "using checkout $Root"

# 3. Make sure the tool is in the checkout ---------------------------------
$Tool = Join-Path $Root "tools\tunza-adw\adw.py"
if (-not (Test-Path $Tool)) {
  $branch = (git -C $Root branch --show-current).Trim()
  $dirty = git -C $Root status --porcelain --untracked-files=no
  if ($branch -eq "main" -and -not $dirty) {
    Say "updating main"
    git -C $Root pull --ff-only origin main
  }
}
if (-not (Test-Path $Tool)) {
  throw "tools\tunza-adw is not in $Root (branch $(git -C $Root branch --show-current)). " +
        "Commit or stash your work, run 'git switch main; git pull', then run this line again."
}

# 4. Command + desktop shortcut ---------------------------------------------
$Bin = "$HOME\.local\bin"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
$Shim = Join-Path $Bin "tunza-adw.cmd"
Set-Content -Path $Shim -Encoding ASCII -Value "@echo off`r`nuv run --script `"$Tool`" %*"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not ($userPath -split ";" | Where-Object { $_ -eq $Bin })) {
  [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $Bin), "User")
}
Refresh-Path

try {
  $shell = New-Object -ComObject WScript.Shell
  $lnk = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Tunza ADW.lnk"))
  $lnk.TargetPath = $Shim
  $lnk.Arguments = "ui"
  $lnk.WorkingDirectory = $Root
  $lnk.Description = "Tunza ADW dashboard: run the model-build workflows, watch GPU memory and RAM"
  $lnk.Save()
  Say "desktop shortcut 'Tunza ADW' created"
} catch { Warn "could not create the desktop shortcut: $($_.Exception.Message)" }

# 5. Doctor --------------------------------------------------------------------
Say "checking this machine"
& $Shim doctor
Write-Host ""
Say "installed. Open the dashboard with the 'Tunza ADW' desktop icon, or run:  tunza-adw ui"
Say "First time only: run 'claude' once in a terminal and log in, if doctor says you are not logged in."
