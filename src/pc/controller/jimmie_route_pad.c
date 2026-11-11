/* Opt-in controller-input source for a private route test. */
#if defined(JIMMIE_NATIVE_HEAD) && defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "controller_api.h"
#include "game/area.h"
#include "game/camera.h"
#include "game/game_init.h"
#include "game/ingame_menu.h"
#include "game/level_update.h"
#include "game/mario.h"

static HANDLE sRoutePad = INVALID_HANDLE_VALUE;
static int sChecked;
static int sEnabled;
static unsigned long long sPoll;

static void route_pad_connect(void) {
    const char *token = getenv("JIMMIE_ROUTE_PAD_TEST");
    char name[96];
    sChecked = 1;
    if (!token || !*token) return;
    sEnabled = 1;
    if (strlen(token) != 32) {
        fprintf(stderr, "Route controller test: invalid session token\n");
        return;
    }
    for (size_t i = 0; i < 32; i++) {
        if (!isxdigit((unsigned char)token[i])) {
            fprintf(stderr, "Route controller test: invalid session token\n");
            return;
        }
    }
    snprintf(name, sizeof(name), "\\\\.\\pipe\\Jimmie64RoutePad-%s", token);
    sRoutePad = CreateFileA(name, GENERIC_READ | GENERIC_WRITE, 0, NULL,
                            OPEN_EXISTING, 0, NULL);
    if (sRoutePad == INVALID_HANDLE_VALUE) {
        fprintf(stderr, "Route controller test: controller connection failed (%lu)\n", GetLastError());
    }
}

/* The test can change only the controller values read by the game. */
int jimmie_route_pad_read(OSContPad *pad) {
    char state[512];
    unsigned char input[4];
    DWORD written = 0, received = 0;
    if (!sChecked) route_pad_connect();
    if (!sEnabled) return 0;
    if (sRoutePad == INVALID_HANDLE_VALUE) return 1;

    const struct MarioState *m = &gMarioStates[0];
    int present = m->marioObj != NULL && gCurrLevelNum > 0;
    int size = snprintf(state, sizeof(state),
        "{\"poll\":%llu,\"frame\":%u,\"level\":%d,\"area\":%d,\"course\":%d,\"act\":%d,"
        "\"slot\":%d,\"present\":%d,\"dialog\":%d,\"action\":%u,\"stars\":%u,"
        "\"x\":%.4f,\"y\":%.4f,\"z\":%.4f,\"speed\":%.4f,\"vy\":%.4f,"
        "\"facing\":%d,\"camera\":%d}",
        sPoll++, gGlobalTimer, gCurrLevelNum, gCurrAreaIndex, gCurrCourseNum, gCurrActNum,
        gCurrSaveFileNum, present, get_dialog_id(), present ? m->action : 0,
        present ? m->numStars : 0, present ? m->pos[0] : 0.0f, present ? m->pos[1] : 0.0f,
        present ? m->pos[2] : 0.0f, present ? m->forwardVel : 0.0f, present ? m->vel[1] : 0.0f,
        present ? m->faceAngle[1] : 0, gLakituState.yaw);
    if (size <= 0 || size >= (int)sizeof(state)
            || !WriteFile(sRoutePad, state, (DWORD)size, &written, NULL) || written != (DWORD)size
            || !ReadFile(sRoutePad, input, sizeof(input), &received, NULL) || received != sizeof(input)) {
        fprintf(stderr, "Route controller test: connection closed\n");
        CloseHandle(sRoutePad);
        sRoutePad = INVALID_HANDLE_VALUE;
        return 1;
    }
    pad->button = ((u16)input[0] << 8) | input[1];
    pad->stick_x = (s8)input[2];
    pad->stick_y = (s8)input[3];
    return 1;
}
#endif
