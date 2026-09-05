"""Folder-first lecture library, persistent queue, cached STT and note generation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time

from core import AUDIO, TEXT, atomic, load, digest, slug, inside, stamp, parse_transcript, normalize_segments, transcript_md, transcript_srt, protect, split_text, inferred_names
from provider import OpenAI, ProviderError, NOTES_PROMPT, EXAM_PROMPT
from vault_sync import VaultSync

class Library(VaultSync):
    def __init__(self, root, client_factory=None):
        self.root = Path(root).resolve()
        self.private = self.root / '.local'
        self.library = self.root / 'library'
        for folder in [self.private, self.library / 'inbox', self.library / 'exam-inbox', self.library / 'lectures', self.library / 'exams', self.private / 'uploads']:
            folder.mkdir(parents=True, exist_ok=True)
        self.config = load(self.private / 'settings.json', {})
        self.config.setdefault('token', secrets.token_urlsafe(32))
        self.config.setdefault('text_model', 'gpt-4.1-mini')
        self.config.setdefault('timed', False)
        self.config.setdefault('vault_folder', str(self.root / 'Obsidian'))
        Path(self.config['vault_folder']).mkdir(parents=True, exist_ok=True)
        self.config.setdefault('auto_process', True)
        self.config.setdefault('watch_folder', str(self.library / 'inbox'))
        atomic(self.private / 'settings.json', self.config)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.client_factory = client_factory
        self.seen = {}
        self.watch_error = ''
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS lectures(id TEXT PRIMARY KEY, hash TEXT UNIQUE, title TEXT, course TEXT, folder TEXT, source TEXT, kind TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT, target TEXT, status TEXT, progress TEXT, error TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS sources(path TEXT PRIMARY KEY, signature TEXT, lecture_id TEXT);
            CREATE TABLE IF NOT EXISTS exam_runs(signature TEXT PRIMARY KEY, job_id TEXT);''')
            db.execute("UPDATE jobs SET status='queued', progress='중단된 작업 재개 대기' WHERE status='running'")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.private / 'index.sqlite', timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def key(self):
        if self.client_factory:
            return 'test-key'
        if os.environ.get('OPENAI_API_KEY'):
            return os.environ['OPENAI_API_KEY']
        encrypted = self.config.get('api_key_dpapi')
        return protect(encrypted, decrypt=True) if encrypted else ''

    def client(self):
        key = self.key()
        if not key:
            raise ProviderError('설정에서 OpenAI API 키를 입력하세요.')
        return self.client_factory() if self.client_factory else OpenAI(key, self.config['text_model'])

    def public_settings(self):
        try:
            has_key = bool(self.key())
        except OSError:
            has_key = False
        return {k: self.config[k] for k in ['text_model', 'timed', 'auto_process', 'watch_folder', 'vault_folder']} | {'has_key': has_key, 'library': str(self.library), 'ffmpeg': bool(shutil.which('ffmpeg')), 'watch_error': self.watch_error}

    def update_settings(self, data):
        with self.lock:
            updated = dict(self.config)
            if data.get('api_key'):
                updated['api_key_dpapi'] = protect(str(data['api_key']).strip())
            if 'watch_folder' in data:
                path = Path(data['watch_folder']).expanduser().resolve()
                if not path.is_dir():
                    raise ValueError('감시 폴더가 없습니다. 탐색기에서 폴더를 만든 뒤 지정하세요.')
                # Never watch generated files and feed them back into the import pipeline.
                if path == self.library or path == self.root or path.is_relative_to(self.library / 'lectures') or path.is_relative_to(self.library / 'exams'):
                    raise ValueError('결과 보관 폴더 대신 다운로드 전용 폴더를 지정하세요.')
                updated['watch_folder'] = str(path)
            if 'vault_folder' in data:
                vault = Path(data['vault_folder']).expanduser().resolve()
                if not vault.is_dir():
                    raise ValueError('Obsidian 보관함 폴더가 없습니다. 먼저 폴더를 만들어 주세요.')
                if vault == self.root or vault.is_relative_to(self.library):
                    raise ValueError('자료함과 분리된 Obsidian 보관함 폴더를 지정하세요.')
                updated['vault_folder'] = str(vault)
            for name in ['timed', 'auto_process']:
                if name in data:
                    updated[name] = bool(data[name])
            if 'text_model' in data:
                model = str(data['text_model']).strip()
                if not model or len(model) > 100 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_' for c in model):
                    raise ValueError('모델 이름이 올바르지 않습니다.')
                updated['text_model'] = model
            watch, vault = Path(updated['watch_folder']).resolve(), Path(updated['vault_folder']).resolve()
            if self.root.is_relative_to(watch) or watch.is_relative_to(vault) or vault.is_relative_to(watch):
                raise ValueError('자동 입력 폴더와 Obsidian 출력 폴더를 분리하세요. 상위 폴더 전체를 감시할 수 없습니다.')
            atomic(self.private / 'settings.json', updated)
            vault_changed = Path(self.config['vault_folder']).resolve() != vault
            self.config = updated
            if vault_changed:
                # Make a successful settings response mean the existing notes are
                # already available at the selected location, not a future scan.
                for lecture in self.list_lectures():
                    self.export(lecture['id'])
        return self.public_settings()

    def list_lectures(self):
        with self.db() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM lectures ORDER BY created DESC')]
        for row in rows:
            folder = inside(self.library, row['folder'])
            row['has_transcript'] = (folder / 'transcript.json').exists()
            row['has_notes'] = (folder / '강의노트.md').exists()
            row['bindings'] = load(folder / 'bindings.json', [])
            row['sync_status'] = self.sync_status(load(folder / 'export.json', {}))
        return rows

    def lecture(self, ident):
        with self.db() as db:
            row = db.execute('SELECT * FROM lectures WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('강의를 찾지 못했습니다.')
        data = dict(row)
        folder = inside(self.library, data['folder'])
        data['transcript'] = load(folder / 'transcript.json', {})
        exported = load(folder / 'export.json', {})
        note = self.valid_export(exported, 'note') if exported.get('note') else folder / '강의노트.md'
        data['notes'] = note.read_text(encoding='utf-8-sig') if note.exists() else ''
        data['note_path'] = str(note)
        data['bindings'] = load(folder / 'bindings.json', [])
        data['sync_status'] = self.sync_status(exported)
        data['files'] = [p.name for p in folder.iterdir() if p.is_file() and not p.name.startswith('.')]
        return data

    def enqueue(self, kind, target):
        with self.lock, self.db() as db:
            old = db.execute("SELECT id FROM jobs WHERE kind=? AND target=? AND status IN ('queued','running')", (kind, target)).fetchone()
            if old:
                return old['id']
            ident = secrets.token_hex(12)
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)', (ident, kind, target, 'queued', '대기 중', '', time.time()))
            return ident

    def import_file(self, path, title='', course='', process=None):
        path = Path(path).resolve()
        ext = path.suffix.lower()
        if ext not in AUDIO | TEXT or not path.is_file():
            raise ValueError('지원 파일: MP3/MP4/M4A/WAV/WEBM, TXT/MD/SRT/VTT/JSON')
        if path.stat().st_size > 2_000_000_000:
            raise ValueError('파일 하나는 2GB 이하로 가져오세요.')
        file_hash = digest(path)
        with self.lock, self.db() as db:
            existing = db.execute('SELECT id FROM lectures WHERE hash=?', (file_hash,)).fetchone()
            if existing:
                return existing['id']
            ident = file_hash[:24]
            guessed_title, guessed_course = inferred_names(path.name)
            title = str(title or guessed_title)[:200]
            course = course or guessed_course
            folder = self.library / 'lectures' / f'{ident[:12]}-{slug(title)}'
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / ('source' + ext)
            # Source copy and parsed output finish before the index exposes the lecture.
            shutil.copy2(path, target)
            kind = 'audio' if ext in AUDIO else 'notes' if ext == '.md' and any(w in path.stem.lower() for w in ['노트', 'note', '요약']) else 'transcript'
            if kind != 'audio':
                transcript = parse_transcript(target)
                if not transcript.get('text', '').strip():
                    raise ValueError('읽을 수 있는 전사/노트 본문이 없습니다.')
                self.write_transcript(folder, transcript)
                if kind == 'notes':
                    atomic(folder / '강의노트.md', target.read_text(encoding='utf-8-sig'))
            metadata = {'id': ident, 'title': title, 'course': str(course)[:200], 'sha256': file_hash, 'source': target.name, 'kind': kind, 'created': time.time(), 'schema': 1}
            atomic(folder / 'manifest.json', metadata)
            db.execute('INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?)', (ident, file_hash, title, str(course)[:200], str(folder), target.name, kind, metadata['created']))
        self.export(ident)
        if (self.config['auto_process'] if process is None else process) and kind != 'notes':
            self.enqueue('lecture', ident)
        return ident

    def write_transcript(self, folder, transcript):
        atomic(folder / 'transcript.json', transcript)
        atomic(folder / '전사본.md', transcript_md(transcript))
        if transcript.get('timed'):
            atomic(folder / '전사본.srt', transcript_srt(transcript))

    def status(self, job, progress, status=None, error=''):
        with self.db() as db:
            if status:
                db.execute('UPDATE jobs SET progress=?,status=?,error=? WHERE id=?', (progress, status, error, job))
            else:
                db.execute('UPDATE jobs SET progress=? WHERE id=?', (progress, job))

    def jobs(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 100')]

    def retry(self, ident):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='queued', error='', progress='저장된 결과부터 재시도' WHERE id=? AND status='error'", (ident,))

    def transcribe(self, lecture, job):
        folder = Path(lecture['folder'])
        cached = load(folder / 'transcript.json')
        if cached:
            return cached
        self.status(job, '오디오 준비 중')
        chunks_dir = folder / '.cache' / 'audio'
        chunks_dir.mkdir(parents=True, exist_ok=True)
        parts = sorted(chunks_dir.glob('part-*.mp3'))
        ready = chunks_dir / 'ready.json'
        if not ready.exists():
            exe = shutil.which('ffmpeg')
            if not exe:
                raise ProviderError('FFmpeg가 필요합니다. setup.ps1을 실행하세요.')
            command = [exe, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', str(folder / lecture['source']), '-vn', '-ac', '1', '-ar', '16000', '-b:a', '64k', '-f', 'segment', '-segment_time', '600', '-reset_timestamps', '1', str(chunks_dir / 'part-%04d.mp3')]
            try:
                result = subprocess.run(command, capture_output=True, timeout=7200, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except (OSError, subprocess.TimeoutExpired):
                raise ProviderError('오디오 변환을 실행하지 못했습니다.') from None
            parts = sorted(chunks_dir.glob('part-*.mp3'))
            if result.returncode or not parts:
                raise ProviderError('오디오 파일을 읽지 못했습니다. 다운로드 완료 여부를 확인하세요.')
            atomic(ready, {'parts': [p.name for p in parts]})
        else:
            parts = [chunks_dir / name for name in load(ready)['parts']]
        timed = bool(self.config['timed'])
        mode = 'timed-whisper' if timed else 'fast-mini'
        completed = 0
        progress_lock = threading.Lock()
        def one(pair):
            nonlocal completed
            index, part = pair
            cache = chunks_dir / f'{part.stem}-{mode}.json'
            data = load(cache)
            if data is None:
                data = self.client().transcribe(part, timed=timed)
                if not str(data.get('text', '')).strip() and not data.get('segments'):
                    raise ProviderError('음성 구간에서 텍스트를 얻지 못했습니다.')
                atomic(cache, data)
            with progress_lock:
                completed += 1
                self.status(job, f'전사 {completed}/{len(parts)} 구간 완료 · 최대 3개 동시 처리')
            return index, data
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(one, enumerate(parts)))
        text = '\n\n'.join(str(data.get('text', '')).strip() for _, data in results)
        segments = []
        for index, data in results:
            segments.extend({'start': float(s['start']) + index * 600, 'end': float(s['end']) + index * 600, 'text': s['text']} for s in data.get('segments', []))
        transcript = {'text': text, 'segments': normalize_segments(segments), 'timed': timed, 'model': 'whisper-1' if timed else 'gpt-4o-mini-transcribe', 'audio_chunks': len(parts)}
        self.write_transcript(folder, transcript)
        return transcript

    def generated(self, folder, prompt, text, progress=None):
        # Content-addressed cache includes prompt and model so retry does not repeat completed calls.
        key = hashlib.sha256((self.config['text_model'] + prompt + text).encode()).hexdigest()
        cache = folder / '.cache' / (key + '.md')
        if cache.exists():
            return cache.read_text(encoding='utf-8')
        value = self.client().generate(prompt, text)
        atomic(cache, value)
        return value

    def notes(self, lecture, transcript, job, replace=False):
        folder = Path(lecture['folder'])
        if (folder / '강의노트.md').exists() and not replace:
            return
        # The storage wrapper is not lecture content and must not become an AI heading.
        source = transcript_md(transcript).removeprefix('# 전사본\n\n')
        if not source.strip():
            raise ValueError('저장된 전사본이 없습니다. 기존 전사본을 연결한 뒤 다시 정리하세요.')
        parts = split_text(source)
        self.status(job, f'AI 강의노트 작성 중 · {len(parts)}개 구간')
        def one(pair):
            index, text = pair
            context = parts[index - 1][-600:] if index else ''
            following = parts[index + 1][:600] if index + 1 < len(parts) else ''
            return self.generated(folder, NOTES_PROMPT, f"강의: {lecture['title']}\n자료 구간 {index+1}/{len(parts)}\n이전 문맥(출력 제외): {context}\n다음 문맥(출력 제외): {following}\n\n현재 구간:\n{text}")
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(one, enumerate(parts)))
        body = '# ' + lecture['title'] + '\n\n' + '\n\n'.join(results) + '\n'
        if replace:
            with self.lock:
                latest = self.lecture(lecture['id'])
                if latest['notes'] != lecture['notes'] or latest['note_path'] != lecture['note_path']:
                    atomic(folder / 'versions' / (job + '-AI-재정리.md'), body)
                    raise ValueError('생성 중 노트가 변경되어 덮어쓰지 않았습니다. 원본 폴더의 versions에 AI 결과를 보관했습니다.')
                self.save_notes(lecture['id'], body)
            return
        atomic(folder / '강의노트.md', body)
        self.export(lecture['id'])

    def valid_export(self, exported, key):
        return inside(Path(exported['vault']) / '강의노트', exported[key])

    def export(self, ident):
        """Vault file becomes authoritative once exported; preserve Obsidian edits."""
        with self.lock:
            if ident in getattr(self, 'sync_blocked', set()):
                return
            lecture = self.lecture(ident)
            folder = Path(lecture['folder'])
            old = load(folder / 'export.json', {})
            vault = Path(self.config['vault_folder']).resolve()
            course = slug(lecture['course'] or '미분류')
            title = slug(lecture['title'])
            destination = inside(vault, vault / '강의노트' / course)
            destination.mkdir(parents=True, exist_ok=True)
            changed = old.get('vault') != str(vault) or old.get('course') != course or old.get('title') != title
            # Explicitly tracked files only. Never overwrite unrelated existing notes.
            if not old or changed:
                note = destination / (title + '.md')
                if note.exists():
                    note = destination / (title + '-' + ident[:8] + '.md')
                if note.exists() and str(note) != old.get('note'):
                    note = destination / (title + '-' + secrets.token_hex(4) + '.md')
                transcript = destination / '전사본' / (note.stem + '.md')
                if transcript.exists() and str(transcript) != old.get('transcript'):
                    transcript = transcript.with_name(transcript.stem + '-' + ident[:8] + '.md')
                if lecture['notes']:
                    atomic(note, lecture['notes'])
                exported = {'vault': str(vault), 'course': course, 'title': title, 'note': str(note), 'transcript': str(transcript)}
                atomic(folder / 'export.json', exported)
            else:
                exported = old
                note = self.valid_export(exported, 'note')
            internal = folder / '강의노트.md'
            if note.exists():
                content = note.read_text(encoding='utf-8-sig')
                if content.strip() and (not internal.exists() or internal.read_text(encoding='utf-8-sig') != content):
                    if internal.exists():
                        self.backup_vault_note(ident, internal.read_text(encoding='utf-8-sig'))
                    atomic(internal, content)
                exported['note_created'] = True
            elif internal.exists() and not exported.get('note_created'):
                atomic(note, internal.read_text(encoding='utf-8-sig'))
                exported['note_created'] = True
            source = folder / '전사본.md'
            transcript_path = self.valid_export(exported, 'transcript')
            if source.exists() and not transcript_path.exists() and not exported.get('transcript_created'):
                atomic(transcript_path, source.read_text(encoding='utf-8-sig'))
            if transcript_path.exists():
                exported['transcript_created'] = True
            atomic(folder / 'export.json', exported)
            self.publish_record(lecture, exported)

    def rename(self, ident, title, course):
        title, course = str(title).strip()[:200], str(course).strip()[:200]
        if not title:
            raise ValueError('강의명을 입력하세요.')
        with self.lock, self.db() as db:
            db.execute('UPDATE lectures SET title=?, course=? WHERE id=?', (title, course, ident))
        lecture = self.lecture(ident)
        folder = Path(lecture['folder'])
        metadata = load(folder / 'manifest.json', {})
        atomic(folder / 'manifest.json', metadata | {'title': title, 'course': course})
        self.export(ident)

    def save_notes(self, ident, text):
        lecture = self.lecture(ident)
        if lecture['sync_status']:
            raise ValueError('동기화 대기 파일이 있습니다. Obsidian 동기화 완료 또는 휴지통 복원 후 저장하세요.')
        folder = Path(lecture['folder'])
        old = folder / '강의노트.md'
        if old.exists():
            self.backup_vault_note(ident, lecture['notes'])
            atomic(folder / 'versions' / (str(time.time_ns()) + '.md'), lecture['notes'])
        atomic(old, str(text))
        exported = load(folder / 'export.json', {})
        if exported.get('note'):
            atomic(self.valid_export(exported, 'note'), str(text))
        self.export(ident)

    def attach_file(self, ident, path):
        """Attach an existing transcript or note to a chosen lecture, without STT."""
        path = Path(path)
        if path.suffix.lower() not in TEXT:
            raise ValueError('연결할 파일은 MD/TXT/SRT/VTT/JSON 전사본 또는 노트여야 합니다.')
        lecture = self.lecture(ident)
        folder = Path(lecture['folder'])
        if path.suffix.lower() == '.md' and any(w in path.stem.lower() for w in ['노트', 'note', '요약']):
            self.save_notes(ident, path.read_text(encoding='utf-8-sig'))
        else:
            transcript = parse_transcript(path)
            if not transcript.get('text', '').strip():
                raise ValueError('전사본 본문이 비어 있습니다.')
            previous = folder / 'transcript.json'
            if previous.exists():
                atomic(folder / 'versions' / (str(time.time_ns()) + '-transcript.json'), load(previous))
            self.write_transcript(folder, transcript)
            exported = load(folder / 'export.json', {})
            if exported.get('transcript'):
                atomic(self.valid_export(exported, 'transcript'), transcript_md(transcript))
            # Existing notes remain intact; generating missing notes reuses this transcript.
            self.export(ident)
        return ident

    def exam(self, ids=None, paths=None, title='시험 대비 자료'):
        sources = []
        for ident in dict.fromkeys(ids or []):
            self.export(ident)
            lecture = self.lecture(ident)
            folder = Path(lecture['folder'])
            for name in ['전사본.md', '강의노트.md']:
                if lecture['sync_status']:
                    raise ValueError('선택한 강의의 노트·전사본 동기화를 완료한 뒤 시험 자료를 만드세요.')
                p = folder / name
                if p.exists():
                    sources.append({'name': lecture['title'] + '/' + name, 'text': p.read_text(encoding='utf-8-sig')})
        for path in paths or []:
            path = inside(self.library / 'exam-inbox', path)
            if path.suffix.lower() not in TEXT:
                continue
            transcript = parse_transcript(path)
            sources.append({'name': path.name, 'text': transcript_md(transcript)})
        if not sources:
            raise ValueError('먼저 전사본 또는 노트를 선택/추가하세요. 시험 자료 생성은 음성을 재전사하지 않습니다.')
        payload = {'title': str(title)[:200], 'sources': sources}
        signature = hashlib.sha256((json.dumps(payload, ensure_ascii=False, sort_keys=True) + self.config['text_model']).encode()).hexdigest()
        with self.lock, self.db() as db:
            old = db.execute('SELECT job_id FROM exam_runs WHERE signature=?', (signature,)).fetchone()
            if old:
                return old['job_id']
            target = self.library / 'exams' / f'{slug(title)}-{signature[:12]}'
            target.mkdir(parents=True, exist_ok=True)
            atomic(target / 'sources.json', payload)
            job = self.enqueue('exam', str(target))
            db.execute('INSERT INTO exam_runs VALUES(?,?)', (signature, job))
            return job

    def run_exam(self, target, job):
        folder = inside(self.library / 'exams', target)
        payload = load(folder / 'sources.json')
        source = '\n\n'.join('=== FILE: ' + s['name'] + ' ===\n' + s['text'] for s in payload['sources'])
        atomic(folder / '원본자료모음.md', '# 원본 자료 모음\n\n' + source)
        self.status(job, '저장된 텍스트로 시험 자료 작성 중 · 재전사 없음')
        parts = split_text(source, 22000)
        if len(parts) == 1:
            body = self.generated(folder, EXAM_PROMPT, source)
        else:
            def one(pair):
                i, text = pair
                value = self.generated(folder, EXAM_PROMPT, f'전체 자료 중 구간 {i+1}/{len(parts)}. 입력에 있는 파일명 근거를 유지하세요.\n' + text)
                atomic(folder / f'범위별정리-{i+1:03d}.md', value)
                return value
            with ThreadPoolExecutor(max_workers=3) as pool:
                sections = list(pool.map(one, enumerate(parts)))
            # Do not silently truncate large sets: retain every detailed section in the main result.
            body = '\n\n---\n\n'.join(sections)
        atomic(folder / '시험대비.md', '# ' + payload['title'] + '\n\n' + body + '\n')
        vault_exam = Path(self.config['vault_folder']) / '시험대비' / (folder.name + '.md')
        if not vault_exam.exists():
            atomic(vault_exam, '# ' + payload['title'] + '\n\n' + body + '\n')

    def run_once(self):
        if not self.key():
            return False
        with self.lock, self.db() as db:
            job = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not job:
                return False
            job = dict(job)
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job['id'],))
        try:
            if job['kind'] in ('lecture', 'renote'):
                lecture = self.lecture(job['target'])
                if lecture['sync_status'] or (lecture['kind'] == 'synced' and not lecture['transcript'].get('text', '').strip()):
                    raise ValueError('노트·전사본 동기화가 완료된 뒤 다시 시도하세요. 다른 PC의 음성은 자동 재전사하지 않습니다.')
                transcript = self.transcribe(lecture, job['id']) if lecture['kind'] == 'audio' and job['kind'] != 'renote' else lecture['transcript']
                self.notes(lecture, transcript, job['id'], replace=job['kind'] == 'renote')
            else:
                self.run_exam(job['target'], job['id'])
            self.status(job['id'], '완료 · 파일로 저장됨', 'done')
        except Exception as error:
            message = str(error) if isinstance(error, (ProviderError, ValueError)) else '로컬 파일 처리에 실패했습니다. 파일과 저장 폴더를 확인하세요.'
            self.status(job['id'], '작업 중단', 'error', message[:500])
        return True

    def scan(self):
        folders = {self.library / 'inbox', Path(self.config['watch_folder']).resolve()}
        self.watch_error = ''
        self.sync_vault()
        for folder in folders:
            if not folder.is_dir():
                continue
            for path in folder.rglob('*'):
                try:
                    if not path.is_file() or path.suffix.lower() not in AUDIO | TEXT or path.is_symlink():
                        continue
                    stat = path.stat()
                    signature = f'{stat.st_size}:{stat.st_mtime_ns}'
                    key = str(path.resolve())
                    previous = self.seen.get(key)
                    self.seen[key] = signature
                    if previous != signature or time.time() - stat.st_mtime < 8:
                        continue
                    with self.db() as db:
                        old = db.execute('SELECT signature FROM sources WHERE path=?', (key,)).fetchone()
                    if old and old['signature'] == signature:
                        continue
                    relative = path.relative_to(folder)
                    ident = self.import_file(path, course=relative.parts[0] if len(relative.parts) > 1 else '')
                    with self.db() as db:
                        db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?)', (key, signature, ident))
                except (OSError, ValueError) as error:
                    self.watch_error = f'{path.name}: {str(error)[:160]}'
        for lecture in self.list_lectures():
            self.export(lecture['id'])
        paths = [p for p in (self.library / 'exam-inbox').rglob('*') if p.is_file() and not p.is_symlink() and p.suffix.lower() in TEXT]
        signature = '|'.join(f'{p}:{p.stat().st_size}:{p.stat().st_mtime_ns}' for p in sorted(paths))
        prior = self.seen.get('__exam__')
        self.seen['__exam__'] = signature
        if paths and signature == prior and all(time.time() - p.stat().st_mtime > 8 for p in paths) and self.config['auto_process']:
            try:
                self.exam(paths=paths)
            except (ValueError, OSError) as error:
                self.watch_error = str(error)[:200]

    def start(self):
        def worker():
            while not self.stop.is_set():
                try:
                    busy = self.run_once()
                except Exception:
                    busy = False
                self.stop.wait(0.2 if busy else 2)
        def watcher():
            while not self.stop.is_set():
                try:
                    self.scan()
                except Exception:
                    self.watch_error = '폴더 감시 오류: 경로와 파일 접근 권한을 확인하세요.'
                self.stop.wait(5)
        for target in [worker, watcher]:
            threading.Thread(target=target, daemon=True).start()
