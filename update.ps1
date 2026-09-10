$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$HealthUrl = 'http://127.0.0.1:18765/health'
function Get-LectureNotesHealth {
  try {
    return Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
  } catch {
    return $null
  }
}

# UPDATE must replace an already-running copy even when the new ZIP was
# extracted to a different folder and therefore does not have the old token.
$health = Get-LectureNotesHealth
if ($health -and $health.app -eq 'lecture-notes') {
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
      throw 'Could not stop the previous Lecture Notes server. Close the Python process using port 18765 or restart Windows, then run UPDATE.cmd again.'
    }
  }
}

& (Join-Path $PSScriptRoot 'setup.ps1')

$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'extension\manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$running = Get-LectureNotesHealth
if (-not $running -or $running.app -ne 'lecture-notes' -or [string]$running.version -ne [string]$manifest.version) {
  throw "Update finished copying files, but Lecture Notes v$($manifest.version) did not start correctly. Check .local/server-error.log."
}

Write-Output ''
Write-Output "Lecture Notes v$($manifest.version) is running from this folder."
Write-Output 'Chrome unpacked extensions need one manual reload after files change.'
Write-Output 'Opening chrome://extensions when Chrome can be found...'

$chromeCandidates = @(@(
  (Get-Command chrome.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique)

if ($chromeCandidates.Count -gt 0) {
  Start-Process -FilePath $chromeCandidates[0] -ArgumentList 'chrome://extensions/'
  Write-Output 'Click Reload on "Lecture Notes · 강의 노트" once. That is the final update step.'
} else {
  Write-Output 'Open chrome://extensions in Chrome and click Reload on Lecture Notes once.'
}
