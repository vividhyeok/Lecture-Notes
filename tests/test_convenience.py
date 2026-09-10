import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from convenience import ConvenienceLibrary


class ConvenienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = ConvenienceLibrary(self.root, client_factory=lambda: None)
        self.app.config['auto_process'] = False

    def tearDown(self):
        self.app.stop.set()
        self.tmp.cleanup()

    @staticmethod
    def stable(path):
        old = time.time() - 20
        os.utime(path, (old, old))

    def test_external_folder_is_event_only_by_default(self):
        downloads = self.root / 'Downloads'
        downloads.mkdir()
        self.app.update_settings({'watch_folder': str(downloads)})
        song = downloads / 'ordinary-song.txt'
        song.write_text('not a lecture', encoding='utf-8')
        self.stable(song)
        self.app.scan()
        self.app.scan()
        self.assertEqual(self.app.list_lectures(), [])
        self.assertFalse(self.app.public_settings()['watch_all_files'])

    def test_full_folder_scan_is_explicit_opt_in(self):
        downloads = self.root / 'Downloads'
        downloads.mkdir()
        self.app.update_settings({'watch_folder': str(downloads), 'watch_all_files': True})
        lecture = downloads / '[운영체제] 프로세스.txt'
        lecture.write_text('프로세스는 실행 중인 프로그램입니다.', encoding='utf-8')
        self.stable(lecture)
        self.app.scan()
        self.app.scan()
        items = self.app.list_lectures()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['course'], '운영체제')

    def test_app_owned_inbox_always_scans(self):
        lecture = self.app.library / 'inbox' / '[자료구조] 연결리스트.txt'
        lecture.write_text('연결 리스트 설명', encoding='utf-8')
        self.stable(lecture)
        self.app.scan()
        self.app.scan()
        items = self.app.list_lectures()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['course'], '자료구조')


if __name__ == '__main__':
    unittest.main()
