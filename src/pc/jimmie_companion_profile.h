#ifndef JIMMIE_COMPANION_PROFILE_H
#define JIMMIE_COMPANION_PROFILE_H
#include <stdbool.h>
struct Mod;
struct ModFile;
#ifdef JIMMIE_NATIVE_HEAD
bool jimmie_companion_profile_ok(void);
void jimmie_companion_before_reload(struct Mod *, struct ModFile *);
#else
#define jimmie_companion_before_reload(mod, file) ((void)0)
#endif
#endif
