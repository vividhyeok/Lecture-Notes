"""Portable Markdown index. Credentials, queues and absolute paths stay on each PC."""
import hashlib
import json
import re
import time
from urllib.parse import urlsplit, parse_qsl, urlencode
from pathlib import Path
from core import atomic, load, inside, slug, parse_transcript


class VaultSync:
    def clean_binding(self, data):
        if not isinstance(data, dict):
            raise ValueError('강의 연결 정보가 올바르지 않습니다.')
        result = {key: str(data.get(key, ''))[:200].strip() for key in ['course', 'title', 'module']}
        for key in ['pageKey', 'mediaKey']:
            value = str(data.get(key, ''))
            if not value:
                result[key] = ''
                continue
            url = urlsplit(value)
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
                raise ValueError('강의 주소가 올바르지 않습니다.')
            query = urlencode(sorted((k, v) for k, v in parse_qsl(url.query) if k in (['v'] if url.hostname in ('www.youtube.com', 'm.youtube.com', 'youtube.com') else []) + ['id', 'course_id', 'lecture_id', 'video_id', 'content_id', 'module_item_id']))
            result[key] = (url.scheme + '://' + url.netloc + url.path + ('?' + query if query else ''))[:2000]
        if not result['title'] or not result['pageKey']:
            raise ValueError('현재 열린 강의의 제목과 주소를 확인할 수 없습니다.')
        host = urlsplit(result['pageKey']).hostname or ''
        if host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com'):
            result['course'] = 'youtube'
        return result

    def bind_lecture(self, ident, data):
        binding = self.clean_binding(data)
        with self.lock:
            lecture = self.lecture(ident)
            if lecture['sync_status']:
                raise ValueError('노트 동기화를 완료한 뒤 연결하세요.')
            if binding['course'] == 'youtube' and lecture['course'] != 'youtube':
                self.rename(ident, lecture['title'], 'youtube')
            # Reassigning an explicit video connection must not leave two automatic targets.
            for row in self.list_lectures():
                path = Path(row['folder']) / 'bindings.json'
                previous = load(path, [])
                previous_without_video = [b for b in previous if b.get('pageKey') != binding['pageKey']]
                kept = [b for b in previous_without_video if not (b == binding or ((binding['mediaKey'] and b.get('mediaKey') == binding['mediaKey'] or b.get('pageKey') == binding['pageKey']) and b.get('title') == binding['title'] and b.get('course') == binding['course']))]
                if row['id'] == ident:
                    kept.append(binding)
                if kept != previous:
                    atomic(path, kept)
                    self.export(row['id'])
        return binding

    def backup_vault_note(self, ident, content):
        if content.strip():
            name = hashlib.sha256(content.encode('utf-8')).hexdigest()[:20] + '.md'
            path = Path(self.config['vault_folder']) / '강의노트' / '_관리' / '변경이력' / ident / name
            if not path.exists():
                atomic(path, content)

    def publish_record(self, lecture, exported):
        vault = Path(exported['vault'])
        record = {'schema': 1, 'id': lecture['id'], 'sha256': lecture['hash'],
                  'title': lecture['title'], 'course': lecture['course'],
                  'created': lecture['created']}
        record['bindings'] = load(Path(lecture['folder']) / 'bindings.json', [])
        for key in ['note', 'transcript']:
            record[key] = self.valid_export(exported, key).relative_to(vault).as_posix()
            record[key + '_created'] = bool(exported.get(key + '_created'))
        path = vault / '강의노트' / '_관리' / 'records' / (lecture['id'] + '.md')
        text = '# Lecture Notes 동기화 정보\n\n자동 관리 파일입니다. 노트와 함께 동기화하세요.\n\n```json\n' + json.dumps(record, ensure_ascii=False, indent=2) + '\n```\n'
        if not path.exists() or path.read_text(encoding='utf-8-sig') != text:
            atomic(path, text)

    def sync_vault(self):
        vault = Path(self.config['vault_folder']).resolve()
        records = vault / '강의노트' / '_관리' / 'records'
        self.sync_blocked = set()
        for path in records.glob('*.md'):
            if not re.fullmatch(r'[a-f0-9]{24}', path.stem):
                self.watch_error = '동기화 관리 파일 충돌 사본이 있습니다. 원본과 비교해 주세요: ' + path.name
                continue
            try:
                raw = path.read_text(encoding='utf-8-sig')
                match = re.search(r'```json\s*\n(.*?)\n```', raw, re.S)
                data = json.loads(match.group(1)) if match else {}
                ident = data['id']
                if data.get('schema') != 1 or ident != path.stem or not re.fullmatch(r'[a-f0-9]{64}', data['sha256']) or data['sha256'][:24] != ident:
                    raise ValueError('unsupported record')
                exported = {'vault': str(vault), 'course': slug(data['course'] or '미분류'), 'title': slug(data['title'])}
                for key in ['note', 'transcript']:
                    relative = Path(data[key])
                    if relative.is_absolute() or relative.suffix.lower() != '.md':
                        raise ValueError('invalid path')
                    target = inside(vault / '강의노트', vault / relative)
                    if target.is_relative_to(records.parent):
                        raise ValueError('reserved path')
                    exported[key] = str(target)
                    exported[key + '_created'] = bool(data.get(key + '_created'))
                bindings = data.get('bindings', [])
                if not isinstance(bindings, list) or len(bindings) > 100:
                    raise ValueError('invalid bindings')
                bindings = [self.clean_binding(b) for b in bindings]
                with self.lock, self.db() as db:
                    row = db.execute('SELECT * FROM lectures WHERE id=?', (ident,)).fetchone()
                    folder = inside(self.library, row['folder']) if row else self.library / 'lectures' / (ident + '-synced')
                    folder.mkdir(parents=True, exist_ok=True)
                    if not row:
                        db.execute('INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?)', (ident, data['sha256'], str(data['title'])[:200], str(data['course'])[:200], str(folder), '', 'synced', float(data.get('created', time.time()))))
                        atomic(folder / 'manifest.json', data | {'kind': 'synced', 'source': ''})
                    else:
                        db.execute('UPDATE lectures SET title=?,course=? WHERE id=?', (str(data['title'])[:200], str(data['course'])[:200], ident))
                    atomic(folder / 'export.json', exported)
                    atomic(folder / 'bindings.json', bindings)
                    transcript = Path(exported['transcript'])
                    if transcript.is_file() and transcript.stat().st_size:
                        text = transcript.read_text(encoding='utf-8-sig')
                        cached = folder / '전사본.md'
                        if text.strip() and (not cached.exists() or cached.read_text(encoding='utf-8-sig') != text):
                            parsed = parse_transcript(transcript)
                            atomic(folder / 'transcript.json', parsed)
                            atomic(cached, text)
            except (OSError, ValueError, KeyError, TypeError):
                self.sync_blocked.add(path.stem)
                self.watch_error = '동기화 관리 파일을 아직 읽을 수 없습니다: ' + path.name

    def sync_status(self, exported):
        missing = []
        for key, label in [('note', '노트'), ('transcript', '전사본')]:
            if exported.get(key + '_created'):
                path = self.valid_export(exported, key)
                if not path.is_file() or not path.stat().st_size:
                    missing.append(label)
        return ('동기화 대기 또는 삭제된 파일: ' + ', '.join(missing) + ' · 자동 복원·재전사하지 않습니다.') if missing else ''
