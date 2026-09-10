"""Lecture Notes server entry point with convenience-safe defaults."""
import json
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import server
from convenience import ConvenienceLibrary

ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / 'extension' / 'manifest.json').read_text(encoding='utf-8-sig'))['version']


def _safe_name(value):
    value = str(value or '')
    if not value or Path(value).name != value or value in {'.', '..'}:
        raise ValueError('자료 이름이 올바르지 않습니다.')
    return value


def _exam_metadata(app):
    exams = []
    local_files = sorted((app.library / 'exams').glob('*/시험대비.md'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
    for path in local_files:
        stat = path.stat()
        exams.append({'source': 'local', 'key': path.parent.name, 'name': path.parent.name, 'folder': str(path.parent), 'modified': stat.st_mtime, 'size': stat.st_size})
    local_names = {item['name'] for item in exams}
    vault = Path(app.config['vault_folder']) / '시험대비'
    for path in sorted(vault.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        stat = path.stat()
        if path.stem not in local_names and stat.st_size:
            exams.append({'source': 'vault', 'key': path.stem, 'name': path.stem, 'folder': str(path.parent), 'modified': stat.st_mtime, 'size': stat.st_size})
    return exams


class PerformanceLibrary(ConvenienceLibrary):
    """Throttle only repetitive watcher exports; user-triggered saves stay immediate."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scan_context = threading.local()
        self._background_exports = {}

    def export(self, ident):
        if getattr(self._scan_context, 'active', False):
            now = time.monotonic()
            if now - self._background_exports.get(ident, 0) < 10:
                return
            self._background_exports[ident] = now
        return super().export(ident)

    def scan(self):
        self._scan_context.active = True
        try:
            return super().scan()
        finally:
            self._scan_context.active = False


class ConvenienceHandler(server.Handler):
    def get(self):
        path = urlsplit(self.path).path
        if path in {'/ui-bootstrap.js', '/performance.js'}:
            if self.headers.get('Sec-Fetch-Site', '') == 'cross-site':
                return self.respond(403, {'error': '다른 사이트에서 설정 파일을 읽을 수 없습니다.'})
            return self.send_file(self.server.app.root / 'extension' / path[1:])
        if path == '/health':
            if not self.host_ok() or not self.origin_ok():
                return self.respond(403, {'error': '접근 불가'})
            return self.respond(200, {'app': 'lecture-notes', 'version': VERSION})
        if path == '/api/state' and self.authorized():
            query = parse_qs(urlsplit(self.path).query)
            if query.get('compact', ['0'])[0] == '1':
                app = self.server.app
                return self.respond(200, {'settings': app.public_settings(), 'lectures': app.list_lectures(), 'jobs': app.jobs(), 'exams': _exam_metadata(app)})
        if path == '/api/exam-content' and self.authorized():
            app = self.server.app
            query = parse_qs(urlsplit(self.path).query)
            source = query.get('source', [''])[0]
            name = _safe_name(query.get('name', [''])[0])
            if source == 'local':
                file = app.library / 'exams' / name / '시험대비.md'
            elif source == 'vault':
                file = Path(app.config['vault_folder']) / '시험대비' / (name + '.md')
            else:
                raise ValueError('시험 자료 위치가 올바르지 않습니다.')
            if not file.is_file():
                raise FileNotFoundError(file)
            return self.respond(200, {'name': name, 'folder': str(file.parent), 'content': file.read_text(encoding='utf-8-sig')})
        return super().get()


server.Library = PerformanceLibrary
server.Handler = ConvenienceHandler

if __name__ == '__main__':
    server.main()
