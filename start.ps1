[CmdletBinding()]
param([switch]$ServerOnly)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$manifestPath = Join-Path $PSScriptRoot 'extension\manifest.json'
$ExpectedVersion = (Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json).version
$HealthUrl = 'http://127.0.0.1:18765/health'

function Get-LectureNotesHealth {
  try {
    return Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
  } catch {
    return $null
  }
}

function Stop-CurrentLectureNotesServer {
  param([object]$Health)
  if (-not $Health -or $Health.app -ne 'lecture-notes') { return }

  # Prefer the authenticated shutdown endpoint when this folder owns the token.
  $settingsPath = Join-Path $PSScriptRoot '.local\settings.json'
  if (Test-Path -LiteralPath $settingsPath) {
    try {
      $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($settings.token) {
        Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18765/api/shutdown' -Headers @{ Authorization = 'Bearer ' + $settings.token } -ContentType 'application/json' -Body '{}' -TimeoutSec 3 | Out-Null
        Start-Sleep -Milliseconds 800
      }
    } catch {}
  }

  # A previous installation may live in a different folder, so its token is not
  # available here. Only after /health positively identifies Lecture Notes do we
  # terminate the process that owns the fixed loopback port.
  $stillRunning = Get-LectureNotesHealth
  if ($stillRunning -and $stillRunning.app -eq 'lecture-notes') {
    try {
      $owners = Get-NetTCPConnection -LocalPort 18765 -State Listen -ErrorAction Stop |
        Select-Object -ExpandProperty OwningProcess -Unique
      foreach ($owner in $owners) {
        if ($owner -and $owner -ne $PID) {
          Stop-Process -Id $owner -Force -ErrorAction Stop
        }
      }
      Start-Sleep -Milliseconds 600
    } catch {
      throw 'An older Lecture Notes server is still using port 18765. Close it in Task Manager or restart Windows, then run START.cmd again.'
    }
  }
}

$health = Get-LectureNotesHealth
if ($health -and $health.app -eq 'lecture-notes' -and [string]$health.version -ne [string]$ExpectedVersion) {
  Write-Output "Replacing Lecture Notes v$($health.version) with v$ExpectedVersion..."
  Stop-CurrentLectureNotesServer -Health $health
  $health = Get-LectureNotesHealth
}

$ready = $health -and $health.app -eq 'lecture-notes' -and [string]$health.version -eq [string]$ExpectedVersion
if (-not $ready) {
  if ($health -and $health.app -ne 'lecture-notes') {
    throw 'Port 18765 is already used by another application. Close that application and run START.cmd again.'
  }

  $python = (Get-Command python -ErrorAction Stop).Source
  New-Item -ItemType Directory -Force '.local' | Out-Null
  Start-Process -FilePath $python -ArgumentList @('backend/app.py') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot '.local/server.log') -RedirectStandardError (Join-Path $PSScriptRoot '.local/server-error.log')
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 300
    $health = Get-LectureNotesHealth
    if ($health -and $health.app -eq 'lecture-notes' -and [string]$health.version -eq [string]$ExpectedVersion) {
      $ready = $true
      break
    }
  }
}

if (-not $ready) {
  throw "Could not start Lecture Notes v$ExpectedVersion. Check .local/server-error.log."
}

if (-not $ServerOnly) {
  Start-Process 'http://127.0.0.1:18765'
}
