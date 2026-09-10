"""Windows regression test: START must replace an older server on port 18765."""
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
PORT = 18765


def health(timeout=1):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=timeout) as response:
            return json.load(response)
    except Exception:
        return None


def wait_for(predicate, seconds=12):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.15)
    return None


def shutdown_current():
    settings = ROOT / '.local' / 'settings.json'
    if not settings.exists():
        return
    try:
        token = json.loads(settings.read_text(encoding='utf-8-sig')).get('token')
        if not token:
            return
        request = urllib.request.Request(
            f'http://127.0.0.1:{PORT}/api/shutdown',
            data=b'{}',
            method='POST',
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        )
        urllib.request.urlopen(request, timeout=2).read()
    except Exception:
        pass


def main():
    if os.name != 'nt':
        print('SKIP: stale-server replacement is Windows-specific')
        return
    if health():
        raise RuntimeError('port 18765 must be free before this regression test')

    fake_code = r'''
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
class H(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path == '/health':
            data=json.dumps({'app':'lecture-notes','version':'0.0.0'}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
        else:
            self.send_response(404); self.end_headers()
    def do_POST(self):
        self.send_response(401); self.end_headers()
ThreadingHTTPServer(('127.0.0.1',18765),H).serve_forever()
'''
    fake = subprocess.Popen([sys.executable, '-c', fake_code], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        old = wait_for(lambda: health() if health() and health().get('version') == '0.0.0' else None)
        if not old:
            raise RuntimeError('fake old Lecture Notes server did not start')

        shell = shutil.which('pwsh') or shutil.which('powershell')
        if not shell:
            raise RuntimeError('PowerShell was not found')
        subprocess.run(
            [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'start.ps1'), '-ServerOnly'],
            cwd=ROOT,
            check=True,
            timeout=35,
        )

        expected = json.loads((ROOT / 'extension' / 'manifest.json').read_text(encoding='utf-8-sig'))['version']
        current = wait_for(lambda: health() if health() and health().get('version') == expected else None)
        if not current:
            raise RuntimeError(f'START did not replace the stale server with v{expected}: {health()}')
        print(f'PASS: START replaced stale v0.0.0 with v{expected}')
    finally:
        shutdown_current()
        try:
            fake.wait(timeout=3)
        except subprocess.TimeoutExpired:
            fake.kill()
            fake.wait(timeout=3)
        wait_for(lambda: not health(), seconds=5)


if __name__ == '__main__':
    main()
