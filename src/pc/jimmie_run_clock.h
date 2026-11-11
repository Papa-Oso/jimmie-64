#ifndef JIMMIE_RUN_CLOCK_H
#define JIMMIE_RUN_CLOCK_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define JRC_SEED_US UINT64_C(1149570000) /* Transcript PB: 19:09.57. */
#define JRC_MAX_US UINT64_C(86400000000)
typedef enum { JRC_BOOT, JRC_RUNNING, JRC_FINISHED, JRC_INVALID } JrcPhase;
typedef enum { JRC_NO_CHANGE=0, JRC_NEW_PB=1, JRC_STORE_FAILED=2, JRC_REJECTED=3 } JrcResult;
typedef struct {
    JrcPhase phase;
    int64_t boot_us, last_us;
    uint64_t elapsed_us, best_us;
    uint64_t split_us[16];          /* elapsed time when each star was collected; 0 = not yet */
    int file, stars;
    bool storage_ready, storage_fault;
    char path[1024];
    const char *reason;
} JrcState;
/* Call once at actual process/game boot, before title/load delays. No reset UI. */
void jrc_boot(JrcState *s, int64_t now_us);
/* Call after filesystem initialization. Missing file means seeded PB, no write. */
bool jrc_load_pb(JrcState *s, const char *path);
/* Fresh-file proof must include zero star masks and no progress flags except FILE_EXISTS.
   eligible must stay true only for the supported single-player, unassisted profile. */
bool jrc_begin_file(JrcState *s, int64_t now_us, int file, bool clean, bool eligible);
void jrc_tick(JrcState *s, int64_t now_us);
void jrc_observe(JrcState *s, int64_t now_us, int file, int stars, bool eligible);
void jrc_invalidate(JrcState *s, const char *reason);
/* Call only from actual local grand-star collection puff/burst path in Bowser 3.
   Caller supplies fresh completion data; merely entering credits is insufficient. */
JrcResult jrc_finish(JrcState *s, int64_t now_us, int file, int stars,
                     bool local_bowser3_grand_star, bool eligible);
void jrc_format(uint64_t microseconds, char *out, size_t capacity);
/* Native monotonic source: QPC on Windows, CLOCK_MONOTONIC elsewhere; no wall fallback. */
int64_t jrc_monotonic_us(void);
#endif
