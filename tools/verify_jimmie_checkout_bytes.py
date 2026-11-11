"""Verify static Lua profile bytes survive real Git checkouts with either autocrlf setting."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    header = (ROOT / 'src/pc/generated/jimmie_companion_profile.inc.h').read_text()
    pins = {}
    for path, octets, dynamic in re.findall(r'\{"([^"\n]+)",\s*\{([^}]+)\},\s*(\d+)\}', header):
        if path.endswith('.lua'):
            assert dynamic == '0'
            pins['mods/jimmie/' + path] = bytes.fromhex(''.join(re.findall(r'0x([0-9a-fA-F]{2})', octets)))
    expected_rails = {'mods/jimmie/' + name for name in (
        'skate_rail_index.lua', 'skate_surface_rails.lua', 'skate_visible_rails.lua',
        'skate_rail_presentation.lua', 'skate_rail_binding.lua')}
    assert len(pins) == 32 and expected_rails <= pins.keys(), 'Review inventory change before accepting new profile'
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT / 'build/checkout-byte-tests' / stamp
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    for mode in ('true', 'false'):
        destination = out / ('autocrlf-' + mode)
        destination.mkdir()
        command = ['git', '-c', 'core.autocrlf=' + mode, 'checkout-index',
                   '--prefix=' + destination.as_posix() + '/', '--', *sorted(pins)]
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        for name, expected in sorted(pins.items()):
            source = (ROOT / name).read_bytes()
            checked = (destination / name).read_bytes()
            blob = subprocess.check_output(['git', 'show', ':' + name], cwd=ROOT)
            valid = source == checked == blob and hashlib.md5(checked).digest() == expected and b'\r\n' not in checked
            checks.append({'autocrlf': mode, 'path': name, 'passed': valid,
                           'sha256': hashlib.sha256(checked).hexdigest()})
    report = {'passed': all(c['passed'] for c in checks), 'checks': checks,
              'checkouts': 2, 'profile_files': len(pins), 'output': str(out.relative_to(ROOT)),
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'limits': 'Real Git index text checkouts only. Ignored private assets and a fresh full build are separate requirements.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'report': str(out / 'report.json')}))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
