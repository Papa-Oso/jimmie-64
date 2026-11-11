#ifdef JIMMIE_NATIVE_HEAD
#include <string.h>
#include "jimmie_title_pb.h"
#include "pc/jimmie_run_bridge.h"
#include "game/print.h"
#include "pc/update_checker.h"
void jimmie_title_pb_draw(void) {
    char duration[24];
    jimmie_run_best_text(duration, sizeof(duration));
    print_text(180, 40, "16 STAR PB");
    print_text(300 - (s32)strlen(duration) * 12, 20, duration);
    if (gUpdateMessage) {                       // stays on the start screen; nothing is shown once play begins
        print_text(236, 212, "UPDATE");         // top right: clear of the logo, PRESS START and the best time
        print_text(248, 192, "READY");
    }
}
#endif
