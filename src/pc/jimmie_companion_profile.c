#ifdef JIMMIE_NATIVE_HEAD
#include "jimmie_companion_profile.h"
#include "jimmie_run_bridge.h"
#include "mods/mods.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

struct JimmieProfileFile { const char *path; unsigned char md5[16]; int dynamic; };
#include "generated/jimmie_companion_profile.inc.h"
#include "generated/jimmie_text_profile.inc.h"
static struct Mod *sVerifiedMod;
static struct ModFile *sVerifiedFiles;
static struct Mod *sVerifiedTextMod;
static bool sRejected;
static bool reject_profile(const char *reason, const char *file) {
    if (getenv("JIMMIE_HEAD_TRACE")) fprintf(stderr, "Jimmie PB profile rejected: %s (%s)\n", reason, file ? file : "");
    return false;
}

/* The two generated mailboxes contain flat literal data, never expressions.
 * Validate without executing Lua, before initial eligibility or a hot reload.
 * This is a personal-practice guard against accidental code/config changes. */
static void space(const char **p) { while (isspace((unsigned char)**p)) ++*p; }
static bool token(const char **p, const char *s) {
    space(p); size_t n = strlen(s);
    if (strncmp(*p, s, n)) return false;
    *p += n; return true;
}
static bool value(const char **p) {
    space(p);
    if (**p == '"') {
        ++*p;
        while (**p && **p != '"') {
            if ((unsigned char)**p < 32) return false;
            if (**p == '\\') { ++*p; if (!**p || (unsigned char)**p < 32) return false; }
            ++*p;
        }
        if (**p != '"') return false;
        ++*p; return true;
    }
    if (isdigit((unsigned char)**p)) {
        while (isdigit((unsigned char)**p)) ++*p;
        return true;
    }
    return token(p, "nil") || token(p, "true") || token(p, "false");
}
static bool table(const char **p) {
    if (!token(p, "{")) return false;
    space(p);
    if (**p == '}') { ++*p; return true; }
    for (int fields = 0; fields < 24; ++fields) {
        space(p);
        if (!isalpha((unsigned char)**p) && **p != '_') return false;
        do { ++*p; } while (isalnum((unsigned char)**p) || **p == '_');
        if (!token(p, "=") || !value(p)) return false;
        space(p);
        if (**p == '}') { ++*p; return true; }
        if (!token(p, ",")) return false;
    }
    return false;
}
static bool literal_data(const char *path, int kind) {
    if (!path) return false;
    char data[4096]; FILE *f = fopen(path, "rb");
    if (!f) return false;
    size_t n = fread(data, 1, sizeof(data)-1, f);
    bool complete = !ferror(f) && feof(f); fclose(f);
    if (!complete || memchr(data, 0, n)) return false;
    data[n] = 0; const char *p = data;
    const char *owner = kind == 1 ? "-- JIMMIE_DIRECTOR_V1: generated local AI mailbox; no manual commands."
        : "-- JIMMIE_ROUTE_LAUNCH_PROFILE_V1: generated launch capability check";
    if (!token(&p, owner) || (*p != '\n' && *p != '\r')) return false;
    if (kind == 1) {
        if (!token(&p, "PENDING_DIRECTOR") || !token(&p, "=")) return false;
        space(&p);
        if (*p == '{') { if (!table(&p)) return false; }
        else if (!token(&p, "nil")) return false;
        if (!token(&p, "return") || !token(&p, "{") || !token(&p, "}")) return false;
    } else if (!token(&p, "return") || !table(&p)) return false;
    space(&p); return !*p;
}

static bool same_path(const char *a, const char *b) {
    while (*a && *b) {
        char ca = *a++ == '\\' ? '/' : a[-1];
        char cb = *b++ == '\\' ? '/' : b[-1];
        if (ca != cb) return false;
    }
    return !*a && !*b;
}

static bool verify_files(struct Mod *mod, const struct JimmieProfileFile *pins, size_t count) {
    if (mod->fileCount != count || !mod->files) {
        if (getenv("JIMMIE_HEAD_TRACE")) fprintf(stderr, "Jimmie PB profile: path=%s directory=%d files=%u expected=%zu\n", mod->relativePath, mod->isDirectory, mod->fileCount, count);
        return false;
    }
    if (pins == sProfileFiles && mod == sVerifiedMod && mod->files == sVerifiedFiles) return true;
    for (size_t i = 0; i < count; ++i) {
        const struct JimmieProfileFile *pin = &pins[i];
        struct ModFile *file = &mod->files[i];
        if (!same_path(file->relativePath, pin->path)) return reject_profile("file order/name", file->relativePath);
        if (pin->dynamic) { if (!literal_data(file->cachedPath, pin->dynamic)) return reject_profile("literal data", file->relativePath); }
        else if (memcmp(file->dataHash, pin->md5, 16)) return reject_profile("content hash", file->relativePath);
    }
    return true;
}

bool jimmie_companion_profile_ok(void) {
    if (sRejected || gActiveMods.entryCount > 2) return false;
    if (gActiveMods.entryCount && !gActiveMods.entries) return false;
    bool companion = false, text = false;
    for (size_t i = 0; i < gActiveMods.entryCount; ++i) {
        struct Mod *mod = gActiveMods.entries[i];
        if (!mod || !mod->isDirectory) return false;
        if (!strcmp(mod->relativePath, "jimmie")) {
            if (companion) return false;
            companion = true;
            if (!verify_files(mod, sProfileFiles, sizeof(sProfileFiles)/sizeof(sProfileFiles[0]))) return false;
            if (!sVerifiedMod && getenv("JIMMIE_HEAD_TRACE"))
                fprintf(stderr, "Jimmie PB profile verified: %u original candidate files\n", mod->fileCount);
            sVerifiedMod = mod; sVerifiedFiles = mod->files;
        } else if (!strcmp(mod->relativePath, "jimmie_text")) {
            if (text) return false;
            text = true;
            if (!verify_files(mod, sTextProfileFiles, sizeof(sTextProfileFiles)/sizeof(sTextProfileFiles[0]))) return false;
            sVerifiedTextMod = mod;
        } else return false;
    }
    /* Removing an already-verified mod cannot turn a running attempt into a
     * different allowed profile. Static hot reloads also remain disqualifying. */
    return (!sVerifiedMod || companion) && (!sVerifiedTextMod || text);
}

void jimmie_companion_before_reload(struct Mod *mod, struct ModFile *file) {
    bool allowed = false;
    if (mod == sVerifiedMod && file) {
        int kind = !strcmp(file->relativePath, "director_relay.lua") ? 1
            : !strcmp(file->relativePath, "route_launch_profile.lua") ? 2 : 0;
        allowed = kind && literal_data(file->cachedPath, kind);
    }
    if (!allowed) { sRejected = true; jimmie_run_disqualify(); }
}
#endif
