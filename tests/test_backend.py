import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from core import atomic, inside, slug, parse_transcript, split_text, protect
from library import Library
from provider import OpenAI, NOTES_PROMPT, ProviderError
from server import Server

class FakeAI:
    def __init__(self):
        self.stt = 0
        self.notes = 0
        self.fail_note = False
        self.inputs = []
    def transcribe(self, path, timed=False):
        self.stt += 1
        return {'text': '프로세스는 실행 중인 프로그램입니다.', 'segments': [{'start':0,'end':2,'text':'프로세스는 실행 중인 프로그램입니다.'}]} if timed else {'text':'프로세스는 실행 중인 프로그램입니다.'}
    def generate(self, prompt, text):
        self.notes += 1
        self.inputs.append(text)
        if self.fail_note:
            raise ProviderError('temporary failure')
        return '## 프로세스\n\n- 실행 중인 프로그램\n  - 독립된 주소 공간\n'

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.ai=FakeAI()
        self.app=Library(self.root, client_factory=lambda:self.ai)
    def tearDown(self):
        self.app.stop.set()
        self.tmp.cleanup()
    def source(self,name='[운영체제] 01.txt',text='프로세스는 실행 중인 프로그램입니다.'):
        path=self.root/name;path.write_text(text,encoding='utf-8');return path
    def test_lossless_split_and_names(self):
        source=('설명과 예시.\n\n'*4000)+'끝'
        pieces=split_text(source,1000)
        self.assertEqual(''.join(pieces),source)
        self.assertTrue(all(len(p)<=1000 for p in pieces))
        self.assertEqual(slug('../CON'), '_CON')
        with self.assertRaises(ValueError): inside(self.root,self.root.parent/'outside')

    def test_video_binding_portable_reassignment_and_credentials_removed(self):
        first = self.app.import_file(self.source('first-note.md', '# First'))
        second = self.app.import_file(self.source('second-note.md', '# Second'))
        data = {'course':'운영체제', 'title':'02 프로세스', 'pageKey':'https://jnuclass.jejunu.ac.kr/courses/1?id=2&token=secret', 'mediaKey':'https://common.jejunu.ac.kr/video.mp4?signature=secret'}
        self.app.bind_lecture(first, data)
        self.assertNotIn('secret', json.dumps(self.app.lecture(first)['bindings']))
        self.app.bind_lecture(second, data)
        self.assertEqual(self.app.lecture(first)['bindings'], [])
        self.assertEqual(len(self.app.lecture(second)['bindings']), 1)
        pc = Library(self.root / 'pc2')
        pc.config['vault_folder'] = self.app.config['vault_folder']
        pc.scan()
        self.assertEqual(pc.lecture(second)['bindings'], self.app.lecture(second)['bindings'])
        self.assertEqual(pc.jobs(), [])

    def test_youtube_video_id_survives_sync_and_reassignment(self):
        first = self.app.import_file(self.source('first-note.md', '# First'))
        second = self.app.import_file(self.source('second-note.md', '# Second'))
        data = {'course': 'youtube', 'title': 'First', 'pageKey': 'https://www.youtube.com/watch?v=abcdefghijk&token=secret&list=playlist'}
        self.app.bind_lecture(first, data)
        self.assertEqual(self.app.lecture(first)['bindings'][0]['pageKey'], 'https://www.youtube.com/watch?v=abcdefghijk')
        self.app.bind_lecture(second, dict(data, title='Changed title'))
        self.assertEqual(self.app.lecture(first)['bindings'], [])
        pc = Library(self.root / 'pc2')
        pc.config['vault_folder'] = self.app.config['vault_folder']
        pc.scan()
        self.assertEqual(pc.lecture(second)['bindings'], self.app.lecture(second)['bindings'])

    def test_reorganize_reuses_transcript_and_backs_up_note(self):
        ident = self.app.import_file(self.source(), process=False)
        self.app.save_notes(ident, '# 이전 노트\n- 직접 편집한 내용')
        job = self.app.enqueue('renote', ident)
        self.app.run_once()
        self.assertEqual(self.ai.stt, 0)
        self.assertEqual(self.ai.notes, 1)
        self.assertNotIn('# 전사본', self.ai.inputs[0])
        self.assertIn('프로세스', self.app.lecture(ident)['notes'])
        versions = list((Path(self.app.lecture(ident)['folder']) / 'versions').glob('*.md'))
        self.assertTrue(any('직접 편집한 내용' in p.read_text(encoding='utf-8') for p in versions))

    def test_reorganize_preserves_concurrent_obsidian_edit(self):
        ident = self.app.import_file(self.source(), process=False)
        self.app.save_notes(ident, '# 원래 노트')
        note = Path(self.app.lecture(ident)['note_path'])
        def changed(prompt, text):
            note.write_text('# Obsidian 수정', encoding='utf-8')
            return '## 새로운 구조\n- AI 결과'
        self.ai.generate = changed
        self.app.enqueue('renote', ident)
        self.app.run_once()
        self.assertEqual(note.read_text(encoding='utf-8'), '# Obsidian 수정')
        self.assertEqual(self.app.jobs()[0]['status'], 'error')
        self.assertEqual(self.ai.stt, 0)

    def test_portable_vault_restores_on_second_pc_without_ai(self):
        ident = self.app.import_file(self.source('강의노트.md', '# 강의\n\n- 원문 내용'))
        second = Library(self.root / 'pc2', client_factory=lambda: self.ai)
        second.config['vault_folder'] = self.app.config['vault_folder']
        second.scan()
        self.assertEqual(second.lecture(ident)['notes'], self.app.lecture(ident)['notes'])
        self.assertEqual(second.lecture(ident)['kind'], 'synced')
        self.assertEqual(second.jobs(), [])
        self.assertNotEqual(second.config['token'], self.app.config['token'])
        record = next((Path(second.config['vault_folder']) / '강의노트' / '_관리' / 'records').glob('*.md'))
        self.assertNotIn(str(self.root), record.read_text(encoding='utf-8'))
        note = Path(second.lecture(ident)['note_path'])
        note.write_text('# 다른 PC 수정\n- 내용 유지', encoding='utf-8')
        self.app.scan()
        self.assertIn('다른 PC 수정', self.app.lecture(ident)['notes'])
        self.assertTrue(list((record.parent.parent / '변경이력' / ident).glob('*.md')))
        self.assertEqual(self.ai.stt + self.ai.notes, 0)

    def test_partial_sync_and_deleted_note_never_resurrect(self):
        ident = self.app.import_file(self.source('강의노트.md', '# 보존\n- 내용'))
        note = Path(self.app.lecture(ident)['note_path'])
        note.unlink()
        self.app.scan()
        self.assertFalse(note.exists())
        second = Library(self.root / 'pc2')
        second.config['vault_folder'] = self.app.config['vault_folder']
        second.scan()
        self.assertTrue(second.lecture(ident)['sync_status'])
        self.assertFalse(note.exists())
        self.assertEqual(second.jobs(), [])
        with self.assertRaises(ValueError):
            self.app.save_notes(ident, 'accidental restore')
        note.write_text('', encoding='utf-8')
        self.app.scan()
        self.assertIn('보존', (Path(self.app.lecture(ident)['folder']) / '강의노트.md').read_text(encoding='utf-8'))

    def test_corrupt_sync_record_is_preserved(self):
        ident = self.app.import_file(self.source('강의노트.md', '# 보존'))
        record = Path(self.app.config['vault_folder']) / '강의노트' / '_관리' / 'records' / (ident + '.md')
        record.write_text('partial json', encoding='utf-8')
        self.app.scan()
        self.assertEqual(record.read_text(encoding='utf-8'), 'partial json')
        self.assertTrue(self.app.watch_error)
    def test_subtitles_preserve_time_and_plain_has_no_fake_time(self):
        p=self.source('a.srt','1\n00:00:01,000 --> 00:00:03,500\n안녕하세요\n')
        t=parse_transcript(p);self.assertEqual(t['segments'][0]['end'],3.5)
        self.assertFalse(parse_transcript(self.source())['timed'])
    def test_import_dedupe_and_prompt(self):
        p=self.source();a=self.app.import_file(p);b=self.app.import_file(p)
        self.assertEqual(a,b);self.assertEqual(len(self.app.jobs()),1)
        self.assertEqual(self.app.lecture(a)['course'],'운영체제')
        self.assertTrue(self.app.run_once());self.assertEqual(self.ai.stt,0)
        self.assertEqual(self.ai.notes,1)
        self.assertIn('내용은 삭제하지 말고 전부 살려줘',NOTES_PROMPT)
        self.assertIn('중첩 unordered list',NOTES_PROMPT)
    def test_obsidian_edit_is_authoritative_and_versioned(self):
        ident=self.app.import_file(self.source());self.app.run_once()
        lecture=self.app.lecture(ident);note=Path(lecture['note_path'])
        self.assertEqual(note.parent.name,'운영체제');self.assertEqual(note.stem,'01')
        note.write_text('# 사용자 편집\n- 중요한 필기',encoding='utf-8')
        self.app.export(ident)
        self.assertIn('중요한 필기',self.app.lecture(ident)['notes'])
        self.app.save_notes(ident,'# 새 내용')
        self.assertEqual(note.read_text(encoding='utf-8'),'# 새 내용')
        backups=list((Path(lecture['folder'])/'versions').glob('*.md'))
        self.assertIn('중요한 필기',backups[0].read_text(encoding='utf-8'))
    def test_export_collision_preserves_existing_note(self):
        dest=Path(self.app.config['vault_folder'])/'강의노트'/'운영체제';dest.mkdir(parents=True)
        (dest/'01.md').write_text('기존 노트',encoding='utf-8')
        ident=self.app.import_file(self.source());self.app.run_once()
        self.assertEqual((dest/'01.md').read_text(encoding='utf-8'),'기존 노트')
        self.assertNotEqual(Path(self.app.lecture(ident)['note_path']).name,'01.md')
    def test_exam_reuses_transcript_and_dedupes(self):
        ident=self.app.import_file(self.source());self.app.run_once()
        first=self.app.exam(ids=[ident]);second=self.app.exam(ids=[ident])
        self.assertEqual(first,second);self.app.run_once();self.assertEqual(self.ai.stt,0)
        self.assertTrue(list((self.app.library/'exams').glob('*/시험대비.md')))
    def test_note_failure_reuses_completed_transcription_on_retry(self):
        path=self.root/'lecture.mp3';path.write_bytes(b'audio fixture')
        ident=self.app.import_file(path)
        folder=Path(self.app.lecture(ident)['folder'])/'.cache'/'audio';folder.mkdir(parents=True)
        (folder/'part-0000.mp3').write_bytes(b'chunk')
        atomic(folder/'ready.json',{'parts':['part-0000.mp3']})
        self.ai.fail_note=True;self.app.run_once()
        self.assertEqual(self.app.jobs()[0]['status'],'error');self.assertEqual(self.ai.stt,1)
        self.ai.fail_note=False;self.app.retry(self.app.jobs()[0]['id']);self.app.run_once()
        self.assertEqual(self.ai.stt,1);self.assertEqual(self.app.jobs()[0]['status'],'done')
    def test_watch_subfolder_course_and_stability(self):
        folder=self.app.library/'inbox'/'자료구조';folder.mkdir()
        path=folder/'리스트.txt';path.write_text('연결 리스트 설명',encoding='utf-8')
        os.utime(path,(time.time()-20,time.time()-20))
        self.app.scan();self.assertEqual(len(self.app.list_lectures()),0)
        self.app.scan();self.assertEqual(self.app.list_lectures()[0]['course'],'자료구조')
    def test_markdown_import_does_not_call_ai(self):
        ident=self.app.import_file(self.source('강의노트.md','# 내 노트\n- 기존 필기'))
        self.assertEqual(len(self.app.jobs()),0)
        self.assertEqual(self.app.lecture(ident)['notes'],'# 내 노트\n- 기존 필기')
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg not installed')
    def test_real_ffmpeg_conversion_with_mock_stt(self):
        path=self.root/'audio.wav'
        subprocess.run([shutil.which('ffmpeg'),'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=1','-y',str(path)],check=True,capture_output=True)
        ident=self.app.import_file(path);self.app.run_once()
        self.assertEqual(self.app.jobs()[0]['status'],'done');self.assertEqual(self.ai.stt,1)
        self.assertTrue(self.app.lecture(ident)['transcript']['text'])
    @unittest.skipUnless(os.name=='nt','Windows DPAPI only')
    def test_settings_applies_vault_to_existing_notes_immediately(self):
        ident = self.app.import_file(self.source('lecture-note.md', '# Original'))
        old = Path(self.app.lecture(ident)['note_path'])
        old.write_text('# Edited in Obsidian', encoding='utf-8')
        target = self.root / 'OneDrive' / 'ドキュメント' / 'jnuclass'
        target.mkdir(parents=True)
        self.app.update_settings({'vault_folder': str(target)})
        note = Path(self.app.lecture(ident)['note_path'])
        self.assertTrue(note.is_relative_to(target))
        self.assertEqual(note.read_text(encoding='utf-8'), '# Edited in Obsidian')
        self.assertTrue(old.exists())
        self.assertEqual(json.loads((self.app.private / 'settings.json').read_text(encoding='utf-8'))['vault_folder'], str(target.resolve()))

    def test_dpapi_and_public_settings_hide_key(self):
        encrypted=protect('test-private-key');self.assertNotIn('test-private-key',encrypted)
        self.assertEqual(protect(encrypted,decrypt=True),'test-private-key')
        self.app.update_settings({'api_key':'test-private-key'})
        self.assertNotIn('test-private-key',json.dumps(self.app.public_settings()))

class APITests(unittest.TestCase):
    def test_provider_shapes_and_no_store(self):
        seen=[]
        def open_req(req,timeout):
            seen.append(req)
            if req.full_url.endswith('/responses'):
                return io.BytesIO(json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'## 노트'}]}]}).encode())
            return io.BytesIO(b'{"text":"hello"}')
        ai=OpenAI('fake',opener=open_req)
        self.assertEqual(ai.generate('rules','text'),'## 노트')
        self.assertFalse(json.loads(seen[0].data)['store'])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.mp3';p.write_bytes(b'audio');ai.transcribe(p)
        self.assertIn(b'gpt-4o-mini-transcribe',seen[1].data)
        self.assertNotIn(b'timestamp_granularities',seen[1].data)
    def test_http_auth_origin_and_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Library(tmp)
            app.config['auto_process']=False
            (Path(tmp)/'extension').mkdir()
            (Path(tmp)/'extension'/'config.local.js').write_text('secret config',encoding='utf-8')
            server=Server(('127.0.0.1',0),app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                with urllib.request.urlopen(base+'/health') as response:self.assertEqual(json.load(response)['app'],'lecture-notes')
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/api/state')
                self.assertEqual(error.exception.code,401)
                req=urllib.request.Request(base+'/config.local.js',headers={'Sec-Fetch-Site':'cross-site'})
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
                self.assertEqual(error.exception.code,403)
                headers={'Authorization':'Bearer '+app.config['token']}
                req=urllib.request.Request(base+'/api/upload?name=lecture.txt',data='원문'.encode(),headers=headers,method='POST')
                with urllib.request.urlopen(req) as response:ident=json.load(response)['id']
                self.assertEqual(app.lecture(ident)['transcript']['text'],'원문')
                req=urllib.request.Request(base+'/api/state',headers=headers|{'Origin':'https://evil.example'})
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
            finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
