"""Build the claude.ai artifact version (no PWA tags) from index.html.
Usage: python3 tools/build_artifact.py  -> writes dist/artifact.html"""
import re, pathlib
src = pathlib.Path(__file__).resolve().parents[1] / 'index.html'
html = re.sub(r'<!--PWA-->.*?<!--/PWA-->\n?', '', src.read_text(encoding='utf-8'), flags=re.S)
out = src.parent / 'dist' / 'artifact.html'
out.parent.mkdir(exist_ok=True)
out.write_text(html, encoding='utf-8')
print('wrote', out)
