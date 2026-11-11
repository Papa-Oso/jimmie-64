"""Build a private, ROM-free Windows candidate; never install, launch, or publish it.

Python and the existing local .NET compiler are developer-only requirements.
The produced launcher uses Windows .NET Framework, never a Python supervisor.
"""
from pathlib import Path, PurePosixPath
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TITLE_NAMES = tuple('title_good_morning_%02d.ogg' % i for i in range(1, 4)) + (
    'title_pink_bitch_insurance.ogg', 'title_whats_happening.ogg')
ACTORS = ('jimmie_orig_board_geo.bin', 'jimmie_orig_rg_geo.bin',
          'jimmie_orig_tee_geo.bin', 'jimmie_orig_vest_geo.bin',
          'jimmie_original_brace_geo.bin')
LANGUAGES = ('Czech', 'Dutch', 'English', 'French', 'German', 'Italian',
             'Japanese', 'Polish', 'Portuguese', 'Russian', 'Spanish')
SYSTEM_DLLS = {name.lower() + '.dll' for name in (
    'ADVAPI32', 'comdlg32', 'GDI32', 'IMM32', 'KERNEL32', 'msvcrt', 'ole32',
    'OLEAUT32', 'OPENGL32', 'SETUPAPI', 'SHELL32', 'SHLWAPI', 'USER32',
    'VERSION', 'WININET', 'WINMM', 'WS2_32')}
GAME_ARGS = ('--server 7777 --playercount 1 --windowed --skip-update-check '
             '--no-discord --disable-mods --enable-mod jimmie --console --savepath ')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_file(path, base):
    """Reject symlinks/junctions as well as lexical/resolved escapes."""
    path, base = Path(path).absolute(), Path(base).absolute()
    require(path.is_relative_to(base), 'Input escapes root: ' + str(path))
    for parent in (path, *path.parents):
        if not parent.is_relative_to(base):
            break
        if parent.exists():
            st = parent.lstat()
            require(not parent.is_symlink() and not (getattr(st, 'st_file_attributes', 0) & 0x400),
                    'Reparse point refused: ' + str(parent))
    require(path.resolve().is_relative_to(base.resolve()), 'Resolved path escapes root')
    require(path.is_file() and path.stat().st_size > 0, 'Missing/empty input: ' + str(path))
    return path


def profile_entries(header):
    entries = {}
    for path, octets, dynamic in re.findall(r'\{"([^"\n]+)",\s*\{([^}]+)\},\s*(\d+)\}', header):
        require(path not in entries and dynamic == '0', 'Duplicate or dynamic profile entry')
        values = re.findall(r'0x([0-9a-fA-F]{2})', octets)
        require(len(values) == 16, 'Malformed profile MD5: ' + path)
        entries[path] = ''.join(values).lower()
    require(entries, 'Empty native profile')
    return entries


def plan_inputs(root, cache_dir, title_dir, expected_engine, expected_profile):
    """An explicit allowlist, not a recursive copy of the personal installation."""
    root, cache_dir, title_dir = map(Path, (root, cache_dir, title_dir))
    build = root / 'build/us_pc'
    engine = safe_file(build / 'sm64coopdx.exe', root)
    profile = safe_file(root / 'src/pc/generated/jimmie_companion_profile.inc.h', root)
    require(sha(engine) == expected_engine, 'Engine identity changed')
    require(sha(profile) == expected_profile, 'Profile identity changed')
    frozen = json.loads((root / 'docs/jimmie/integration/readiness.json').read_text(encoding='utf-8'))
    # Original reviewed names plus explicitly reviewed outcome and rail modules.
    names = {name for name in frozen['runtime_hashes']
             if '/' not in name and name.endswith('.lua') or
             name.startswith('sound/') and name.endswith('.ogg') and name.count('/') == 1}
    names.update(('jimmie_audition.lua', 'trick_outcomes.lua', 'companion_spawn.lua', 'skate_rail_index.lua',
                  'skate_surface_rails.lua', 'skate_visible_rails.lua',
                  'skate_rail_presentation.lua', 'skate_rail_binding.lua'))
    require(sum(name.startswith('sound/') for name in names) == 37, 'Expected 37 reviewed recording names')
    require(all(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
                and '\\' not in name and ':' not in name for name in names), 'Unsafe manifest path')
    sources = {'game/sm64coopdx.exe': engine}
    for name in sorted(names):
        sources['game/mods/jimmie/' + name] = safe_file(root / 'mods/jimmie' / name, root)
    for name in ACTORS:
        sources['game/mods/jimmie/actors/' + name] = safe_file(cache_dir / name, root)
    loaded = {name.removeprefix('game/mods/jimmie/'): path for name, path in sources.items()
              if name.startswith('game/mods/jimmie/')}
    pins = profile_entries(profile.read_text(encoding='utf-8'))
    require(set(pins) == set(loaded), 'Native profile inventory does not match package (rebuild/pin first)')
    for name, path in loaded.items():
        require(hashlib.md5(path.read_bytes()).hexdigest() == pins[name], 'Native profile content differs: ' + name)
    for name in TITLE_NAMES:
        sources['game/jimmie-title/' + name] = safe_file(title_dir / name, title_dir)
    for name in LANGUAGES:
        sources['game/lang/' + name + '.ini'] = safe_file(build / 'lang' / (name + '.ini'), root)
    sources['FIRST_RUN.md'] = safe_file(root / 'docs/jimmie/FIRST_RUN.md', root)
    sources['RIGHTS_STATUS.md'] = safe_file(root / 'docs/jimmie/RIGHTS_STATUS.md', root)
    require(sha(profile) == expected_profile, 'Profile changed during input verification')
    return sources


def verify_engine_imports(engine, objdump):
    result = subprocess.run([str(objdump), '-p', str(engine)], capture_output=True,
                            text=True, check=True, timeout=30,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    imports = re.findall(r'DLL Name:\s*(\S+)', result.stdout)
    require(imports and all(name.lower() in SYSTEM_DLLS for name in imports),
            'Unreviewed engine dependency: ' + repr(imports))
    return imports


LAUNCHER = r'''
using System;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32.SafeHandles;

internal static class JimmieLauncher {
    private const string MutexName = @"Local\Jimmie64-Unified-Launch";
    private const string EngineName = "sm64coopdx.exe";
    private static readonly Dictionary<string, string> Files = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) {
        // FILE_PINS
    };
    private static string Root;
    private static void RejectReparse(string path) {
        string full = Path.GetFullPath(path);
        if (!full.StartsWith(Root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) && !String.Equals(full, Root, StringComparison.OrdinalIgnoreCase))
            throw new IOException("Path escapes this package.");
        while (full.Length >= Root.Length) {
            if ((File.Exists(full) || Directory.Exists(full)) && (File.GetAttributes(full) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Linked folders/files are not supported: " + full);
            if (String.Equals(full, Root, StringComparison.OrdinalIgnoreCase)) break;
            full = Path.GetDirectoryName(full);
        }
    }
    private static string LocalPath(string path) {
        string result = Path.Combine(Root, path.Replace('/', Path.DirectorySeparatorChar));
        RejectReparse(result);
        return result;
    }
    private static string Hash(string path) {
        using (SHA256 hash = SHA256.Create()) using (FileStream stream = File.OpenRead(path))
            return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }
    private static void ExactTree(string path) {
        foreach (string entry in Directory.GetFileSystemEntries(LocalPath(path))) {
            RejectReparse(entry);
            string rel = entry.Substring(Root.Length + 1).Replace('\\', '/');
            if (Directory.Exists(entry)) ExactTree(rel);
            else if (!Files.ContainsKey(rel)) throw new IOException("Unexpected package file: " + rel);
        }
    }
    private static void Verify() {
        foreach (KeyValuePair<string, string> pin in Files) {
            string path = LocalPath(pin.Key);
            if (!File.Exists(path) || Hash(path) != pin.Value)
                throw new IOException("Package file missing or changed: " + pin.Key + ". Use a fresh verified candidate; your saves have not been changed.");
        }
        ExactTree("game/mods"); ExactTree("game/lang"); ExactTree("game/jimmie-title");
        foreach (string dll in Directory.GetFiles(LocalPath("game"), "*.dll"))
            throw new IOException("Unexpected local DLL: " + Path.GetFileName(dll));
        RejectReparse(Path.Combine(Root, "user"));
    }
    private static void EnsureDirectory(string relative) {
        string path = LocalPath(relative);
        Directory.CreateDirectory(path);
        RejectReparse(path);
    }
    // Logging is best effort. Pipe readers never wait for filesystem operations.
    private const int LogLimit = 512 * 1024;
    private const int LogBlock = 8192;
    private const int LogExitWaitMilliseconds = 2000;
    [StructLayout(LayoutKind.Sequential)]
    private struct FileInformation {
        public uint Attributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME Creation, Access, Write;
        public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(string path, uint access, uint share,
        IntPtr security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInformation information);
    private static SafeFileHandle OpenLogHandle(string path, bool directory) {
        // OPEN_REPARSE_POINT refuses following a final link, including a dangling one.
        // No FILE_SHARE_DELETE: pin every directory while creating/opening its child.
        SafeFileHandle handle = CreateFile(path, directory ? 0x80u : 0x40000000u,
            directory ? 3u : 1u, IntPtr.Zero, directory ? 3u : 4u,
            0x00200000u | (directory ? 0x02000000u : 0u), IntPtr.Zero);
        FileInformation information;
        if (handle.IsInvalid || !GetFileInformationByHandle(handle, out information) ||
            (information.Attributes & (uint)FileAttributes.ReparsePoint) != 0 ||
            ((information.Attributes & (uint)FileAttributes.Directory) != 0) != directory ||
            (!directory && information.Links != 1)) {
            handle.Dispose();
            throw new IOException("Local log path is unavailable or linked.");
        }
        return handle;
    }
    private sealed class Capture {
        private readonly Stream input;
        private readonly string name;
        private readonly byte[] pending = new byte[LogLimit];
        private readonly object gate = new object();
        private readonly Thread reader, writer;
        private int available;
        private bool complete, disabled;
        public Capture(Stream stream, string filename) {
            input = stream;
            name = filename;
            reader = new Thread(Drain); reader.IsBackground = true;
            writer = new Thread(Append); writer.IsBackground = true;
            // Start draining before opening a file, even if that open later fails/hangs.
            reader.Start();
            try { writer.Start(); }
            catch (Exception) { lock (gate) { disabled = true; } }
        }
        private void Drain() {
            byte[] block = new byte[LogBlock];
            try {
                int count;
                while ((count = input.Read(block, 0, block.Length)) != 0) {
                    lock (gate) {
                        if (!disabled) {
                            int take = Math.Min(count, pending.Length - available);
                            if (take != 0) {
                                Buffer.BlockCopy(block, 0, pending, available, take);
                                available += take;
                                Monitor.Pulse(gate);
                            }
                        }
                    }
                }
            } catch (IOException) { } catch (ObjectDisposedException) { }
            finally { lock (gate) { complete = true; Monitor.Pulse(gate); } }
        }
        private void Append() {
            List<SafeFileHandle> directories = new List<SafeFileHandle>();
            try {
                // Fixed paths only. Reject links before any log directory/file creation.
                string folder = LocalPath("user/logs");
                string path = LocalPath("user/logs/" + name);
                directories.Add(OpenLogHandle(Root, true));
                directories.Add(OpenLogHandle(LocalPath("user"), true));
                if (!Directory.Exists(folder)) Directory.CreateDirectory(folder);
                directories.Add(OpenLogHandle(folder, true));
                using (SafeFileHandle handle = OpenLogHandle(path, false))
                using (FileStream output = new FileStream(handle, FileAccess.Write, LogBlock, false)) {
                    long position = output.Seek(0, SeekOrigin.End);
                    byte[] block = new byte[LogBlock];
                    int consumed = 0;
                    while (position < LogLimit) {
                        int count;
                        lock (gate) {
                            while (consumed == available && !complete) Monitor.Wait(gate);
                            count = Math.Min(available - consumed, (int)Math.Min(LogBlock, LogLimit - position));
                            if (count == 0) break;
                            Buffer.BlockCopy(pending, consumed, block, 0, count);
                            consumed += count;
                        }
                        output.Write(block, 0, count);
                        output.Flush();
                        position += count;
                    }
                }
            } catch (Exception) {
                // No dialogs, retry loops, uploads or gameplay failure for unavailable logs.
            } finally {
                lock (gate) { disabled = true; }
                foreach (SafeFileHandle handle in directories) handle.Dispose();
            }
        }
        public void Finish(Stopwatch elapsed) {
            foreach (Thread thread in new Thread[] { reader, writer }) {
                int left = Math.Max(0, LogExitWaitMilliseconds - (int)elapsed.ElapsedMilliseconds);
                if (left != 0 && (thread.ThreadState & System.Threading.ThreadState.Unstarted) == 0) thread.Join(left);
            }
        }
    }
    private static ProcessStartInfo Command() {
        string save = LocalPath("user/save");
        ProcessStartInfo command = new ProcessStartInfo(LocalPath("game/" + EngineName));
        command.WorkingDirectory = LocalPath("game");
        command.UseShellExecute = false;
        command.CreateNoWindow = true;
        command.RedirectStandardOutput = true;
        command.RedirectStandardError = true;
        command.Arguments = "GAME_ARGUMENTS" + "\"" + save + "\"";
        List<string> remove = new List<string>();
        foreach (DictionaryEntry item in command.EnvironmentVariables) {
            string key = (string)item.Key;
            if (key.StartsWith("JIMMIE_", StringComparison.OrdinalIgnoreCase) || key.StartsWith("SDL_", StringComparison.OrdinalIgnoreCase)) remove.Add(key);
        }
        foreach (string key in remove) command.EnvironmentVariables.Remove(key);
        command.EnvironmentVariables["JIMMIE_NATIVE_HEAD"] = "1";
        command.EnvironmentVariables["SDL_JOYSTICK_RAWINPUT"] = "0";
        command.EnvironmentVariables["APPDATA"] = LocalPath("user/appdata");
        command.EnvironmentVariables["LOCALAPPDATA"] = LocalPath("user/localappdata");
        command.EnvironmentVariables["TEMP"] = LocalPath("user/temp");
        command.EnvironmentVariables["TMP"] = LocalPath("user/temp");
        return command;
    }
    [STAThread]
    private static int Main(string[] args) {
        bool check = false, silent = false;
        foreach (string arg in args) {
            if (arg == "--check") check = true;
            else if (arg == "--no-dialog") silent = true;
            else { Console.Error.WriteLine("Unknown launcher option: " + arg); return 2; }
        }
        try {
            Root = Path.GetDirectoryName(typeof(JimmieLauncher).Assembly.Location).TrimEnd(Path.DirectorySeparatorChar);
            Verify();
            if (check) {
                Console.WriteLine("Package hashes verified. ROM intentionally not required. Native importer opens when no supported ROM is present. No game launched.");
                return 0;
            }
            bool created;
            using (Mutex mutex = new Mutex(true, MutexName, out created)) {
                if (!created) throw new IOException("Jimmie 64 is already starting or running. Close it before opening again.");
                try {
                    Process[] games = Process.GetProcessesByName("sm64coopdx");
                    int count = games.Length;
                    foreach (Process game in games) game.Dispose();
                    if (count != 0) throw new IOException("A game is already running. Close it before opening Jimmie 64 again.");
                    foreach (string dir in new string[] { "user/save", "user/appdata", "user/localappdata", "user/temp" }) EnsureDirectory(dir);
                    // CreateNew never overwrites an existing save or user configuration.
                    string config = LocalPath("user/save/sm64config.txt");
                    if (!File.Exists(config)) using (FileStream stream = new FileStream(config, FileMode.CreateNew, FileAccess.Write))
                        using (StreamWriter writer = new StreamWriter(stream))
                            writer.Write("fullscreen false\namount_of_players 1\nbubble_death false\nskip_intro false\npause_anywhere false\ncoop_mod_dev_mode false\nbackground_gamepad false\n");
                    // No ROM search, copy, validation, download or hidden diagnostic Start.
                    using (Process child = Process.Start(Command())) {
                        Capture stdout = new Capture(child.StandardOutput.BaseStream, "stdout.log");
                        Capture stderr = new Capture(child.StandardError.BaseStream, "stderr.log");
                        child.WaitForExit();
                        Stopwatch elapsed = Stopwatch.StartNew();
                        stdout.Finish(elapsed); stderr.Finish(elapsed);
                        if (child.ExitCode != 0) throw new IOException("Game exited with code " + child.ExitCode + ". Your private save is in " + LocalPath("user/save"));
                    }
                } finally { mutex.ReleaseMutex(); }
            }
            return 0;
        } catch (Exception error) {
            Console.Error.WriteLine(error.Message);
            if (!check && !silent) MessageBox.Show(error.Message, "Jimmie 64 could not start", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
'''


def compile_launcher(destination, pins, compiler, template=LAUNCHER):
    lines = ['        { ' + json.dumps(path) + ', ' + json.dumps(digest) + ' },'
             for path, digest in sorted(pins.items())]
    source = template.replace('        // FILE_PINS', '\n'.join(lines)).replace('GAME_ARGUMENTS', GAME_ARGS)
    cs = destination / 'JimmieLauncher.cs'
    cs.write_text(source, encoding='utf-8', newline='\n')
    temp = destination / 'compiler-temp'
    temp.mkdir(exist_ok=True)
    compiler_env = dict(os.environ, TEMP=str(temp), TMP=str(temp))
    result = subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x64',
        '/reference:System.Windows.Forms.dll', '/out:' + str(destination / 'Launch Jimmie 64.exe'), str(cs)],
        capture_output=True, text=True, timeout=60, env=compiler_env,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(result.returncode == 0, 'Launcher compilation failed:\n' + result.stdout + result.stderr)
    return destination / 'Launch Jimmie 64.exe'


def assemble(destination, sources, compiler, metadata):
    """Fresh directory only: never update a user's runtime in place."""
    destination = Path(destination)
    require(not destination.exists(), 'Output already exists; choose a new package (never overwrite saves)')
    destination.mkdir(parents=True)
    pins = {}
    for name, source in sorted(sources.items()):
        require(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
                and '\\' not in name and ':' not in name, 'Unsafe package destination')
        before = sha(source)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        require(sha(target) == before == sha(source), 'Source changed while packaging: ' + name)
        pins[name] = before
    if 'engine_sha256' in metadata:
        require(pins.get('game/sm64coopdx.exe') == metadata['engine_sha256'], 'Engine changed while packaging')
    if 'native_profile_entries' in metadata:
        actual = {name.removeprefix('game/mods/jimmie/'): hashlib.md5((destination / name).read_bytes()).hexdigest()
                  for name in pins if name.startswith('game/mods/jimmie/')}
        require(actual == metadata['native_profile_entries'], 'Packaged bytes do not match native profile')
    manifest = dict(metadata, schema=1, private_only=True, rom_included=False,
                    ai_supervisor_enabled=False, runtime_files=pins.copy(),
                    limits='Private candidate, not licensed for distribution. No clean-machine, visible-ROM-import, controller, listening, multiplayer or played-run acceptance is implied.')
    path = destination / 'package-manifest.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    pins[path.name] = sha(path)
    executable = compile_launcher(destination, pins, compiler)
    check = subprocess.run([str(executable), '--check'], capture_output=True, text=True,
                           timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(check.returncode == 0, 'Packaged launcher check failed: ' + check.stderr)
    report = {'passed': True, 'package': str(destination), 'runtime_files': len(sources),
              'manifest_sha256': sha(path), 'launcher_sha256': sha(executable),
              'launcher_source_sha256': sha(destination / 'JimmieLauncher.cs'),
              'check_output': check.stdout.strip(), 'no_game_launched': True,
              'no_rom_read_or_copied': True, 'not_installed': True, 'no_publication': True}
    (destination / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-engine-sha256', required=True)
    parser.add_argument('--expected-profile-sha256', required=True)
    parser.add_argument('--actor-cache-dir', type=Path, required=True)
    parser.add_argument('--title-dir', type=Path, required=True, help='Explicit local directory of the five private title recordings')
    parser.add_argument('--name', default=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    parser.add_argument('--plan', action='store_true', help='Validate all inputs without writing or launching')
    args = parser.parse_args()
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.name), 'Unsafe package name')
    sources = plan_inputs(ROOT, args.actor_cache_dir, args.title_dir,
                          args.expected_engine_sha256, args.expected_profile_sha256)
    objdump = ROOT.parent / 'jimmie-native-head-toolchain/msys64/mingw64/bin/objdump.exe'
    dependencies = verify_engine_imports(sources['game/sm64coopdx.exe'], objdump)
    destination = ROOT / 'build/private-packages' / args.name
    for parent in (destination, *destination.parents):
        if parent.exists():
            require(not (getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400) and not parent.is_symlink(),
                    'Linked output ancestor refused')
    metadata = {'engine_sha256': args.expected_engine_sha256,
                'native_profile_sha256': args.expected_profile_sha256,
                'engine_dll_imports': dependencies, 'builder_sha256': sha(Path(__file__)),
                'native_profile_matches_package': True,
                'native_profile_entries': profile_entries((ROOT / 'src/pc/generated/jimmie_companion_profile.inc.h').read_text(encoding='utf-8'))}
    require(sha(ROOT / 'src/pc/generated/jimmie_companion_profile.inc.h') == args.expected_profile_sha256,
            'Profile changed before packaging')
    if args.plan:
        print(json.dumps(dict(metadata, output=str(destination), files=len(sources), read_only=True), indent=2))
        return 0
    compiler = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    require(compiler.is_file(), 'Existing Windows .NET Framework compiler not found; no download attempted')
    report = assemble(destination, sources, compiler, metadata)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
