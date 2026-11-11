#ifndef JIMMIE_RUN_BRIDGE_H
#define JIMMIE_RUN_BRIDGE_H
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
struct MarioState;
struct Object;
#ifdef JIMMIE_NATIVE_HEAD
void jimmie_run_boot(void);
void jimmie_run_load(void);
void jimmie_run_begin_file(void);
void jimmie_run_update(void);
void jimmie_run_disqualify(void);
void jimmie_run_collection(struct MarioState *, struct Object *, struct Object *);
void jimmie_run_puff_emitted(struct Object *);
void jimmie_run_best_text(char *, size_t);
#else
#define jimmie_run_boot() ((void)0)
#define jimmie_run_load() ((void)0)
#define jimmie_run_begin_file() ((void)0)
#define jimmie_run_update() ((void)0)
#define jimmie_run_disqualify() ((void)0)
#define jimmie_run_collection(m, star, puff) ((void)0)
#define jimmie_run_puff_emitted(puff) ((void)0)
#endif
#ifdef __cplusplus
}
#endif
#endif
