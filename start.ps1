# One-step launcher for Windows: installs Docker Desktop if needed, starts the app, opens the browser.
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$Url = 'http://localhost:81'

function Say($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "`nError: $msg" -ForegroundColor Red; Read-Host 'Press Enter to close'; exit 1 }
function DockerReady { docker info *> $null; return ($LASTEXITCODE -eq 0) }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $answer = Read-Host 'Docker Desktop is not installed. Install it now with winget? [y/N]'
    if ($answer -match '^[Yy]$' -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        Write-Host "`nDocker Desktop was installed. Restart Windows if it asks you to, open Docker Desktop once, then run start.bat again." -ForegroundColor Yellow
        Read-Host 'Press Enter to close'
        exit 0
    }
    Fail 'Install Docker Desktop from https://www.docker.com/products/docker-desktop/ , open it once, then run start.bat again.'
}

if (-not (DockerReady)) {
    Say 'Starting Docker Desktop (this can take a minute)...'
    $exe = Join-Path $Env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $exe) { Start-Process $exe }
    for ($i = 0; $i -lt 60 -and -not (DockerReady); $i++) { Start-Sleep -Seconds 3 }
    if (-not (DockerReady)) { Fail 'Docker is installed but not running. Open Docker Desktop and run start.bat again.' }
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker Compose is missing. Update Docker Desktop and run start.bat again.' }

# First run: create a private admin password instead of a well-known default.
$NewPassword = ''
if (-not (Test-Path '.env')) {
    $chars = [char[]]([char]'a'..[char]'z' + [char]'A'..[char]'Z' + [char]'0'..[char]'9')
    $NewPassword = -join (1..14 | ForEach-Object { $chars | Get-Random })
    Set-Content -Path '.env' -Value "PD_ADMIN_USER=admin`nPD_ADMIN_PASSWORD=$NewPassword" -Encoding ascii
}

Say 'Building and starting Paper Downloader (the first time takes 5-10 minutes)...'
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Fail 'docker compose failed. Scroll up to see why.' }

Say "Waiting for the app to answer at $Url ..."
$up = $false
for ($i = 0; $i -lt 60 -and -not $up; $i++) {
    try { Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null; $up = $true } catch { Start-Sleep -Seconds 2 }
}
if (-not $up) { Fail 'The app did not start. See the logs with: docker compose logs' }

Say "Ready: $Url"
if ($NewPassword) {
    Write-Host "`n  First login  ->  user: admin   password: $NewPassword" -ForegroundColor Green
    Write-Host '  (saved in the .env file; you can change it later in Users)'
}
Start-Process $Url
Read-Host "`nPress Enter to close this window (the app keeps running)"
