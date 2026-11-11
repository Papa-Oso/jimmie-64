#ifndef JIMMIE_HEAD_H
#define JIMMIE_HEAD_H
#include "gd_types.h"
#ifdef JIMMIE_NATIVE_HEAD
const u8 *jimmie_head_texture(const void *address);
void jimmie_head_trace(const char *event);
u32 jimmie_head_frame(void);
void jimmie_head_init(struct ObjAnimator *animator, struct ObjGroup *grabbers, struct ObjCamera *camera);
void jimmie_head_test_pad(OSContPad *pad, struct ObjView *view);
void jimmie_head_capture_eye_offset(struct GdObj *net, struct GdVec3f *offset);
void jimmie_head_reset(void);
void jimmie_head_capture_bind(struct ObjJoint *joint);
s32 jimmie_head_draw(struct ObjShape *shape);
#else
#define jimmie_head_trace(event) ((void)0)
#define jimmie_head_frame() 0
#define jimmie_head_init(animator, grabbers, camera) ((void)0)
#define jimmie_head_test_pad(pad, view) ((void)0)
#define jimmie_head_capture_eye_offset(net, offset) ((void)0)
#define jimmie_head_reset() ((void)0)
#define jimmie_head_capture_bind(joint) ((void)0)
#define jimmie_head_draw(shape) 0
#endif
#endif
