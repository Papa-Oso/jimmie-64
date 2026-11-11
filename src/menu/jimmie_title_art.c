#ifdef JIMMIE_NATIVE_HEAD
#include <ultra64.h>
#include "sm64.h"
#include "types.h"
#include <stdlib.h>
#include "game/segment2.h"
#include "jimmie_title_art.h"
#include "generated/jimmie_title_art.inc.h"
s32 jimmie_title_active(void) {
    const char *flag=getenv("JIMMIE_NATIVE_HEAD");
    return flag && flag[0]=='1' && flag[1]=='\0';
}
Gfx *jimmie_title_backdrop(void) { return (Gfx *)sJimmieTitleBackdrop; }
#endif
