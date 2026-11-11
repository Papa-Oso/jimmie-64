/* Exercises verbatim production allocator/cache/transfer functions included by
 * test_jimmie_audio_dma.py. OS DMA is an explicit memcpy stub, not audio output. */
#include <stdarg.h>
static unsigned char poolMemory[4 * 1024 * 1024 + 32] __attribute__((aligned(16)));
static unsigned char sampleMemory[2 * 1024 * 1024] __attribute__((aligned(16)));
static unsigned tests;

struct CacheSnapshot {
    struct SharedDma entries[SAMPLE_DMA_COUNT];
    u8 queue1[256], queue2[256];
    u32 count, count1, used, bufferSize;
    u8 head1, tail1, head2, tail2;
    unsigned long long memoryHash;
};

static void configure(u32 bytes, s32 notes) {
    assert(bytes <= sizeof(poolMemory) - 32);
    memset(poolMemory, 0xa5, sizeof(poolMemory));
    memset(sSampleDmas, 0, sizeof(sSampleDmas));
    memset(sSampleDmaReuseQueue1, 0, sizeof(sSampleDmaReuseQueue1));
    memset(sSampleDmaReuseQueue2, 0, sizeof(sSampleDmaReuseQueue2));
    gNotesAndBuffersPool.start = gNotesAndBuffersPool.cur = poolMemory;
    gNotesAndBuffersPool.size = bytes;
    gNotesAndBuffersPool.numAllocatedEntries = 0;
    gSampleDmaNumListItems = sSampleDmaListSize1 = sDmaBufSize = 0;
    sSampleDmaReuseQueueHead1 = sSampleDmaReuseQueueTail1 = 0;
    sSampleDmaReuseQueueHead2 = sSampleDmaReuseQueueTail2 = 0;
    gMaxSimultaneousNotes = notes;
    errorCount = 0;
}

static void snapshot(struct CacheSnapshot *out) {
    memset(out, 0, sizeof(*out));
    memcpy(out->entries, sSampleDmas, sizeof(sSampleDmas));
    memcpy(out->queue1, sSampleDmaReuseQueue1, sizeof(out->queue1));
    memcpy(out->queue2, sSampleDmaReuseQueue2, sizeof(out->queue2));
    out->count = gSampleDmaNumListItems;
    out->count1 = sSampleDmaListSize1;
    out->used = (u32)(gNotesAndBuffersPool.cur - poolMemory);
    out->bufferSize = sDmaBufSize;
    out->head1 = sSampleDmaReuseQueueHead1; out->tail1 = sSampleDmaReuseQueueTail1;
    out->head2 = sSampleDmaReuseQueueHead2; out->tail2 = sSampleDmaReuseQueueTail2;
    out->memoryHash = 1469598103934665603ULL;
    for (u32 i = 0; i < gNotesAndBuffersPool.size; ++i)
        out->memoryHash = (out->memoryHash ^ poolMemory[i]) * 1099511628211ULL;
}

static void guards(void) {
    assert(gNotesAndBuffersPool.cur >= poolMemory);
    assert(gNotesAndBuffersPool.cur <= poolMemory + gNotesAndBuffersPool.size);
    assert(gSampleDmaNumListItems <= 255);
    assert(sSampleDmaListSize1 <= 255);
    for (u32 i = 0; i < 32; ++i)
        assert(poolMemory[gNotesAndBuffersPool.size + i] == 0xa5);
    for (u32 i = 0; i < gSampleDmaNumListItems; ++i) {
        assert(sSampleDmas[i].buffer >= poolMemory);
        assert(sSampleDmas[i].buffer + sSampleDmas[i].bufSize <= poolMemory + gNotesAndBuffersPool.size);
    }
}

static void equivalent(u32 bytes, s32 notes, unsigned oldErrors, unsigned newErrors) {
    struct CacheSnapshot oldState, newState;
    configure(bytes, notes);
    baseline_init_sample_dma_buffers(notes);
    assert(errorCount == oldErrors);
    snapshot(&oldState);
    configure(bytes, notes);
    init_sample_dma_buffers(notes);
    assert(errorCount == newErrors);
    snapshot(&newState);
    assert(memcmp(&oldState, &newState, sizeof(oldState)) == 0);
    guards();
    ++tests;
}

static void transfers(s32 notes, u32 bytes) {
    configure(bytes, notes);
    init_sample_dma_buffers(notes);
    assert(errorCount == 0);
    for (u32 i = 0; i < sizeof(sampleMemory); ++i) sampleMemory[i] = (u8)((i * 13 + (i >> 11)) & 255);
    u8 index = 0;
    for (unsigned i = 0; i < 4096; ++i) {
        const u8 *source = sampleMemory + (i % 512) * 2048 + ((i * 7) % 16);
        gCurrAudioFrameDmaCount = 0;
        u8 *got = dma_sample_data((uintptr_t)source, 32, i & 1, &index);
        assert(got != NULL && memcmp(got, source, 32) == 0);
        /* Also exercise a cache hit before returning expired entries to queues. */
        got = dma_sample_data((uintptr_t)source, 32, i & 1, &index);
        assert(memcmp(got, source, 32) == 0);
        decrease_sample_dma_ttls();
        decrease_sample_dma_ttls();
        guards();
    }
    ++tests;
}

int main(void) {
    const u32 small = 144 * 9 * 4, large = 160 * 9 * 4;
    const u32 counts[] = {1, 17, 100, 128, 200, 254, 255};
    for (unsigned i = 0; i < sizeof(counts)/sizeof(counts[0]); ++i)
        equivalent(counts[i] * small + 4256, 128, 2, 0);
    equivalent(100 * small + 1120, 128, 2, 0);
    equivalent(24 * small + 8 * large, 8, 0, 0);
    equivalent(24 * small + 7 * large + 15, 8, 1, 0);
    equivalent(24 * small + 7 * large + large - 1, 8, 1, 0);
    equivalent(small - 1, 128, 2, 2);
    equivalent(0, 128, 2, 2);
    /* Genuine required allocation failures remain visible through soundAlloc. */
    configure(16, 1);
    assert(soundAlloc(&gNotesAndBuffersPool, 17) == NULL && errorCount == 1);
    ++tests;
    configure(32, 1);
    gSampleDmaNumListItems = 1; gNotesAndBuffersPool.cur += 16;
    assert(sample_dma_cache_can_grow(15));
    assert(sample_dma_cache_can_grow(16));
    assert(!sample_dma_cache_can_grow(17));
    ++tests;
    configure(4 * 1024 * 1024, 128);
    init_sample_dma_buffers(128);
    assert(gSampleDmaNumListItems == 255 && sSampleDmaListSize1 == 255);
    assert(sSampleDmaReuseQueueHead1 == 255 && sSampleDmaReuseQueueTail1 == 0);
    assert(sSampleDmas[255].buffer == NULL && errorCount == 0);
    guards(); ++tests;
    configure(4 * 1024 * 1024, 64);
    init_sample_dma_buffers(64);
    assert(gSampleDmaNumListItems == 255 && sSampleDmaListSize1 == 192);
    assert(sSampleDmaReuseQueueHead2 == 63 && errorCount == 0);
    guards(); ++tests;
    /* Audio session reset clears the count and rewinds the pool, not all arrays. */
    for (unsigned i = 0; i < 100; ++i) {
        gSampleDmaNumListItems = 0;
        gNotesAndBuffersPool.cur = gNotesAndBuffersPool.start;
        gMaxSimultaneousNotes = (i & 1) ? 8 : 128;
        init_sample_dma_buffers(gMaxSimultaneousNotes);
        assert(gSampleDmaNumListItems == ((i & 1) ? 32 : 255));
        guards();
    }
    assert(errorCount == 0); ++tests;
    transfers(8, 24 * small + 8 * large);
    transfers(128, 4 * 1024 * 1024);
    printf("PASS %u groups; baseline cache bytes/metadata unchanged in 13 bounded cases; 100 resets; 16384 synthetic DMA reads; queue cap255; real failures retained\n", tests);
    return 0;
}
