$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  throw 'Python 3.11+ is required. Install Python and enable Add Python to PATH.'
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    Write-Output 'FFmpeg installation was requested. If START fails, sign out/in or reopen the terminal once.'
  } else {
    throw 'FFmpeg is required. Install FFmpeg and add it to PATH.'
  }
}

python backend/app.py --init-only
if ($LASTEXITCODE -ne 0) {
  throw 'Configuration initialization failed.'
}

# Run the local processing server silently whenever this Windows account signs in.
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$startScript = Join-Path $PSScriptRoot 'start.ps1'
$autoStartCommand = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $startScript + '" -ServerOnly'
New-Item -Path $runKey -Force | Out-Null
New-ItemProperty -Path $runKey -Name 'Lecture Notes' -Value $autoStartCommand -PropertyType String -Force | Out-Null

# Also create a Start-menu fallback so the project folder never has to be remembered.
$programs = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'
New-Item -ItemType Directory -Force $programs | Out-Null
$shortcutPath = Join-Path $programs 'Lecture Notes.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = 'powershell.exe'
$shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $startScript + '"'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Start Lecture Notes local server and open the app'
$shortcut.Save()

# Start it immediately as well. Future Windows logins do this automatically.
& $startScript -ServerOnly

Write-Output ''
Write-Output 'Lecture Notes is ready.'
Write-Output '- It will start automatically when you sign in to Windows.'
Write-Output '- If it is ever offline, search the Windows Start menu for "Lecture Notes".'
Write-Output '- Set your OpenAI API key / Obsidian folder, then load extension/ in Chrome once.'
