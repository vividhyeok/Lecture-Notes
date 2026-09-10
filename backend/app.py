"""Lecture Notes server entry point with convenience-safe defaults."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import server
from convenience import ConvenienceLibrary

ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / 'extension' / 'manifest.json').read_text(encoding='utf-8-sig'))['version']


class ConvenienceHandler(server.Handler):
    def get(self):
        if urlsplit(self.path).path == '/health':
            if not self.host_ok() or not self.origin_ok():
                return self.respond(403, {'error': '접근 불가'})
            return self.respond(200, {'app': 'lecture-notes', 'version': VERSION})
        return super().get()


server.Library = ConvenienceLibrary
server.Handler = ConvenienceHandler

if __name__ == '__main__':
    server.main()
