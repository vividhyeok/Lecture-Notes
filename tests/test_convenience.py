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
        self.assertEqual(items[0]['import_source'], 'downloads')

    def test_app_owned_inbox_always_scans(self):
        lecture = self.app.library / 'inbox' / '[자료구조] 연결리스트.txt'
        lecture.write_text('연결 리스트 설명', encoding='utf-8')
        self.stable(lecture)
        self.app.scan()
        self.app.scan()
        items = self.app.list_lectures()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['course'], '자료구조')
        self.assertEqual(items[0]['import_source'], 'inbox')

    def test_archive_is_reversible_and_filters_the_library(self):
        first = self.root / 'first.txt'
        second = self.root / 'second.txt'
        first.write_text('첫 번째 강의 내용', encoding='utf-8')
        second.write_text('두 번째 강의 내용', encoding='utf-8')
        first_id = self.app.import_file(first, title='첫 강의', course='운영체제', process=False)
        second_id = self.app.import_file(second, title='둘째 강의', course='운영체제', process=False)

        self.app.update_settings({'archive_id': first_id})
        self.assertEqual([row['id'] for row in self.app.list_lectures()], [second_id])
        self.assertEqual(self.app.public_settings()['archived_count'], 1)

        self.app.update_settings({'archive_view': True})
        archived = self.app.list_lectures()
        self.assertEqual([row['id'] for row in archived], [first_id])
        self.assertTrue(archived[0]['archived'])

        self.app.update_settings({'restore_id': first_id, 'archive_view': False})
        self.assertEqual({row['id'] for row in self.app.list_lectures()}, {first_id, second_id})
        self.assertEqual(self.app.public_settings()['archived_count'], 0)

    def test_unclassified_can_be_archived_in_bulk(self):
        path = self.root / 'mystery.txt'
        path.write_text('분류되지 않은 강의', encoding='utf-8')
        ident = self.app.import_file(path, title='미분류 강의', course='', process=False)
        self.app.update_settings({'archive_unclassified': True})
        self.assertEqual(self.app.list_lectures(), [])
        self.app.update_settings({'archive_view': True})
        self.assertEqual(self.app.list_lectures()[0]['id'], ident)

    def test_quality_presets_choose_current_models(self):
        settings = self.app.public_settings()
        self.assertEqual(settings['quality_preset'], 'balanced')
        self.assertEqual(settings['text_model'], 'gpt-5.6-terra')
        self.app.update_settings({'quality_preset': 'fast'})
        self.assertEqual(self.app.public_settings()['text_model'], 'gpt-5.6-luna')
        self.app.update_settings({'quality_preset': 'precise'})
        self.assertEqual(self.app.public_settings()['text_model'], 'gpt-5.6-sol')


if __name__ == '__main__':
    unittest.main()
