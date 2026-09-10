"""Convenience-focused Library wrapper.

Keeps arbitrary Downloads folders event-only by default, adds reversible
archiving, simple quality presets, and coherence passes for long AI outputs.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import time

from core import AUDIO, TEXT, atomic, inside, load, split_text, transcript_md
from library import Library
from provider import NOTES_PROMPT, EXAM_PROMPT, ProviderError


QUALITY_MODELS = {
    'fast': 'gpt-5.6-luna',
    'balanced': 'gpt-5.6-terra',
    'precise': 'gpt-5.6-sol',
}

FINALIZE_NOTES_PROMPT = '''아래 Markdown은 같은 대학 강의의 여러 구간을 각각 정리한 초안이다.
내용을 새로 만들거나 요약해서 삭제하지 말고, 초안에 있는 사실·수식·코드·예시·조건을 모두 보존한 채 하나의 일관된 강의노트로 정돈하라.
- 반복되는 제목과 실질적으로 같은 불릿만 합친다.
- 같은 개념의 용어·표기를 통일한다.
- 구간 경계 때문에 끊어진 부모/자식 관계와 제목 계층을 자연스럽게 연결한다.
- 원래 강의 순서를 유지한다. 멀리 떨어진 내용을 임의로 재배치하지 않는다.
- 외부 지식, 복습 문제, 새로운 예시는 추가하지 않는다.
- 내용 손실이 의심되면 합치지 말고 둘 다 남긴다.
- 최상위 # 제목은 출력하지 말고 ## 이하의 완성된 Markdown 본문만 출력한다.'''

EXAM_MERGE_PROMPT = '''아래 내용은 시험 범위를 여러 구간으로 나눠 정리한 결과다. 모든 구간을 근거로 하나의 시험 대비 자료로 통합하라.
반드시 지킬 것:
- 각 구간의 핵심 개념, 정의, 비교, 과정, 예시와 [파일명 · 시각 또는 구간] 근거를 빠뜨리지 않는다.
- 같은 개념은 중복을 줄여 한곳에 통합하되 서로 다른 설명이나 조건은 보존한다.
- 전체 범위의 개념 관계와 비교가 드러나게 구조화한다.
- 자료에 없는 사실이나 실제 출제 예측을 만들어내지 않는다. 근거가 불충분하면 확인 필요로 남긴다.
- 자가점검 문제와 정답·해설은 제공된 자료에서 답할 수 있는 범위에서만 만든다.
- 결과는 완성된 Markdown 본문만 출력한다.'''


class ConvenienceLibrary(Library):
    def __init__(self, root, client_factory=None):
        super().__init__(root, client_factory=client_factory)
        changed = False
        if 'watch_all_files' not in self.config:
            self.config['watch_all_files'] = False
            changed = True
        if 'archived_lectures' not in self.config:
            self.config['archived_lectures'] = []
            changed = True
        if 'archive_view' not in self.config:
            self.config['archive_view'] = False
            changed = True
        if 'finalize_long_notes' not in self.config:
            self.config['finalize_long_notes'] = True
            changed = True
        if 'quality_preset' not in self.config:
            legacy = self.config.get('text_model', 'gpt-4.1-mini')
            inverse = {model: name for name, model in QUALITY_MODELS.items()}
            if legacy == 'gpt-4.1-mini':
                self.config['quality_preset'] = 'balanced'
                self.config['text_model'] = QUALITY_MODELS['balanced']
            else:
                self.config['quality_preset'] = inverse.get(legacy, 'custom')
            changed = True
        self._include_archived_internal = False
        if changed:
            atomic(self.private / 'settings.json', self.config)

    def _archived(self):
        return {str(value) for value in self.config.get('archived_lectures', [])}

    def _all_lectures(self):
        previous = self._include_archived_internal
        self._include_archived_internal = True
        try:
            return self.list_lectures()
        finally:
            self._include_archived_internal = previous

    def public_settings(self):
        archived = self._archived()
        return super().public_settings() | {
            'watch_all_files': bool(self.config.get('watch_all_files', False)),
            'quality_preset': self.config.get('quality_preset', 'custom'),
            'finalize_long_notes': bool(self.config.get('finalize_long_notes', True)),
            'archive_view': bool(self.config.get('archive_view', False)),
            'archived_count': len(archived),
        }

    def list_lectures(self):
        rows = super().list_lectures()
        archived = self._archived()
        for row in rows:
            row['archived'] = row['id'] in archived
            metadata = load(Path(row['folder']) / 'manifest.json', {})
            row['import_source'] = metadata.get('import_source', '')
        if self._include_archived_internal:
            return rows
        archive_view = bool(self.config.get('archive_view', False))
        return [row for row in rows if (row['id'] in archived) == archive_view]

    def lecture(self, ident):
        data = super().lecture(ident)
        data['archived'] = ident in self._archived()
        metadata = load(Path(data['folder']) / 'manifest.json', {})
        data['import_source'] = metadata.get('import_source', '')
        return data

    def import_file(self, path, title='', course='', process=None):
        original = Path(path).resolve()
        ident = super().import_file(original, title=title, course=course, process=process)
        lecture = super().lecture(ident)
        folder = Path(lecture['folder'])
        metadata = load(folder / 'manifest.json', {})
        if not metadata.get('import_source'):
            source = 'manual'
            try:
                if original.is_relative_to((self.library / 'inbox').resolve()):
                    source = 'inbox'
                elif original.is_relative_to(Path(self.config['watch_folder']).resolve()):
                    source = 'downloads'
                elif original.is_relative_to(self.private / 'uploads'):
                    source = 'manual'
            except (OSError, ValueError):
                pass
            metadata['import_source'] = source
            metadata['schema'] = max(2, int(metadata.get('schema', 1)))
            atomic(folder / 'manifest.json', metadata)
        return ident

    def update_settings(self, data):
        data = dict(data)
        watch_all = data.pop('watch_all_files', None)
        archive_view = data.pop('archive_view', None)
        archive_id = str(data.pop('archive_id', '') or '')
        restore_id = str(data.pop('restore_id', '') or '')
        archive_unclassified = bool(data.pop('archive_unclassified', False))
        restore_all = bool(data.pop('restore_all_archived', False))
        finalize = data.pop('finalize_long_notes', None)
        preset = data.pop('quality_preset', None)

        if preset is not None:
            preset = str(preset)
            if preset not in set(QUALITY_MODELS) | {'custom'}:
                raise ValueError('AI 품질 설정이 올바르지 않습니다.')
            if preset in QUALITY_MODELS:
                data['text_model'] = QUALITY_MODELS[preset]
        elif 'text_model' in data:
            inverse = {model: name for name, model in QUALITY_MODELS.items()}
            preset = inverse.get(str(data['text_model']).strip(), 'custom')

        if data:
            super().update_settings(data)

        with self.lock:
            archived = self._archived()
            valid_ids = {row['id'] for row in super().list_lectures()}
            if archive_id:
                if archive_id not in valid_ids:
                    raise ValueError('보관할 강의를 찾지 못했습니다.')
                archived.add(archive_id)
            if restore_id:
                archived.discard(restore_id)
            if archive_unclassified:
                archived.update(row['id'] for row in super().list_lectures() if not row['course'] or row['course'] == '미분류')
            if restore_all:
                archived.clear()
            self.config['archived_lectures'] = sorted(archived & valid_ids)
            if archive_view is not None:
                self.config['archive_view'] = bool(archive_view)
            if watch_all is not None:
                self.config['watch_all_files'] = bool(watch_all)
            if finalize is not None:
                self.config['finalize_long_notes'] = bool(finalize)
            if preset is not None:
                self.config['quality_preset'] = preset
            atomic(self.private / 'settings.json', self.config)
        return self.public_settings()

    def bind_lecture(self, ident, data):
        # Binding reassignment must also inspect archived items so a page never
        # remains attached to two lectures merely because one is hidden.
        previous = self._include_archived_internal
        self._include_archived_internal = True
        try:
            return super().bind_lecture(ident, data)
        finally:
            self._include_archived_internal = previous

    def notes(self, lecture, transcript, job, replace=False):
        folder = Path(lecture['folder'])
        if (folder / '강의노트.md').exists() and not replace:
            return
        source = transcript_md(transcript).removeprefix('# 전사본\n\n')
        if not source.strip():
            raise ValueError('저장된 전사본이 없습니다. 기존 전사본을 연결한 뒤 다시 정리하세요.')
        parts = split_text(source)
        self.status(job, f'노트 구성 중 · {len(parts)}개 구간')

        def one(pair):
            index, text = pair
            context = parts[index - 1][-600:] if index else ''
            following = parts[index + 1][:600] if index + 1 < len(parts) else ''
            return self.generated(
                folder,
                NOTES_PROMPT,
                f"강의: {lecture['title']}\n자료 구간 {index+1}/{len(parts)}\n이전 문맥(출력 제외): {context}\n다음 문맥(출력 제외): {following}\n\n현재 구간:\n{text}",
            )

        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(one, enumerate(parts)))

        body_text = '\n\n'.join(results)
        if len(parts) > 1 and self.config.get('finalize_long_notes', True):
            self.status(job, '노트 최종 정리 중 · 제목·용어·계층 통합')
            finalized = self.generated(
                folder,
                FINALIZE_NOTES_PROMPT,
                f"강의명: {lecture['title']}\n\n구간별 초안:\n{body_text}",
            ).strip()
            finalized = re.sub(r'^#\s+[^\n]+\n+', '', finalized, count=1).strip()
            if finalized:
                body_text = finalized

        body = '# ' + lecture['title'] + '\n\n' + body_text + '\n'
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

    def run_exam(self, target, job):
        folder = inside(self.library / 'exams', target)
        payload = load(folder / 'sources.json')
        source = '\n\n'.join('=== FILE: ' + s['name'] + ' ===\n' + s['text'] for s in payload['sources'])
        atomic(folder / '원본자료모음.md', '# 원본 자료 모음\n\n' + source)
        parts = split_text(source, 22000)
        self.status(job, f'시험 범위 핵심 추출 중 · {len(parts)}개 구간 · 재전사 없음')

        if len(parts) == 1:
            body = self.generated(folder, EXAM_PROMPT, source)
        else:
            def one(pair):
                index, text = pair
                value = self.generated(
                    folder,
                    EXAM_PROMPT,
                    f'전체 자료 중 구간 {index+1}/{len(parts)}. 입력에 있는 파일명 근거를 유지하고 현재 구간을 빠짐없이 정리하세요.\n{text}',
                )
                atomic(folder / f'범위별정리-{index+1:03d}.md', value)
                return value

            with ThreadPoolExecutor(max_workers=3) as pool:
                sections = list(pool.map(one, enumerate(parts)))
            draft = '\n\n--- 구간 경계 ---\n\n'.join(sections)
            self.status(job, '시험 자료 최종 통합 중 · 중복 제거·개념 관계 정리')
            try:
                body = self.generated(folder, EXAM_MERGE_PROMPT, draft)
            except (ProviderError, ValueError):
                # Detailed map outputs are already complete and grounded. If a
                # final synthesis call fails, still leave a usable result.
                body = draft
                self.status(job, '최종 통합을 건너뛰고 범위별 정리본을 보존했습니다.')

        final = '# ' + payload['title'] + '\n\n' + body.strip() + '\n'
        atomic(folder / '시험대비.md', final)
        vault_exam = Path(self.config['vault_folder']) / '시험대비' / (folder.name + '.md')
        if not vault_exam.exists():
            atomic(vault_exam, final)

    def scan(self):
        # Always scan the app-owned inbox. Scan a user Downloads folder only
        # when they explicitly opt into full-folder monitoring.
        folders = {self.library / 'inbox'}
        if self.config.get('watch_all_files', False):
            folders.add(Path(self.config['watch_folder']).resolve())

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

        # Background maintenance always sees every lecture, regardless of the
        # user's active/archive view.
        for lecture in super().list_lectures():
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
