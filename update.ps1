$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# Stop an older in-memory server so the newly extracted Python code is used
# immediately instead of waiting for the next Windows sign-in.
$settingsPath = Join-Path $PSScriptRoot '.local\settings.json'
if (Test-Path -LiteralPath $settingsPath) {
  try {
    $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($settings.token) {
      Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18765/api/shutdown' -Headers @{ Authorization = 'Bearer ' + $settings.token } -ContentType 'application/json' -Body '{}' -TimeoutSec 3 | Out-Null
      Start-Sleep -Milliseconds 700
    }
  } catch {
    # An already-stopped server is a normal update state.
  }
}

& (Join-Path $PSScriptRoot 'setup.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output ''
Write-Output 'Program files and the local server are updated.'
Write-Output 'Chrome unpacked extensions need one manual reload after files change.'
Write-Output 'Opening chrome://extensions when Chrome can be found...'

$chromeCandidates = @(
  (Get-Command chrome.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique

if ($chromeCandidates.Count -gt 0) {
  Start-Process -FilePath $chromeCandidates[0] -ArgumentList 'chrome://extensions/'
  Write-Output 'Click Reload on "Lecture Notes · 강의 노트" once. That is the final update step.'
} else {
  Write-Output 'Open chrome://extensions in Chrome and click Reload on Lecture Notes once.'
}
