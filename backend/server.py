"""Authenticated loopback-only HTTP bridge for the Chrome extension."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit, parse_qs, unquote

from core import atomic, inside, load, slug, inferred_names
from library import Library

PORT = 18765

class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, app):
        self.app = app
        super().__init__(address, Handler)

class Handler(BaseHTTPRequestHandler):
    server_version = 'LectureNotes/0.1'
    def log_message(self, *_):
        pass

    def origin_ok(self):
        origin = self.headers.get('Origin', '')
        return not origin or origin == f'http://127.0.0.1:{self.server.server_port}' or bool(re.fullmatch(r'chrome-extension://[a-p]{32}', origin))

    def host_ok(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def headers_common(self):
        origin = self.headers.get('Origin')
        if origin and self.origin_ok():
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' http://127.0.0.1:18765; img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'")

    def respond(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.headers_common()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        supplied = self.headers.get('Authorization', '')
        expected = 'Bearer ' + self.server.app.config['token']
        return self.host_ok() and self.origin_ok() and hmac.compare_digest(supplied, expected)

    def do_OPTIONS(self):
        if not self.host_ok() or not self.origin_ok():
            return self.respond(403, {'error': '접근 불가'})
        self.send_response(204)
        self.headers_common()
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()

    def do_GET(self):
        try:
            self.get()
        except (ValueError, FileNotFoundError):
            self.respond(404, {'error': '파일 또는 자료를 찾지 못했습니다.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.respond(500, {'error': '자료를 읽지 못했습니다.'})

    def get(self):
        if not self.host_ok() or not self.origin_ok():
            return self.respond(403, {'error': '접근 불가'})
        path = urlsplit(self.path).path
        app = self.server.app
        if path == '/health':
            return self.respond(200, {'app': 'lecture-notes', 'version': '0.1.0'})
        if not path.startswith('/api/'):
            if self.headers.get('Sec-Fetch-Site', '') == 'cross-site':
                return self.respond(403, {'error': '다른 사이트에서 설정 파일을 읽을 수 없습니다.'})
            public = {'/': 'panel.html', '/panel.html': 'panel.html', '/panel.js': 'panel.js', '/style.css': 'style.css', '/markdown.js': 'markdown.js', '/config.local.js': 'config.local.js'}
            public.update({('/' + name): name for name in ['appearance.js', 'print.html', 'print.js', 'print.css']})
            public.update({('/' + name): name for name in ['navigation.js', 'context.js', 'context-router.js']})
            if path not in public:
                return self.respond(404, {'error': '없음'})
            return self.send_file(app.root / 'extension' / public[path])
        if not self.authorized():
            return self.respond(401, {'error': '로컬 서버 연결 키가 다릅니다. START.cmd 실행 후 확장을 다시 로드하세요.'})
        if path == '/api/state':
            exams = [{'name': p.parent.name, 'folder': str(p.parent), 'content': p.read_text(encoding='utf-8')} for p in sorted((app.library / 'exams').glob('*/시험대비.md'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]]
            local_names = {e['name'] for e in exams}
            for p in sorted((Path(app.config['vault_folder']) / '시험대비').glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
                if p.stem not in local_names and p.stat().st_size:
                    exams.append({'name': p.stem, 'folder': str(p.parent), 'content': p.read_text(encoding='utf-8-sig')})
            return self.respond(200, {'settings': app.public_settings(), 'lectures': app.list_lectures(), 'jobs': app.jobs(), 'exams': exams})
        query = parse_qs(urlsplit(self.path).query)
        if path == '/api/lecture':
            return self.respond(200, app.lecture(query.get('id', [''])[0]))
        if path == '/api/file':
            lecture = app.lecture(query.get('id', [''])[0])
            name = query.get('name', [''])[0]
            if name not in lecture['files']:
                raise ValueError()
            return self.send_file(inside(lecture['folder'], Path(lecture['folder']) / name), attachment=True)
        return self.respond(404, {'error': '지원하지 않는 경로'})

    def send_file(self, path, attachment=False):
        path = Path(path)
        size = path.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get('Range', '')
        if range_header:
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', range_header)
            if not match:
                return self.respond(416, {'error': '잘못된 범위'})
            start = int(match[1]); end = min(end, int(match[2])) if match[2] else end
            if start > end or start >= size:
                return self.respond(416, {'error': '잘못된 범위'})
        self.send_response(206 if range_header else 200)
        self.headers_common()
        self.send_header('Content-Type', (mimetypes.guess_type(path.name)[0] or 'application/octet-stream') + ('; charset=utf-8' if path.suffix in {'.html', '.js', '.css', '.md', '.txt'} else ''))
        self.send_header('Content-Length', str(max(0, end - start + 1)))
        self.send_header('Accept-Ranges', 'bytes')
        if range_header:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if attachment:
            from urllib.parse import quote
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(path.name))
        self.end_headers()
        with path.open('rb') as stream:
            stream.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = stream.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_POST(self):
        if not self.authorized():
            return self.respond(401, {'error': '인증되지 않은 요청'})
        try:
            self.post()
        except (ValueError, UnicodeError) as error:
            self.respond(400, {'error': str(error)[:300]})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.respond(500, {'error': '로컬 작업에 실패했습니다. 경로와 파일 접근 권한을 확인하세요.'})

    def body(self, maximum=8_000_000):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= maximum:
            raise ValueError('요청 크기가 올바르지 않습니다.')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError('전송이 완료되지 않았습니다.')
        return json.loads(raw)

    def post(self):
        app = self.server.app
        url = urlsplit(self.path)
        if url.path == '/api/upload':
            query = parse_qs(url.query)
            original_name = query.get('name', ['파일'])[0]
            filename = slug(Path(original_name).stem) + Path(original_name).suffix.lower()
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2_000_000_000:
                raise ValueError('파일은 0바이트 초과 2GB 이하이어야 합니다.')
            target = app.private / 'uploads' / (secrets.token_hex(8) + '-' + filename)
            try:
                with target.open('wb') as stream:
                    left = length
                    while left:
                        chunk = self.rfile.read(min(left, 1024 * 1024))
                        if not chunk:
                            raise ValueError('파일 전송이 중단됐습니다.')
                        stream.write(chunk)
                        left -= len(chunk)
                if query.get('attach', [''])[0]:
                    ident = app.attach_file(query['attach'][0], target)
                    return self.respond(200, {'ok': True, 'id': ident})
                if query.get('exam', ['0'])[0] == '1':
                    if target.suffix.lower() not in {'.md', '.txt', '.srt', '.vtt', '.json'}:
                        raise ValueError('시험 자료함에는 전사본·노트 파일을 넣어 주세요.')
                    destination = app.library / 'exam-inbox' / filename
                    if destination.exists():
                        destination = destination.with_name(destination.stem + '-' + secrets.token_hex(4) + destination.suffix)
                    os.replace(target, destination)
                    return self.respond(200, {'ok': True, 'exam': True})
                guessed_title, guessed_course = inferred_names(filename)
                ident = app.import_file(target, query.get('title', [''])[0] or guessed_title, query.get('course', [''])[0] or guessed_course)
                return self.respond(200, {'ok': True, 'id': ident})
            finally:
                target.unlink(missing_ok=True)
        data = self.body()
        if url.path == '/api/settings':
            return self.respond(200, app.update_settings(data))
        if url.path == '/api/notes':
            current = app.lecture(data['id'])['notes']
            if 'base' in data and data['base'] != current:
                raise ValueError('Obsidian 또는 다른 화면에서 수정된 내용이 있습니다. 변경사항을 복사한 뒤 다시 열어 병합하세요.')
            app.save_notes(data['id'], data['text'])
            return self.respond(200, {'ok': True})
        if url.path == '/api/rename':
            app.rename(data['id'], data['title'], data.get('course', ''))
            return self.respond(200, {'ok': True})
        if url.path == '/api/process':
            app.lecture(data['id'])
            return self.respond(200, {'job': app.enqueue('lecture', data['id'])})
        if url.path == '/api/bind-lecture':
            return self.respond(200, {'binding': app.bind_lecture(data['id'], data.get('context', {}))})
        if url.path == '/api/reorganize':
            lecture = app.lecture(data['id'])
            if lecture['sync_status'] or not lecture['transcript'].get('text', '').strip():
                raise ValueError('저장된 전사본의 동기화를 완료하거나 기존 전사본을 연결하세요.')
            with app.lock, app.db() as db:
                active = db.execute("SELECT id FROM jobs WHERE target=? AND status IN ('queued','running')", (data['id'],)).fetchone()
                if active:
                    raise ValueError('이 강의의 기존 작업이 완료된 뒤 다시 정리하세요.')
                job = app.enqueue('renote', data['id'])
            return self.respond(200, {'job': job})
        if url.path == '/api/retry':
            app.retry(data['id'])
            return self.respond(200, {'ok': True})
        if url.path == '/api/exam':
            return self.respond(200, {'job': app.exam(ids=data.get('ids', []), title=data.get('title', '시험 대비 자료'))})
        if url.path == '/api/download-complete':
            # A download event never grants arbitrary filesystem access.
            path = inside(app.config['watch_folder'], data.get('filename', ''))
            if not path.is_file():
                raise ValueError('다운로드 파일을 찾지 못했습니다.')
            return self.respond(200, {'id': app.import_file(path, data.get('title', ''), data.get('course', ''))})
        if url.path == '/api/open-folder':
            if data.get('id'):
                folder = Path(app.lecture(data['id'])['folder'])
            else:
                names = {'library': app.library, 'inbox': Path(app.config['watch_folder']), 'exam-inbox': app.library / 'exam-inbox', 'extension': app.root / 'extension', 'exams': app.library / 'exams', 'vault': Path(app.config['vault_folder'])}
                folder = names.get(data.get('name'))
            if not folder or not folder.is_dir():
                raise ValueError('폴더를 찾지 못했습니다.')
            if os.name == 'nt':
                os.startfile(str(folder))
            return self.respond(200, {'ok': True, 'path': str(folder)})
        if url.path == '/api/shutdown':
            app.stop.set()
            self.respond(200, {'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        return self.respond(404, {'error': '지원하지 않는 작업'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--init-only', action='store_true')
    args = parser.parse_args()
    if not args.init_only:
        import urllib.request
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/health', timeout=1) as response:
                if json.load(response).get('app') == 'lecture-notes':
                    print('Lecture Notes is already running.', flush=True)
                    return
        except (OSError, ValueError):
            pass
    app = Library(args.root)
    config = {'base': f'http://127.0.0.1:{args.port}', 'token': app.config['token']}
    atomic(app.root / 'extension' / 'config.local.js', 'globalThis.LN_CONFIG = ' + json.dumps(config) + ';\n')
    if args.init_only:
        print('Local configuration initialized. No API call was made.')
        return
    server = Server(('127.0.0.1', args.port), app)
    app.start()
    print(f'Lecture Notes ready: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    finally:
        app.stop.set()
        server.server_close()

if __name__ == '__main__':
    main()
