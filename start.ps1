$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$ready = $false
try { $health=Invoke-RestMethod 'http://127.0.0.1:18765/health' -TimeoutSec 2; $ready=$health.app -eq 'lecture-notes' } catch {}
if (-not $ready) {
  $python=(Get-Command python -ErrorAction Stop).Source
  New-Item -ItemType Directory -Force '.local' | Out-Null
  Start-Process -FilePath $python -ArgumentList @('backend/server.py') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot '.local/server.log') -RedirectStandardError (Join-Path $PSScriptRoot '.local/server-error.log')
  for($i=0;$i -lt 30;$i++) {
    Start-Sleep -Milliseconds 300
    try {$health=Invoke-RestMethod 'http://127.0.0.1:18765/health' -TimeoutSec 1;if($health.app -eq 'lecture-notes'){$ready=$true;break}} catch {}
  }
}
if(-not $ready){throw 'Could not start Lecture Notes. Check .local/server-error.log.'}
Start-Process 'http://127.0.0.1:18765'
