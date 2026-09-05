$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python 3.11+ is required. Install Python and enable Add Python to PATH.' }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    Write-Output 'If FFmpeg was installed, close this window and run START.cmd again.'
  } else { throw 'FFmpeg is required. Install FFmpeg and add it to PATH.' }
}
python backend/server.py --init-only
if ($LASTEXITCODE -ne 0) { throw 'Configuration initialization failed.' }
Write-Output 'Ready. Run START.cmd, set your OpenAI API key and Obsidian folder, then load extension/ in Chrome.'
