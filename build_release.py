"""Build a clean, immediately extractable release; never package private state."""
from pathlib import Path
import hashlib
import zipfile

root = Path(__file__).resolve().parent
target = root / 'dist' / 'Lecture-Notes-v0.1.4.zip'
target.parent.mkdir(exist_ok=True)
files = [root / name for name in ['README.md', 'DEVELOPMENT.md', 'START.cmd', 'start.ps1', 'SETUP.cmd', 'setup.ps1']]
for directory, extensions in [('backend', {'.py'}), ('extension', {'.js', '.html', '.css', '.json'}), ('samples', {'.md', '.txt'}), ('docs', {'.md'})]:
    files.extend(p for p in (root / directory).rglob('*') if p.is_file() and p.suffix in extensions and '__pycache__' not in p.parts)
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('extension/config.local.js', "/* Generated for this PC by START.cmd. */\nglobalThis.LN_CONFIG = {base:'http://127.0.0.1:18765',token:''};\n")
    for path in sorted(files):
        name = path.relative_to(root).as_posix()
        if name == 'extension/config.local.js':
            continue
        else:
            archive.write(path, name)
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert not any(any(part in {'.local', 'library', 'Obsidian', 'node_modules'} for part in Path(name).parts) for name in archive.namelist())
    assert "token:''" in archive.read('extension/config.local.js').decode()
    assert 'backend/vault_sync.py' in archive.namelist()
    assert 'extension/print.html' in archive.namelist()
print(f'{target.name}: {target.stat().st_size:,} bytes; SHA256 {hashlib.sha256(target.read_bytes()).hexdigest()}')
