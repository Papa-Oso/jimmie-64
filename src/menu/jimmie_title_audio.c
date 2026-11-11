#ifdef JIMMIE_NATIVE_HEAD
#include <ultra64.h>
#include "sm64.h"
#include "types.h"
#include <stdio.h>
#include "game/sound_init.h"
#include "seq_ids.h"
#include "pc/fs/fs.h"
#include "pc/lua/utils/smlua_audio_utils.h"
#include "pc/jimmie_run_clock.h"
#include "pc/configfile.h"
#include "pc/pc_main.h"
#include "goddard/jimmie_head.h"
#include "jimmie_title_art.h"

extern struct ModAudio *audio_sample_load_native_title(const char *path);
extern struct ModAudio *audio_stream_load_native_title(const char *path);
static struct ModAudio *sGreeting;
static struct ModAudio *sMusic;
/* One bounded title session; clips never overlap or restart gameplay speech. */
static bool sChatterActive;
static int sChatterAttempts;
static int sLastChatter = -1;
static int64_t sNextChatterUs;
static const char *sChatterFiles[] = {
    "!/jimmie-title/title_whats_happening.ogg",
    "!/jimmie-title/title_pink_bitch_insurance.ogg",
};
#define TITLE_MUSIC_VOLUME 0.60f
#define TITLE_MUSIC_DUCK_VOLUME 0.18f

/* Honor the user’s focus-mute setting without changing gameplay audio. */
static bool title_focus_unavailable(void) {
    return configMuteFocusLoss && (!gWindowApi || !gWindowApi->has_focus);
}
static bool title_focus_muted(void) {
    return configMuteFocusLoss && (title_focus_unavailable() || !gWindowApi->has_focus());
}

/* The title screen plays the game's own title music from the player's ROM. */
static s32 title_music_start(void) {
    return 0;
}

/* Called at the original SET_MENU_MUSIC point, before the reveal transition.
 * The vanilla title sequence is always used. */
s32 jimmie_title_music_init(UNUSED s16 arg, UNUSED s32 unused) {
    if (!jimmie_title_active() || !title_music_start()) {
        set_background_music(0, SEQ_MENU_TITLE_SCREEN, 0);
    } else {
        set_background_music(0, SEQ_SOUND_PLAYER, 0);
    }
    return 1;
}

static void title_chatter_update(void) {
    if (!sChatterActive || sChatterAttempts >= 2) return;
    if (title_focus_unavailable()) { sChatterActive = false; return; }
    if (title_focus_muted()) return;
    if (sGreeting && sGreeting->loaded && ma_sound_is_playing(&sGreeting->sound)) return;
    int64_t now = jrc_monotonic_us();
    if (now < 0) { sChatterActive = false; return; }
    if (!sNextChatterUs) {
        const int64_t gap = sChatterAttempts == 0 ? 3000000 : 12000000;
        if (now > INT64_MAX - gap) { sChatterActive = false; return; }
        sNextChatterUs = now + gap;
        return;
    }
    if (now < sNextChatterUs) return;
    unsigned choice = sLastChatter < 0 ? (unsigned)((uint64_t)now % 2) : (unsigned)(1 - sLastChatter);
    sLastChatter = (int)choice;
    sChatterAttempts++;
    sNextChatterUs = 0;
    char path[SYS_MAX_PATH];
    fs_convert_path(path, sizeof(path), sChatterFiles[choice]);
    sGreeting = audio_sample_load_native_title(path);
    if (!sGreeting) { jimmie_head_trace("title_chatter_load_failed"); return; }
    if (sMusic && sMusic->loaded) audio_stream_set_volume(sMusic, title_focus_muted() ? 0.0f : TITLE_MUSIC_DUCK_VOLUME);
    Vec3f origin = {0, 0, 0};
    audio_sample_play(sGreeting, origin, 1.0f);
    jimmie_head_trace(ma_sound_is_playing(&sGreeting->sound) ? "title_chatter_started" : "title_chatter_play_failed");
}

void jimmie_title_audio_update(void) {
    /* Stop any title voice immediately on the next frame after focus loss. */
    if (title_focus_muted() && sGreeting && sGreeting->loaded && ma_sound_is_playing(&sGreeting->sound))
        audio_sample_stop(sGreeting);
    title_chatter_update(); /* Voice scheduling must not depend on music availability. */
    if (!sMusic || !sMusic->loaded) return;
    f32 target = title_focus_muted() ? 0.0f :
        (sGreeting && sGreeting->loaded && ma_sound_is_playing(&sGreeting->sound)
        ? TITLE_MUSIC_DUCK_VOLUME : TITLE_MUSIC_VOLUME);
    f32 volume = audio_stream_get_volume(sMusic);
    if (volume < target) {
        volume += 0.015f; /* gentle release over about one second at 30 Hz */
        if (volume > target) volume = target;
    } else if (volume > target) {
        volume = target; /* protect the first spoken syllable immediately */
    }
    if (volume != audio_stream_get_volume(sMusic)) audio_stream_set_volume(sMusic, volume);
}

void jimmie_title_greet(void) {
    if (title_focus_unavailable()) { jimmie_head_trace("title_focus_unavailable"); return; }
    if (sChatterActive) return;
    sChatterActive = true;
    sChatterAttempts = 0;
    sLastChatter = -1;
    sNextChatterUs = 0;
    char relative[96], path[SYS_MAX_PATH];
    int64_t tick = jrc_monotonic_us();
    unsigned choice = tick < 0 ? 0 : (unsigned)((uint64_t)tick % 3);
    snprintf(relative, sizeof(relative), "!/jimmie-title/title_good_morning_%02u.ogg", choice + 1);
    fs_convert_path(path, sizeof(path), relative);
    sGreeting = audio_sample_load_native_title(path);
    if (!sGreeting) {
        jimmie_head_trace("title_greeting_load_failed");
        return;
    }
    if (sMusic) audio_stream_set_volume(sMusic, title_focus_muted() ? 0.0f : TITLE_MUSIC_DUCK_VOLUME);
    Vec3f origin = {0, 0, 0};
    audio_sample_play(sGreeting, origin, 1.0f);
    jimmie_head_trace(ma_sound_is_playing(&sGreeting->sound) ? "title_greeting_started" : "title_greeting_play_failed");
}

void jimmie_title_stop_greeting(void) {
    if (sGreeting) audio_sample_stop(sGreeting);
    if (sMusic) {
        audio_stream_stop(sMusic);
        jimmie_head_trace("title_music_stopped");
    }
    jimmie_title_audio_forget();
}

/* The shared audio pool owns these objects. Clear borrowed pointers before
 * shutdown or Lua/mod reload frees that pool; never retain stale handles. */
void jimmie_title_audio_forget(void) {
    sChatterActive = false;
    sChatterAttempts = 0;
    sLastChatter = -1;
    sNextChatterUs = 0;
    sGreeting = NULL;
    sMusic = NULL;
}
#endif
