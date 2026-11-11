"""Exercise exact audio cache functions with explicit OS DMA/log stubs.

No ROM, sound device, game process, installed files or Git index are touched.
Use --baseline-load to identify the preserved pre-fix source for byte/metadata
comparison; this is cache/transfer evidence, not audible output acceptance.
"""
from pathlib import Path
import argparse, hashlib, json, os, subprocess
ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA = '9af237df72dbf61cb542b1c1a5c5622c63f5774eaa2d0d064130debafa107c84'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def between(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
typedef int32_t s32; typedef intptr_t ssize_t;
#define UNUSED __attribute__((unused))
#define TRUE 1
#define FALSE 0
#define ALIGN16(val) (((val) + 0xF) & ~0xF)
#define SAMPLE_DMA_COUNT 0x100
#define bzero(ptr, size) memset(ptr, 0, size)
#define osInvalDCache(ptr, size) ((void)0)
#define OS_MESG_PRI_NORMAL 0
#define OS_READ 0
static unsigned errorCount;
static void record_error(const char *format, ...) { (void)format; ++errorCount; }
#define LOG_ERROR(...) record_error(__VA_ARGS__)
static int gCurrAudioFrameDmaIoMesgBufs[128], gCurrAudioFrameDmaQueue;
static u32 gCurrAudioFrameDmaCount;
static void osPiStartDma(void *request, int priority, int direction, uintptr_t source,
                        void *destination, u32 bytes, void *queue) {
    (void)request; (void)priority; (void)direction; (void)queue;
    memcpy(destination, (void *)source, bytes);
}
'''
GLOBALS = r'''
static struct SoundAllocPool gNotesAndBuffersPool;
static struct SharedDma sSampleDmas[SAMPLE_DMA_COUNT];
static u32 gSampleDmaNumListItems, sSampleDmaListSize1, sUnused80226B40;
static u8 sSampleDmaReuseQueue1[256], sSampleDmaReuseQueue2[256];
static u8 sSampleDmaReuseQueueTail1, sSampleDmaReuseQueueTail2;
static u8 sSampleDmaReuseQueueHead1, sSampleDmaReuseQueueHead2;
static u32 sDmaBufSize;
static s32 gMaxSimultaneousNotes;
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', required=True, type=Path)
    parser.add_argument('--baseline-load', required=True, type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/audio-dma-tests/results')
    args = parser.parse_args()
    baseline = args.baseline_load.read_text(encoding='utf-8-sig')
    assert hashlib.sha256(baseline.encode('utf-8')).hexdigest() == BASELINE_SHA, 'Baseline canonical identity differs'
    load = (ROOT / 'src/audio/load.c').read_text(encoding='utf-8-sig')
    old = baseline
    heap = (ROOT / 'src/audio/heap.c').read_text(encoding='utf-8-sig')
    header = (ROOT / 'src/audio/heap.h').read_text(encoding='utf-8-sig')
    selected = PREFIX + between(header, 'struct SoundAllocPool\n', '\nstruct SeqOrBankEntry')
    selected += between(load, 'struct SharedDma {', '\n// EU only') + GLOBALS
    selected += between(heap, 'void *soundAlloc(', '\n#ifdef VERSION_SH\nvoid *sound_alloc_uninitialized')
    selected += between(old, 'void init_sample_dma_buffers(', '\n#ifndef static').replace('init_sample_dma_buffers(', 'baseline_init_sample_dma_buffers(', 1)
    selected += between(load, 'void decrease_sample_dma_ttls()', '\n#ifndef static')
    selected += '\n#include "' + (ROOT / 'tools/test_jimmie_audio_dma_native.c').as_posix() + '"\n'
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / 'build'):
        raise SystemExit('Test outputs must remain under this checkout build directory')
    out.mkdir(parents=True, exist_ok=True)
    temp = out / 'temp'; temp.mkdir(exist_ok=True)
    sliced = out / 'selected_audio_functions.c'; sliced.write_text(selected, encoding='utf-8')
    compiler = args.cc.resolve()
    env = dict(os.environ, TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
    env['PATH'] = str(compiler.parent) + os.pathsep + env.get('PATH', '')
    report = {'baseline_sha256': sha(args.baseline_load), 'baseline_canonical_sha256': BASELINE_SHA,
              'baseline_commit': '33d90f03f49650809bcb59fe3648f3f455bf1987', 'source_sha256': {p: sha(ROOT/p) for p in (
        'src/audio/load.c', 'src/audio/heap.c', 'src/audio/heap.h',
        'tools/test_jimmie_audio_dma.py', 'tools/test_jimmie_audio_dma_native.c')},
        'selected_functions': ['soundAlloc', 'init_sample_dma_buffers', 'sample_dma_cache_can_grow',
                               'decrease_sample_dma_ttls', 'dma_sample_data'],
        'limits': 'Verbatim source functions with synthetic memory, OS DMA memcpy and log-count stubs. No audible, device, native-game, OGG or PCM-output acceptance.', 'variants': {}}
    for version in ('US', 'JP'):
        exe = out / ('audio-cache-' + version.lower() + '.exe')
        command = [str(compiler), '-std=gnu11', '-O2', '-Wall', '-Wextra',
                   '-Wno-sign-compare', '-DVERSION_' + version, str(sliced), '-o', str(exe)]
        build = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                               timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        item = {'compile_exit': build.returncode, 'compile_output': build.stdout + build.stderr}
        if build.returncode == 0:
            run = subprocess.run([str(exe)], env=env, capture_output=True, text=True, timeout=30,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            item.update(run_exit=run.returncode, output=run.stdout + run.stderr)
        report['variants'][version] = item
    report['passed'] = all(item.get('run_exit') == 0 for item in report['variants'].values())
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
