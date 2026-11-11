#ifndef JIMMIE_TITLE_ART_H
#define JIMMIE_TITLE_ART_H
#include <ultra64.h>
#ifdef JIMMIE_NATIVE_HEAD
s32 jimmie_title_active(void);
Gfx *jimmie_title_backdrop(void);
s32 jimmie_title_music_init(s16 arg, s32 unused);
void jimmie_title_audio_update(void);
void jimmie_title_audio_forget(void);
void jimmie_title_greet(void);
void jimmie_title_stop_greeting(void);
#else
#define jimmie_title_active() 0
#define jimmie_title_greet() ((void)0)
#define jimmie_title_stop_greeting() ((void)0)
#endif
#endif
