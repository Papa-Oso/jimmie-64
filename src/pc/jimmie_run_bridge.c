#ifdef JIMMIE_NATIVE_HEAD
#include "jimmie_run_bridge.h"
#include "jimmie_run_clock.h"
#include "jimmie_companion_profile.h"
#include "fs/fs.h"
#include "mods/mods.h"
#include "network/network.h"
#include "game/area.h"
#include "game/game_init.h"
#include "game/hardcoded.h"
#include "game/interaction.h"
#include "game/level_update.h"
#include "game/save_file.h"
#include "behavior_data.h"
#include "object_constants.h"
#include "object_fields.h"
#include "sm64.h"
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>

extern struct SaveBuffer gSaveBuffer;
extern u8 gSaveFileUsingBackupSlot;
extern s8 gDebugLevelSelect;
static JrcState sClock;
static unsigned int routeFileEpoch;
unsigned int jimmie_route_file_epoch(void) { return routeFileEpoch; }
static struct Object *sFinishPuff;
static u32 sCollectionFrame;

static void trace(const char *event) {
    const char *path = getenv("JIMMIE_HEAD_TRACE");
    if (!path || !*path) return;
    FILE *f = fopen(path, "a");
    if (!f) return;
    fprintf(f, "{\"event\":\"%s\",\"phase\":%d,\"frame\":%u,\"elapsed_us\":%" PRIu64
               ",\"best_us\":%" PRIu64 ",\"storage_ready\":%d}\n",
            event, sClock.phase, gGlobalTimer, sClock.elapsed_us, sClock.best_us, sClock.storage_ready);
    fclose(f);
}

/* Conservative personal-practice profile; not leaderboard certification. */
static bool eligible(void) {
    return gNetworkType == NT_SERVER && gServerSettings.maxPlayers == 1
        && gNetworkPlayerLocal && gNetworkPlayerLocal->connected
        && network_player_connected_count() == 1 && jimmie_companion_profile_ok()
        && !gServerSettings.skipIntro && !gServerSettings.bubbleDeath
        && gServerSettings.stayInLevelAfterStar == STAR_LEAVE_LEVEL
        && gServerSettings.bouncyLevelBounds == BOUNCY_LEVEL_BOUNDS_OFF
        && !gServerSettings.pauseAnywhere && !gSaveFileUsingBackupSlot
        && !gDebugLevelSelect && !gCurrDemoInput && !gCurrCreditsEntry
        && gLevelValues.entryLevel == LEVEL_CASTLE_GROUNDS
        && gMarioStates[0].action != ACT_DEBUG_FREE_MOVE
        && !getenv("JIMMIE_HEAD_TEST_START") && !getenv("JIMMIE_HEAD_TEST_INTERACTION")
        && !getenv("JIMMIE_SDL_CONTROLLER_TEST") && !getenv("JIMMIE_ROUTE_PAD_TEST");
}

static bool clean_file(void) {
    int file = gCurrSaveFileNum - 1;
    if (file < 0 || file >= NUM_SAVE_FILES || gSaveFileUsingBackupSlot) return false;
    const struct SaveFile *save = &gSaveBuffer.files[file][0];
    if (save->flags & ~SAVE_FLAG_FILE_EXISTS) return false;
    /* Raw masks include cannon bits omitted by public star-count APIs. */
    for (size_t i = 0; i < sizeof(save->courseStars); ++i) if (save->courseStars[i]) return false;
    for (size_t i = 0; i < sizeof(save->courseCoinScores); ++i) if (save->courseCoinScores[i]) return false;
    return true;
}

static int stars(void) {
    return save_file_get_total_star_count(gCurrSaveFileNum - 1, COURSE_MIN - 1, COURSE_MAX - 1);
}

void jimmie_run_boot(void) {
    jrc_boot(&sClock, jrc_monotonic_us());
    sFinishPuff = NULL;
    trace("pb_boot");
}

void jimmie_run_load(void) {
    if (!jrc_load_pb(&sClock, fs_get_write_path("jimmie_16star_pb.txt")))
        fprintf(stderr, "Jimmie PB: stored record unavailable/corrupt; seed retained, writes disabled.\n");
    trace("pb_loaded");
}

void jimmie_run_begin_file(void) {
    ++routeFileEpoch;
    /* NT_NONE is the CoopDX menu/demo, not selection of a played save. */
    if (gNetworkType == NT_NONE) return;
    jrc_begin_file(&sClock, jrc_monotonic_us(), gCurrSaveFileNum, clean_file(), eligible());
    if (getenv("JIMMIE_HEAD_TRACE") && sClock.phase == JRC_INVALID)
        fprintf(stderr, "Jimmie PB ineligible: %s\n", sClock.reason ? sClock.reason : "unknown");
    sFinishPuff = NULL;
    trace("pb_file_selected");
}

void jimmie_run_update(void) {
    JrcPhase previous = sClock.phase;
    if (sClock.phase == JRC_RUNNING)
        jrc_observe(&sClock, jrc_monotonic_us(), gCurrSaveFileNum, stars(), eligible());
    else jrc_tick(&sClock, jrc_monotonic_us());
    if (sFinishPuff && (sClock.phase != JRC_RUNNING || gCurrLevelNum != LEVEL_BOWSER_3
                      || (u32)(gGlobalTimer - sCollectionFrame) > 1)) sFinishPuff = NULL;
    if (previous != sClock.phase) trace("pb_invalidated");
    if (sClock.phase == JRC_RUNNING && gGlobalTimer % 300 == 0) trace("pb_running");
}

void jimmie_run_disqualify(void) {
    if (sClock.phase == JRC_RUNNING) {
        jrc_invalidate(&sClock, "scripted/debug warp or frame advance");
        sFinishPuff = NULL;
        trace("pb_invalidated");
    }
}

void jimmie_run_collection(struct MarioState *m, struct Object *star, struct Object *puff) {
    if (sClock.phase != JRC_RUNNING || !m || !star || !puff || m != &gMarioStates[0]
        || gCurrLevelNum != LEVEL_BOWSER_3 || star->behavior != bhvGrandStar
        || !(star->oInteractionSubtype & INT_SUBTYPE_GRAND_STAR) || stars() != 16 || !eligible()) return;
    sFinishPuff = puff;
    sCollectionFrame = gGlobalTimer;
    trace("pb_collection_armed");
}

void jimmie_run_puff_emitted(struct Object *puff) {
    if (!puff || puff != sFinishPuff) return;
    sFinishPuff = NULL;
    bool proof = gCurrLevelNum == LEVEL_BOWSER_3 && puff->parentObj == gMarioStates[0].marioObj
                 && (u32)(gGlobalTimer - sCollectionFrame) <= 1
                 && gMarioStates[0].action == ACT_JUMBO_STAR_CUTSCENE;
    JrcResult result = jrc_finish(&sClock, jrc_monotonic_us(), gCurrSaveFileNum, stars(), proof, eligible());
    if (result == JRC_STORE_FAILED)
        fprintf(stderr, "Jimmie PB: result could not be saved; previous best retained.\n");
    trace(result == JRC_NEW_PB ? "pb_improved" : result == JRC_STORE_FAILED ? "pb_store_failed"
          : result == JRC_NO_CHANGE ? "pb_finished" : "pb_finish_rejected");
}

void jimmie_run_best_text(char *text, size_t capacity) {
    jrc_format(sClock.best_us, text, capacity);
}
#endif
