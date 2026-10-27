#!/usr/bin/env python3
"""Build/check the public skill ZIP and matching install metadata, deterministically."""
import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = r'(<script[^>]*id="page-data"[^>]*>)([\s\S]*?)(</script>)'


def package_files():
    base = ROOT / 'skill/stillpoint'
    files = [base / 'SKILL.md', base / 'README.md']
    for folder, suffix in [('references', '.md'), ('agents', '.yaml'), ('evals', '.json'), ('scripts', '.py')]:
        files += sorted((base / folder).glob('*' + suffix))
    for path in files:
        raw = path.read_bytes()
        if b'/Users/b1axk/' in raw or path.is_symlink():
            raise ValueError('Private absolute path/symlink in distributable: ' + path.name)
        if re.search(rb'(?:sk-proj-|ghp_|github_pat_)[A-Za-z0-9_]{15,}', raw):
            raise ValueError('Possible credential in distributable: ' + path.name)
    return base, files


def build():
    base, files = package_files()
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(files):
            info = zipfile.ZipInfo('stillpoint/' + str(path.relative_to(base)), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, path.read_bytes())
    raw = out.getvalue()
    version = re.search(r'^# .*v(\d+\.\d+\.\d+)\s*$', (base / 'SKILL.md').read_text(), re.M).group(1)
    return raw, version, len(files), (base / 'SKILL.md').stat().st_size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    raw, version, count, main_size = build()
    sha = hashlib.sha256(raw).hexdigest()
    size = str(round(len(raw) / 1024, 1)) + ' KB'
    index = ROOT / 'index.html'
    html = index.read_text(encoding='utf-8')
    match = re.search(PATTERN, html)
    data = json.loads(match.group(2))
    expected = {'ver': 'v' + version, 'size': size, 'sha256': sha}
    zip_path = ROOT / 'skill/stillpoint.zip'
    if args.check:
        okay = zip_path.exists() and zip_path.read_bytes() == raw and all(data['install']['pkg'].get(k) == v for k, v in expected.items())
        if not okay:
            print('Skill package or install metadata drifted; run scripts/build_skill_package.py', file=sys.stderr)
            return 1
    else:
        data['install']['pkg'].update(expected)
        data['install']['spec'][0:3] = ['v' + version, '压缩包 ' + size, '主文件 ' + str(round(main_size / 1024, 1)) + ' KB']
        zip_path.write_bytes(raw)
        replacement = match.group(1) + '\n' + json.dumps(data, ensure_ascii=False, indent=2) + '\n' + match.group(3)
        index.write_text(html[:match.start()] + replacement + html[match.end():], encoding='utf-8')
    print(json.dumps({'version': version, 'files': count, 'bytes': len(raw), 'sha256': sha, 'checked': args.check}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
