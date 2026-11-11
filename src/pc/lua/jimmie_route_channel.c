/* Windows-only local, one-request mailbox for the opt-in Jimmie companion. */
#if defined(JIMMIE_NATIVE_HEAD) && defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <lua.h>
#include <lauxlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc/jimmie_run_clock.h"

extern unsigned int jimmie_route_file_epoch(void);
extern void smlua_bind_function(lua_State *, const char *, void *);

enum { PAYLOAD_SIZE = 4088, MAX_TICKET = 0x1fffffff };
typedef struct {
    volatile LONG ticket;
    volatile LONG response;
    char payload[PAYLOAD_SIZE];
} RouteMailbox;
_Static_assert(sizeof(RouteMailbox) == 4096, "route mailbox ABI");

static RouteMailbox *mailbox(void) {
    static RouteMailbox *mapped;
    static int opened;
    if (opened) return mapped;
    opened = 1;
    const char *id = getenv("JIMMIE_ROUTE_CHANNEL");
    if (!id || strlen(id) != 32 || strspn(id, "0123456789abcdef") != 32) return NULL;
    char name[80];
    snprintf(name, sizeof(name), "Local\\Jimmie64RouteV1_%s", id);
    HANDLE mapping = OpenFileMappingA(FILE_MAP_READ | FILE_MAP_WRITE, FALSE, name);
    if (mapping) {
        mapped = MapViewOfFile(mapping, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, sizeof(RouteMailbox));
        CloseHandle(mapping);
    }
    return mapped;
}

static int enabled(lua_State *L) {
    lua_pushboolean(L, mailbox() != NULL);
    return 1;
}

static int identity(lua_State *L) {
    lua_pushinteger(L, jimmie_route_file_epoch());
    return 1;
}

static int now_ms(lua_State *L) {
    lua_pushnumber(L, (lua_Number)jrc_monotonic_us()/1000.0);
    return 1;
}

static int offer(lua_State *L) {
    RouteMailbox *m = mailbox();
    lua_Integer ticket = luaL_checkinteger(L, 1);
    size_t bytes = 0;
    const char *payload = luaL_checklstring(L, 2, &bytes);
    if (!m || ticket < 1 || ticket > MAX_TICKET || bytes == 0 || bytes >= PAYLOAD_SIZE) {
        lua_pushboolean(L, 0);
        return 1;
    }
    InterlockedExchange(&m->ticket, 0);
    memcpy(m->payload, payload, bytes);
    m->payload[bytes] = 0;
    InterlockedExchange(&m->ticket, (LONG)ticket);
    lua_pushboolean(L, 1);
    return 1;
}

static int reply(lua_State *L) {
    RouteMailbox *m = mailbox();
    lua_Integer ticket = luaL_checkinteger(L, 1);
    LONG response = m ? InterlockedCompareExchange(&m->response, 0, 0) : 0;
    if (ticket > 0 && ticket <= MAX_TICKET && ((unsigned long)response >> 1) == (unsigned long)ticket)
        lua_pushstring(L, (response & 1) ? "A" : "S");
    else lua_pushnil(L);
    return 1;
}

/* The run clock, read-only: phase, milliseconds so far, best milliseconds, stars, why not timed. */
extern int jimmie_run_phase(void);
extern uint64_t jimmie_run_elapsed_us(void);
extern uint64_t jimmie_run_best_us(void);
extern int jimmie_run_stars(void);
extern uint64_t jimmie_run_split_us(int star);
extern const char *jimmie_run_reason(void);

static int run_state(lua_State *L) {
    lua_pushinteger(L, jimmie_run_phase());
    lua_pushnumber(L, (lua_Number)jimmie_run_elapsed_us() / 1000.0);
    lua_pushnumber(L, (lua_Number)jimmie_run_best_us() / 1000.0);
    lua_pushinteger(L, jimmie_run_stars());
    lua_pushstring(L, jimmie_run_reason());
    return 5;
}

static int run_split(lua_State *L) {
    lua_pushnumber(L, (lua_Number)jimmie_run_split_us((int)luaL_checkinteger(L, 1)) / 1000.0);
    return 1;
}

void jimmie_route_bind(lua_State *L) {
    smlua_bind_function(L, "jimmie_run_state", run_state);
    smlua_bind_function(L, "jimmie_run_split", run_split);
    smlua_bind_function(L, "jimmie_route_enabled", enabled);
    smlua_bind_function(L, "jimmie_route_file_epoch", identity);
    smlua_bind_function(L, "jimmie_route_now_ms", now_ms);
    smlua_bind_function(L, "jimmie_route_offer", offer);
    smlua_bind_function(L, "jimmie_route_reply", reply);
}
#endif
