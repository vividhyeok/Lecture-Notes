"""Local persistence utilities and safe subtitle parsing. No network access."""
import base64
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

AUDIO = {'.mp3', '.mp4', '.m4a', '.wav', '.webm', '.mpeg', '.mpga', '.ogg', '.flac'}
TEXT = {'.txt', '.md', '.srt', '.vtt', '.json'}


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.writing-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return default


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def slug(value):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip(' .')[:80]
    if not text or text.upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}:
        text = '강의'
    return text


def inside(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('허용된 폴더 밖의 파일입니다.')
    return path


def stamp(value):
    value = max(0, int(float(value)))
    return f'{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}'


def seconds(value):
    fields = str(value).replace(',', '.').split(':')
    if len(fields) not in (2, 3):
        raise ValueError('잘못된 타임스탬프')
    total = 0.0
    for item in fields:
        total = total * 60 + float(item)
    if not math.isfinite(total) or total < 0:
        raise ValueError('잘못된 타임스탬프')
    return total


def normalize_segments(items):
    result = []
    for item in items:
        start, end = float(item.get('start', 0)), float(item.get('end', item.get('start', 0)))
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise ValueError('전사본 시간 범위가 올바르지 않습니다.')
        text = str(item.get('text', '')).strip()
        if text:
            result.append({'start': round(start, 3), 'end': round(end, 3), 'text': text})
    return sorted(result, key=lambda x: x['start'])


def parse_transcript(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.json':
        data = json.loads(text)
        if isinstance(data, list):
            return {'segments': normalize_segments(data), 'text': '\n'.join(str(x.get('text', '')) for x in data), 'timed': True}
        segments = normalize_segments(data.get('segments', []))
        return {'segments': segments, 'text': str(data.get('text') or '\n'.join(x['text'] for x in segments)), 'timed': bool(segments)}
    if path.suffix.lower() in {'.srt', '.vtt'}:
        items = []
        for block in re.split(r'\n\s*\n', text.replace('\r', '')):
            lines = block.splitlines()
            for index, line in enumerate(lines):
                if '-->' in line:
                    start, end = line.split('-->', 1)
                    items.append({'start': seconds(start.strip()), 'end': seconds(end.strip().split()[0]), 'text': re.sub(r'<[^>]*>', '', '\n'.join(lines[index + 1:]))})
                    break
        segments = normalize_segments(items)
        if not segments:
            raise ValueError('자막의 시간 구간을 찾지 못했습니다.')
        return {'segments': segments, 'text': '\n'.join(x['text'] for x in segments), 'timed': True}
    # Plain Markdown is retained verbatim. Times are never fabricated.
    timed_lines = []
    pattern = re.compile(r'^\s*(?:[-*]\s*)?\[?(\d{1,3}:\d{2}(?::\d{2})?)\]?\s+(.+)$')
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            timed_lines.append({'start': seconds(match[1]), 'end': seconds(match[1]), 'text': match[2]})
    for i in range(len(timed_lines) - 1):
        timed_lines[i]['end'] = timed_lines[i + 1]['start']
    return {'segments': normalize_segments(timed_lines), 'text': text, 'timed': bool(timed_lines)}


def transcript_md(transcript):
    if transcript.get('segments'):
        return '# 전사본\n\n' + '\n\n'.join(f"[{stamp(s['start'])}] {s['text']}" for s in transcript['segments']) + '\n'
    return '# 전사본\n\n' + transcript.get('text', '') + '\n'


def transcript_srt(transcript):
    def precise(n):
        millis = round(n * 1000)
        return stamp(millis // 1000) + f',{millis % 1000:03d}'
    return '\n\n'.join(f"{i+1}\n{precise(s['start'])} --> {precise(s['end'])}\n{s['text']}" for i, s in enumerate(transcript.get('segments', []))) + '\n'


def protect(secret, decrypt=False):
    """Windows DPAPI: encrypted key is tied to the signed-in Windows account."""
    if os.name != 'nt':
        raise ValueError('이 OS에서는 OPENAI_API_KEY 환경변수를 사용하세요.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(secret) if decrypt else secret.encode('utf-8')
    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source, target = Blob(len(raw), buffer), Blob()
    api = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not api(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
        raise OSError('Windows API 키 암호화/복호화에 실패했습니다.')
    try:
        data = ctypes.string_at(target.pbData, target.cbData)
        return data.decode('utf-8') if decrypt else base64.b64encode(data).decode('ascii')
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)

def split_text(text, limit=14000):
    """Lossless, ordered splits, preferring paragraph/sentence boundaries."""
    result = []
    while len(text) > limit:
        end = max(text.rfind('\n\n', limit // 2, limit), text.rfind('. ', limit // 2, limit), text.rfind('\n', limit // 2, limit))
        end = limit if end < 0 else end + 1
        result.append(text[:end])
        text = text[end:]
    if text:
        result.append(text)
    return result


def inferred_names(filename):
    stem = Path(filename).stem
    match = re.match(r'^\[([^\]]+)\]\s*(.+)$', stem)
    if match:
        return match[2].strip(), match[1].strip()
    if '__' in stem:
        course, title = stem.split('__', 1)
        return title.strip(), course.strip()
    return stem, ''
