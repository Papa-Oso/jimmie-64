"""Package/launcher regression tests. Only synthetic .NET probe programs run.

No ROM, personal installation, visible game, controller, or audio is accessed.
The launcher execution tests use a unique test mutex and process name, never the
real game lock, so native fork tests may continue independently.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile
import time
import unittest
import uuid
import importlib.util

_spec = importlib.util.spec_from_file_location("package_jimmie_fork", Path(__file__).with_name("package_jimmie_fork.py"))
package = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(package)

ROOT = Path(__file__).resolve().parents[1]
COMPILER = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
LOG_LIMIT = 512 * 1024
PROBE = r'''
using System;
using System.IO;
using System.Threading;
class Probe {
    static void Emit(Stream output, byte value, int length) {
        byte[] block = new byte[8192];
        for (int i = 0; i < block.Length; i++) block[i] = value;
        while (length > 0) {
            int count = Math.Min(length, block.Length);
            output.Write(block, 0, count); output.Flush(); length -= count;
        }
    }
    static int Main(string[] args) {
        string log = Environment.GetEnvironmentVariable("PACKAGE_PROBE_LOG");
        string[] keys = new string[] {"JIMMIE_NATIVE_HEAD", "JIMMIE_HEAD_TEST_START", "JIMMIE_OTHER", "SDL_AUDIODRIVER", "SDL_JOYSTICK_RAWINPUT", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"};
        using (StreamWriter writer = new StreamWriter(log)) {
            writer.WriteLine("cwd=" + Environment.CurrentDirectory);
            foreach (string arg in args) writer.WriteLine("arg=" + arg);
            foreach (string key in keys) writer.WriteLine(key + "=" + Environment.GetEnvironmentVariable(key));
        }
        int length;
        if (Int32.TryParse(Environment.GetEnvironmentVariable("PACKAGE_PROBE_BYTES"), out length)) {
            // Concurrent raw streams deliberately have no newline or text decoder.
            Thread error = new Thread(delegate() { Emit(Console.OpenStandardError(), 69, length); });
            error.Start(); Emit(Console.OpenStandardOutput(), 79, length); error.Join();
        } else {
            Console.Out.Write("rail_event fixture\n"); Console.Out.Flush();
            Console.Error.Write("rail_error fixture\n"); Console.Error.Flush();
        }
        string release = Environment.GetEnvironmentVariable("PACKAGE_PROBE_RELEASE");
        if (!String.IsNullOrEmpty(release)) {
            for (int i = 0; i < 200 && !File.Exists(release); i++) Thread.Sleep(50);
        }
        return Environment.GetEnvironmentVariable("PACKAGE_PROBE_FAIL") == "1" ? 7 : 0;
    }
}
'''


class PackagePolicy(unittest.TestCase):
    def test_profile_parser_rejects_dynamic(self):
        with self.assertRaisesRegex(ValueError, 'dynamic'):
            package.profile_entries('{"main.lua", {' + ','.join(['0x00'] * 16) + '}, 1}')

    def test_profile_parser_rejects_duplicate(self):
        entry = '{"main.lua", {' + ','.join(['0x00'] * 16) + '}, 0}'
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            package.profile_entries(entry + entry)

    def test_profile_parser_rejects_short_digest(self):
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            package.profile_entries('{"main.lua", {0x00}, 0}')

    def test_profile_parser_rejects_empty(self):
        with self.assertRaisesRegex(ValueError, 'Empty'):
            package.profile_entries('')

    def test_production_launch_contract(self):
        self.assertIn(r'Local\Jimmie64-Unified-Launch', package.LAUNCHER)
        for flag in ('--headless', '--skip-intro', '--hide-loading-screen'):
            self.assertNotIn(flag, package.GAME_ARGS)
        self.assertIn('--server 7777 --playercount 1', package.GAME_ARGS)
        self.assertIn('--console', package.GAME_ARGS)
        self.assertIn('command.CreateNoWindow = true', package.LAUNCHER)
        self.assertIn('command.UseShellExecute = false', package.LAUNCHER)
        self.assertNotIn('baserom', package.LAUNCHER)
        self.assertNotIn('python', package.LAUNCHER.lower())
        self.assertIn('LogLimit = 512 * 1024', package.LAUNCHER)
        self.assertNotIn('BeginOutputReadLine', package.LAUNCHER)
        self.assertNotIn('ReadToEnd', package.LAUNCHER)
        self.assertNotIn('ReadLine', package.LAUNCHER)

    def test_safe_file_rejects_escape_and_empty(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            root = Path(temp)
            (root / 'empty').touch()
            with self.assertRaisesRegex(ValueError, 'Missing/empty'):
                package.safe_file(root / 'empty', root)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                package.safe_file(root.parent / 'other', root)


class InputPlan(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.title = self.root / 'title'
        self.loaded = {'main.lua': b'return {}', 'jimmie_audition.lua': b'return {audition=true}', 'trick_outcomes.lua': b'return {outcome=true}',
                       'companion_spawn.lua': b'return {spawn=true}',
                       'skate_rail_index.lua': b'return {hints={}}',
                       'skate_surface_rails.lua': b'return {surface=true}',
                       'skate_visible_rails.lua': b'return {lines={}}',
                       'skate_rail_presentation.lua': b'return {presentation=true}',
                       'skate_rail_binding.lua': b'return {binding=true}'}
        self.loaded.update({'sound/clip_%02d.ogg' % i: ('private fixture %d' % i).encode() for i in range(37)})
        for name in package.ACTORS:
            self.loaded['actors/' + name] = b'original actor fixture ' + name.encode()
        for name, data in self.loaded.items():
            path = self.cache / Path(name).name if name.startswith('actors/') else self.root / 'mods/jimmie' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.header = self.root / 'src/pc/generated/jimmie_companion_profile.inc.h'
        self.header.parent.mkdir(parents=True)
        text = ''
        for name, data in self.loaded.items():
            md5 = hashlib.md5(data).hexdigest()
            text += '{' + json.dumps(name) + ', {' + ','.join('0x' + md5[i:i+2] for i in range(0, 32, 2)) + '}, 0},\n'
        self.header.write_text(text)
        self.engine = self.root / 'build/us_pc/sm64coopdx.exe'
        self.engine.parent.mkdir(parents=True)
        self.engine.write_bytes(b'not an executable; plan fixture only')
        frozen = self.root / 'docs/jimmie/integration/readiness.json'
        frozen.parent.mkdir(parents=True)
        frozen.write_text(json.dumps({'runtime_hashes': {name: '' for name in self.loaded if not name.startswith('actors/')
                                                and name not in ('trick_outcomes.lua', 'companion_spawn.lua', 'skate_rail_index.lua',
                                                                 'skate_surface_rails.lua', 'skate_visible_rails.lua',
                                                                 'skate_rail_presentation.lua', 'skate_rail_binding.lua')}}))
        (frozen.parent.parent / 'RIGHTS_STATUS.md').write_text('Private only fixture.')
        (frozen.parent.parent / 'FIRST_RUN.md').write_text('Own ROM; private fixture only.')
        for name in package.TITLE_NAMES:
            self.title.mkdir(exist_ok=True)
            (self.title / name).write_bytes(b'private title fixture')
        for name in package.LANGUAGES:
            lang = self.engine.parent / 'lang'
            lang.mkdir(exist_ok=True)
            (lang / (name + '.ini')).write_bytes(b'language fixture')

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        return package.plan_inputs(self.root, self.cache, self.title,
                                   package.sha(self.engine), package.sha(self.header))

    def test_allowlist_omits_rom_music_unknown_lua(self):
        (self.root / 'mods/jimmie/unreviewed.lua').write_text('error()')
        (self.title / 'rainbow_road.ogg').write_bytes(b'never copy')
        (self.engine.parent / 'baserom.us.z64').write_bytes(b'never read')
        files = self.plan()
        self.assertEqual(sum('/sound/' in name for name in files), 37)
        self.assertEqual(sum('/actors/' in name for name in files), 5)
        self.assertFalse(any('unreviewed' in name or 'rainbow' in name or '.z64' in name for name in files))

    def test_changed_module_rejected(self):
        (self.root / 'mods/jimmie/main.lua').write_text('return {changed=true}')
        with self.assertRaisesRegex(ValueError, 'content differs'):
            self.plan()

    def test_changed_spawn_module_rejected(self):
        (self.root / 'mods/jimmie/companion_spawn.lua').write_bytes(b'return {unreviewed=true}')
        with self.assertRaisesRegex(ValueError, 'Native profile content differs'):
            self.plan()

    def test_missing_spawn_module_rejected(self):
        path = self.root / 'mods/jimmie/companion_spawn.lua'
        path.rename(path.with_suffix('.held'))
        with self.assertRaisesRegex(ValueError, 'Missing/empty input'):
            self.plan()

    def test_changed_actor_rejected(self):
        (self.cache / package.ACTORS[0]).write_bytes(b'wrong cache')
        with self.assertRaisesRegex(ValueError, 'content differs'):
            self.plan()

    def test_extra_native_profile_rejected(self):
        with self.header.open('a') as stream:
            stream.write('{"rogue.lua", {' + ','.join(['0x00'] * 16) + '}, 0}')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.plan()

    def test_engine_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Engine identity'):
            package.plan_inputs(self.root, self.cache, self.title, '0' * 64, package.sha(self.header))

    def test_changed_rail_index_rejected(self):
        (self.root / 'mods/jimmie/skate_rail_index.lua').write_bytes(b'return {unreviewed=true}')
        with self.assertRaisesRegex(ValueError, 'Native profile content differs'):
            self.plan()

    def test_missing_rail_index_rejected(self):
        path = self.root / 'mods/jimmie/skate_rail_index.lua'
        path.rename(path.with_suffix('.held'))
        with self.assertRaisesRegex(ValueError, 'Missing/empty input'):
            self.plan()

    def test_changed_raised_rail_modules_rejected(self):
        for name in ('skate_surface_rails.lua', 'skate_visible_rails.lua',
                     'skate_rail_presentation.lua', 'skate_rail_binding.lua'):
            with self.subTest(module=name):
                path = self.root / 'mods/jimmie' / name
                original = path.read_bytes()
                try:
                    path.write_bytes(b'return {unreviewed=true}')
                    with self.assertRaisesRegex(ValueError, 'Native profile content differs'):
                        self.plan()
                finally:
                    path.write_bytes(original)

    def test_missing_raised_rail_modules_rejected(self):
        for name in ('skate_surface_rails.lua', 'skate_visible_rails.lua',
                     'skate_rail_presentation.lua', 'skate_rail_binding.lua'):
            with self.subTest(module=name):
                path = self.root / 'mods/jimmie' / name
                held = path.with_suffix('.held')
                path.rename(held)
                try:
                    with self.assertRaisesRegex(ValueError, 'Missing/empty input'):
                        self.plan()
                finally:
                    held.rename(path)

    def test_manifest_traversal_rejected(self):
        path = self.root / 'docs/jimmie/integration/readiness.json'
        data = json.loads(path.read_text())
        data['runtime_hashes']['sound/..\\escape.ogg'] = ''
        # Replace a name to retain the exact expected voice count.
        del data['runtime_hashes']['sound/clip_00.ogg']
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            self.plan()


@unittest.skipUnless(os.name == 'nt' and COMPILER.is_file(), 'Existing Windows .NET compiler required')
class LauncherExecution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='launcher tests with spaces ', dir=TEST_ROOT)
        cls.base = Path(cls.temp.name)
        source = cls.base / 'Probe.cs'
        source.write_text(PROBE)
        cls.probe_name = 'JimmiePackageProbe' + uuid.uuid4().hex
        cls.probe = cls.base / (cls.probe_name + '.exe')
        result = subprocess.run([str(COMPILER), '/nologo', '/target:winexe', '/out:' + str(cls.probe), str(source)],
                       capture_output=True, text=True, creationflags=NO_WINDOW, timeout=30,
                       env=dict(os.environ, TEMP=str(cls.base), TMP=str(cls.base)))
        if result.returncode: raise RuntimeError(result.stdout + result.stderr)
        cls.sources = {'game/' + cls.probe.name: cls.probe}
        for name in ('game/mods/jimmie/main.lua', 'game/lang/English.ini', 'game/jimmie-title/title_good_morning_01.ogg'):
            path = cls.base / 'inputs' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic fixture, not game content')
            cls.sources[name] = path
        cls.destination = cls.base / 'package with spaces'
        cls.report = package.assemble(cls.destination, cls.sources, COMPILER, {'test_fixture': True})
        if (cls.destination / 'user').exists():
            raise AssertionError('Assembly --check created mutable user directories')
        manifest = cls.destination / 'package-manifest.json'
        cls.pins = {name: package.sha(path) for name, path in cls.sources.items()}
        cls.pins[manifest.name] = package.sha(manifest)
        template = package.LAUNCHER.replace(r'Local\Jimmie64-Unified-Launch', r'Local\JimmiePackageTest-' + uuid.uuid4().hex)
        template = template.replace('"sm64coopdx.exe"', '"' + cls.probe.name + '"').replace('GetProcessesByName("sm64coopdx")', 'GetProcessesByName("' + cls.probe_name + '")')
        cls.template = template
        cls.launcher = package.compile_launcher(cls.destination, cls.pins, COMPILER, template)
        cls.logs = cls.destination / 'user/logs'

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_launcher(self, *args, env=None):
        return subprocess.run([str(self.launcher), *args], capture_output=True, text=True,
                              env=env, creationflags=NO_WINDOW, timeout=20)

    def environment(self):
        return dict(os.environ, PACKAGE_PROBE_LOG=str(self.base / ('probe-' + uuid.uuid4().hex + '.txt')),
                    JIMMIE_HEAD_TEST_START='1', JIMMIE_OTHER='bad', SDL_AUDIODRIVER='dummy')

    def empty_logs(self):
        # Only two owned synthetic fixture files; never traverse or rotate user logs.
        self.logs.mkdir(parents=True, exist_ok=True)
        for name in ('stdout.log', 'stderr.log'):
            path = self.logs / name
            if path.exists(): path.unlink()

    def emit(self, length=None, fail=False):
        env = self.environment()
        if length is not None: env['PACKAGE_PROBE_BYTES'] = str(length)
        if fail: env['PACKAGE_PROBE_FAIL'] = '1'
        return self.run_launcher('--no-dialog', env=env)

    def test_no_rom_check_is_readonly(self):
        before = {str(p.relative_to(self.destination)): package.sha(p) for p in self.destination.rglob('*') if p.is_file()}
        directories = {str(p.relative_to(self.destination)) for p in self.destination.rglob('*') if p.is_dir()}
        result = self.run_launcher('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ROM intentionally not required', result.stdout)
        after = {str(p.relative_to(self.destination)): package.sha(p) for p in self.destination.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(directories, {str(p.relative_to(self.destination)) for p in self.destination.rglob('*') if p.is_dir()})

    def test_logs_capture_both_streams_and_append_across_runs(self):
        self.empty_logs()
        for count in (1, 2):
            result = self.emit()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.logs / 'stdout.log').read_bytes(), b'rail_event fixture\n' * count)
            self.assertEqual((self.logs / 'stderr.log').read_bytes(), b'rail_error fixture\n' * count)

    def test_logs_are_flushed_while_synthetic_child_is_alive(self):
        self.empty_logs()
        env = self.environment()
        release = self.base / ('live-log-release-' + uuid.uuid4().hex)
        env['PACKAGE_PROBE_RELEASE'] = str(release)
        child = subprocess.Popen([str(self.launcher), '--no-dialog'], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        try:
            expected = {'stdout.log': b'rail_event fixture\n', 'stderr.log': b'rail_error fixture\n'}
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if all((self.logs / name).exists() and (self.logs / name).read_bytes() == data
                       for name, data in expected.items()): break
                time.sleep(.02)
            for name, data in expected.items(): self.assertEqual((self.logs / name).read_bytes(), data)
            self.assertIsNone(child.poll(), 'Logs must be available before child exits')
        finally:
            release.write_text('release owned synthetic probe')
            child.communicate(timeout=15)
        self.assertEqual(child.returncode, 0)

    def test_logs_long_no_newline_and_cap_preserve_prefix(self):
        self.empty_logs()
        prefix = b'previous launch\x00\xff\n'
        for name in ('stdout.log', 'stderr.log'): (self.logs / name).write_bytes(prefix)
        for _ in range(2):
            result = self.emit(8 * LOG_LIMIT)
            self.assertEqual(result.returncode, 0, result.stderr)
            for name, value in (('stdout.log', b'O'), ('stderr.log', b'E')):
                self.assertEqual((self.logs / name).read_bytes(), prefix + value * (LOG_LIMIT - len(prefix)))

    def test_logs_preexisting_oversize_files_are_untouched(self):
        self.empty_logs()
        content = b'older oversized evidence\n' + b'X' * LOG_LIMIT
        for name in ('stdout.log', 'stderr.log'): (self.logs / name).write_bytes(content)
        self.assertEqual(self.emit(2 * LOG_LIMIT).returncode, 0)
        for name in ('stdout.log', 'stderr.log'): self.assertEqual((self.logs / name).read_bytes(), content)

    def test_logs_nonzero_exit_retains_both_streams(self):
        self.empty_logs()
        result = self.emit(123457, fail=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('code 7', result.stderr)
        self.assertEqual((self.logs / 'stdout.log').read_bytes(), b'O' * 123457)
        self.assertEqual((self.logs / 'stderr.log').read_bytes(), b'E' * 123457)

    def test_logs_unwritable_files_do_not_block_pipe_draining(self):
        self.empty_logs()
        files = [self.logs / name for name in ('stdout.log', 'stderr.log')]
        for path in files:
            path.write_bytes(b'preserved read-only file')
            os.chmod(path, 0o444)
        try:
            self.assertEqual(self.emit(8 * LOG_LIMIT).returncode, 0)
            for path in files: self.assertEqual(path.read_bytes(), b'preserved read-only file')
        finally:
            for path in files: os.chmod(path, 0o666)

    def test_logs_blocked_directory_is_nonfatal(self):
        self.empty_logs()
        for path in self.logs.iterdir(): path.unlink()
        self.logs.rmdir()
        self.logs.write_bytes(b'not a directory')
        try:
            self.assertEqual(self.emit(8 * LOG_LIMIT).returncode, 0)
            self.assertEqual(self.logs.read_bytes(), b'not a directory')
        finally:
            self.logs.unlink()

    def test_logs_linked_directory_never_writes_target(self):
        self.empty_logs()
        for path in self.logs.iterdir(): path.unlink()
        self.logs.rmdir()
        outside = self.base / ('untouched-' + uuid.uuid4().hex)
        outside.mkdir()
        marker = outside / 'marker'
        marker.write_bytes(b'untouched linked destination')
        command = "New-Item -ItemType Junction -Path '{}' -Target '{}' | Out-Null".format(
            str(self.logs).replace("'", "''"), str(outside).replace("'", "''"))
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, text=True, creationflags=NO_WINDOW, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            self.assertEqual(self.emit(8 * LOG_LIMIT).returncode, 0)
            self.assertEqual(list(outside.iterdir()), [marker])
            self.assertEqual(marker.read_bytes(), b'untouched linked destination')
        finally:
            self.logs.rmdir()  # Remove this test junction, not its target.

    def test_logs_hardlinked_files_never_write_target(self):
        self.empty_logs()
        outside = self.base / ('hardlink-target-' + uuid.uuid4().hex)
        outside.write_bytes(b'untouched hardlinked evidence')
        paths = [self.logs / name for name in ('stdout.log', 'stderr.log')]
        for path in paths: os.link(outside, path)
        try:
            self.assertEqual(self.emit(8 * LOG_LIMIT).returncode, 0)
            self.assertEqual(outside.read_bytes(), b'untouched hardlinked evidence')
        finally:
            for path in paths: path.unlink()

    def test_logs_write_failure_still_drains_and_exits(self):
        self.empty_logs()
        broken = self.template.replace('output.Write(block, 0, count);',
            'if (position >= LogBlock) throw new IOException("synthetic disk failure"); output.Write(block, 0, count);')
        try:
            package.compile_launcher(self.destination, self.pins, COMPILER, broken)
            self.assertEqual(self.emit(8 * LOG_LIMIT).returncode, 0)
            for name, value in (('stdout.log', b'O'), ('stderr.log', b'E')):
                self.assertEqual((self.logs / name).read_bytes(), value * 8192)
        finally:
            package.compile_launcher(self.destination, self.pins, COMPILER, self.template)

    def test_logs_stalled_write_does_not_deadlock_exit(self):
        self.empty_logs()
        slow = self.template.replace('output.Write(block, 0, count);',
            'Thread.Sleep(30000); output.Write(block, 0, count);')
        try:
            package.compile_launcher(self.destination, self.pins, COMPILER, slow)
            started = time.monotonic()
            result = self.emit(8 * LOG_LIMIT)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(time.monotonic() - started, 10, 'Blocked log I/O delayed child exit')
        finally:
            package.compile_launcher(self.destination, self.pins, COMPILER, self.template)

    def test_logs_stalled_setup_does_not_block_child(self):
        self.empty_logs()
        slow = self.template.replace('string folder = LocalPath("user/logs");',
            'Thread.Sleep(30000); string folder = LocalPath("user/logs");')
        try:
            package.compile_launcher(self.destination, self.pins, COMPILER, slow)
            started = time.monotonic()
            result = self.emit(8 * LOG_LIMIT)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(time.monotonic() - started, 10, 'Blocked log setup delayed child exit')
            self.assertEqual(list(self.logs.iterdir()), [])
        finally:
            package.compile_launcher(self.destination, self.pins, COMPILER, self.template)

    def test_changed_and_missing_file_fail_closed(self):
        target = self.destination / 'game/mods/jimmie/main.lua'
        original = target.read_bytes()
        try:
            target.write_bytes(b'changed')
            self.assertNotEqual(self.run_launcher('--check').returncode, 0)
            target.unlink()
            self.assertNotEqual(self.run_launcher('--check').returncode, 0)
        finally:
            target.write_bytes(original)

    def test_added_script_and_dll_fail_closed(self):
        for name in ('game/mods/jimmie/extra.lua', 'game/unexpected.dll'):
            path = self.destination / name
            try:
                path.write_bytes(b'not allowed')
                self.assertNotEqual(self.run_launcher('--check').returncode, 0)
            finally:
                path.unlink()

    def test_manifest_mutation_fails(self):
        path = self.destination / 'package-manifest.json'
        data = path.read_bytes()
        try:
            path.write_bytes(data + b' ')
            self.assertNotEqual(self.run_launcher('--check').returncode, 0)
        finally:
            path.write_bytes(data)

    def test_unknown_argument_fails(self):
        self.assertEqual(self.run_launcher('--headless').returncode, 2)

    def test_launch_arguments_environment_and_save_preservation(self):
        env = self.environment()
        result = self.run_launcher('--no-dialog', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = Path(env['PACKAGE_PROBE_LOG']).read_text().splitlines()
        self.assertIn('arg=--savepath', lines)
        self.assertEqual([line[4:] for line in lines if line.startswith('arg=')],
                         package.GAME_ARGS.split() + [str(self.destination / 'user/save')])
        self.assertIn('arg=' + str(self.destination / 'user/save'), lines)
        self.assertIn('cwd=' + str(self.destination / 'game'), lines)
        self.assertIn('JIMMIE_NATIVE_HEAD=1', lines)
        self.assertIn('JIMMIE_HEAD_TEST_START=', lines)
        self.assertIn('JIMMIE_OTHER=', lines)
        self.assertIn('SDL_AUDIODRIVER=', lines)
        self.assertIn('SDL_JOYSTICK_RAWINPUT=0', lines)
        for key, folder in (('APPDATA', 'appdata'), ('LOCALAPPDATA', 'localappdata'), ('TEMP', 'temp'), ('TMP', 'temp')):
            self.assertIn(key + '=' + str(self.destination / 'user' / folder), lines)
        config = self.destination / 'user/save/sm64config.txt'
        self.assertIn('bubble_death false', config.read_text())
        config.write_text('user-selected settings\n')
        save = self.destination / 'user/save/sm64_save_file.bin'
        save.write_bytes(b'user progress fixture')
        self.assertEqual(self.run_launcher('--no-dialog', env=env).returncode, 0)
        self.assertEqual(config.read_text(), 'user-selected settings\n')
        self.assertEqual(save.read_bytes(), b'user progress fixture')

    def test_concurrent_launch_refused_and_lock_released(self):
        env = self.environment()
        release = self.base / ('release-' + uuid.uuid4().hex)
        env['PACKAGE_PROBE_RELEASE'] = str(release)
        child = subprocess.Popen([str(self.launcher), '--no-dialog'], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        try:
            deadline = time.monotonic() + 10
            while not Path(env['PACKAGE_PROBE_LOG']).exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(Path(env['PACKAGE_PROBE_LOG']).exists(), 'Synthetic probe did not start')
            second = self.run_launcher('--no-dialog', env=self.environment())
            self.assertEqual(second.returncode, 1)
            self.assertIn('already starting or running', second.stderr)
        finally:
            release.write_text('release owned synthetic probe')
            child.communicate(timeout=15)
        self.assertEqual(child.returncode, 0)
        self.assertEqual(self.run_launcher('--no-dialog', env=self.environment()).returncode, 0)

    def test_existing_process_refused_without_stopping_it(self):
        env = self.environment()
        release = self.base / ('release-' + uuid.uuid4().hex)
        env['PACKAGE_PROBE_RELEASE'] = str(release)
        child = subprocess.Popen([str(self.probe)], env=env, creationflags=NO_WINDOW)
        try:
            result = self.run_launcher('--no-dialog', env=self.environment())
            self.assertEqual(result.returncode, 1)
            self.assertIn('A game is already running', result.stderr)
            self.assertIsNone(child.poll())
        finally:
            release.write_text('release owned synthetic probe')
            child.wait(timeout=15)

    def test_engine_error_reported_without_auto_retry(self):
        env = self.environment()
        env['PACKAGE_PROBE_FAIL'] = '1'
        result = self.run_launcher('--no-dialog', env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn('code 7', result.stderr)

    def test_changed_engine_between_plan_and_copy_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Engine changed'):
            package.assemble(self.base / ('stale-engine-' + uuid.uuid4().hex), self.sources, COMPILER, {'engine_sha256': '0' * 64})

    def test_changed_profile_between_plan_and_copy_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Packaged bytes'):
            package.assemble(self.base / ('stale-profile-' + uuid.uuid4().hex), self.sources, COMPILER, {'native_profile_entries': {'main.lua': '0' * 32}})

    def test_repackage_cannot_overwrite_existing_directory(self):
        with self.assertRaisesRegex(ValueError, 'Output already exists'):
            package.assemble(self.destination, self.sources, COMPILER, {})


if __name__ == '__main__':
    TEST_ROOT = ROOT / 'build/private-packages/tests'
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
              'builder_sha256': package.sha(Path(package.__file__)), 'tests_sha256': package.sha(Path(__file__)),
              'synthetic_engine_only': True, 'real_game_launched': False, 'rom_read': False,
              'local_logs': {'paths': ['user/logs/stdout.log', 'user/logs/stderr.log'],
                             'max_bytes_each': LOG_LIMIT, 'append_only': True,
                             'capture_buffer_bytes_each': LOG_LIMIT, 'io_block_bytes': 8192,
                             'post_exit_wait_milliseconds_total': 2000,
                             'native_production_stdout_verified': False},
              'limits': 'Compiled synthetic probes and input-policy checks; not visible native ROM import, audio, controller, clean-machine or native-game acceptance.'}
    (TEST_ROOT.parent / 'package-tests.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
