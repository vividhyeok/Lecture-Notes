"""Convenience-focused Library wrapper.

The dedicated library/inbox remains auto-scanned, while arbitrary external
folders are event-only by default. This prevents unrelated music/downloads
from silently becoming lectures.
"""
from pathlib import Path
import time

from core import AUDIO, TEXT, atomic
from library import Library


class ConvenienceLibrary(Library):
    def __init__(self, root, client_factory=None):
        super().__init__(root, client_factory=client_factory)
        if 'watch_all_files' not in self.config:
            self.config['watch_all_files'] = False
            atomic(self.private / 'settings.json', self.config)

    def public_settings(self):
        return super().public_settings() | {
            'watch_all_files': bool(self.config.get('watch_all_files', False)),
        }

    def update_settings(self, data):
        data = dict(data)
        watch_all = data.pop('watch_all_files', None)
        super().update_settings(data)
        if watch_all is not None:
            with self.lock:
                self.config['watch_all_files'] = bool(watch_all)
                atomic(self.private / 'settings.json', self.config)
        return self.public_settings()

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
