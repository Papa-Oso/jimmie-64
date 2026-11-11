/* Opt-in local visual adapter. Goddard owns animation, picking and springs. */
#ifdef JIMMIE_NATIVE_HEAD
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <sys/time.h>
#include "jimmie_head.h"
#include "dynlist_proc.h"
#include "gd_math.h"
#include "renderer.h"
#include "gd_main.h"
#include "objects.h"
#include "draw_objects.h"
struct JhBindVertex {
    f32 position[3]; u8 color[3]; s16 uv[2]; u8 joints[4]; f32 weights[4];
};
#include "generated/jimmie_head_data.inc.h"
static u8 sFaceTexture[2][64 * 64 * 4];
const u8 *jimmie_head_texture(const void *address) {
    return address == sFaceTexture[0] || address == sFaceTexture[1] ? address : NULL;
}
static struct ObjJoint *sDrivers[JH_DRIVER_COUNT];
static Mat4f sInverseBind[JH_DRIVER_COUNT];
static Mat4f sLocalBind[JH_DRIVER_COUNT], sBindParent[JH_DRIVER_COUNT];
static u8 sBound[JH_DRIVER_COUNT];
static struct ObjShape *sShapes[6];
static s32 sEnabled, sListsReady;
static struct ObjAnimator *sAnimator;
static struct ObjJoint *sGrabbers[7];
static struct ObjNet *sEyeNets[2];
static struct GdVec3f sEyeOffsets[2];
static struct ObjCamera *sCamera;
static u32 sTraceFrame;
static struct GdVec3f sDeformed[JH_VERTEX_COUNT];
static Vtx sVertices[2][JH_PACKED_COUNT];
static Gfx sLists[2][JH_TRIANGLE_COUNT * 2 + 128];
u32 jimmie_head_frame(void) { return sTraceFrame; }

/* Explicit local diagnostic only; no file is opened without an opt-in path. */
void jimmie_head_trace(const char *event) {
    const char *path = getenv("JIMMIE_HEAD_TRACE");
    if (!path) return;
    FILE *f = fopen(path, "a");
    if (f) { fprintf(f, "{\"event\":\"%s\"}\n", event); fclose(f); }
}

void jimmie_head_reset(void) {
    sEnabled = sListsReady = 0;
    sAnimator = NULL; sTraceFrame = 0;
    sCamera = NULL;
    memset(sDrivers, 0, sizeof(sDrivers));
    memset(sShapes, 0, sizeof(sShapes));
    memset(sBound, 0, sizeof(sBound));
    memset(sGrabbers, 0, sizeof(sGrabbers));
    memset(sEyeNets, 0, sizeof(sEyeNets));
    memset(sEyeOffsets, 0, sizeof(sEyeOffsets));
}
void jimmie_head_init(struct ObjAnimator *animator, struct ObjGroup *grabbers, struct ObjCamera *camera) {
    static const s32 ids[6] = {225, 100, 116, 59, 93, 25};
    char name[20];
    const char *enabled = getenv("JIMMIE_NATIVE_HEAD");
    jimmie_head_reset();
    if (!enabled || strcmp(enabled, "1") != 0) return;
    for (s32 i = 0; i < JH_DRIVER_COUNT; ++i) {
        snprintf(name, sizeof(name), "N%dl", sJhDriverIds[i]);
        struct GdObj *obj = d_use_obj(name);
        if (!obj || obj->type != OBJ_TYPE_JOINTS) return;
        sDrivers[i] = (struct ObjJoint *) obj;
    }
    for (s32 i = 0; i < 6; ++i) {
        snprintf(name, sizeof(name), "N%dl", ids[i]);
        struct GdObj *obj = d_use_obj(name);
        if (!obj || obj->type != OBJ_TYPE_SHAPES) return;
        sShapes[i] = (struct ObjShape *) obj;
    }
    sEnabled = 1;
    sAnimator = animator;
    sCamera = camera;
    sEyeNets[0] = (struct ObjNet *)d_use_obj("N96l");
    sEyeNets[1] = (struct ObjNet *)d_use_obj("N112l");
    s32 count = 0;
    for (struct ListNode *link = grabbers->firstMember; link && count < 7; link = link->next) {
        if (link->obj->type == OBJ_TYPE_JOINTS && (link->obj->drawFlags & OBJ_IS_GRABBALE))
            sGrabbers[count++] = (struct ObjJoint *)link->obj;
    }
    const char *trace = getenv("JIMMIE_HEAD_TRACE");
    if (trace) {
        FILE *f = fopen(trace, "a");
        if (f) { fprintf(f, "{\"event\":\"loaded\",\"drivers\":%d}\n", JH_DRIVER_COUNT); fclose(f); }
    }
    printf("[jimmie-head] native rig: %d vertices, %d triangles, %d drivers\n",
           JH_VERTEX_COUNT, JH_TRIANGLE_COUNT, JH_DRIVER_COUNT);
}
/* Test inputs go only to this process's Goddard controller buffer. Projection,
 * picking, driver updates, springs and rendering remain the native code. */
void jimmie_head_test_pad(OSContPad *pad, struct ObjView *view) {
    memset(sEyeOffsets, 0, sizeof(sEyeOffsets));
    if (sEnabled && getenv("JIMMIE_SDL_CONTROLLER_TEST") && (pad->button || pad->stick_x)) {
        const char *path = getenv("JIMMIE_HEAD_TRACE");
        FILE *f = path ? fopen(path, "a") : NULL;
        if (f) {
            fprintf(f, "{\"event\":\"goddard_pad\",\"sample\":%u,\"buttons\":%u,\"x\":%d}\n",
                sTraceFrame, pad->button, pad->stick_x);
            fclose(f);
        }
    }
    if (!sEnabled || !getenv("JIMMIE_HEAD_TEST_INTERACTION")) return;
    memset(pad, 0, sizeof(*pad));
    if (sTraceFrame >= 60 && sTraceFrame < 63) pad->button = A_BUTTON;
    if (sTraceFrame < 690 || sTraceFrame >= 1180) return;
    s32 target = (sTraceFrame - 690) / 70, phase = (sTraceFrame - 690) % 70;
    struct ObjJoint *grabber = sGrabbers[target];
    if (!grabber || !sCamera || !view) {
        if (phase == 0) jimmie_head_trace("interaction_fixture_missing_target_or_view");
        return;
    }
    if (phase == 0) {
        struct GdVec3f p = {grabber->mat128[3][0], grabber->mat128[3][1], grabber->mat128[3][2]};
        world_pos_to_screen_coords(&p, sCamera, view);
        gGdCtrl.csrX = p.x; gGdCtrl.csrY = p.y;
    }
    if (phase >= 1 && phase <= 12) pad->button = A_BUTTON;
    if (phase >= 3 && phase <= 12) pad->stick_x = 45;
    if (phase >= 13 && phase <= 20) pad->button = R_TRIG;
    if (phase == 13 || phase == 15 || phase == 21 || phase == 69) {
        const char *path = getenv("JIMMIE_HEAD_TRACE");
        FILE *f = path ? fopen(path, "a") : NULL;
        if (f) {
            fprintf(f, "{\"event\":\"interaction\",\"target\":%d,\"phase\":%d,\"picked\":%d,\"dx\":%.3f,\"dy\":%.3f,\"dz\":%.3f,\"eye_net_x\":%.3f,\"eye_joint_x\":%.3f}\n",
                    target, phase, !!(grabber->header.drawFlags & OBJ_PICKED),
                    grabber->mat128[3][0]-grabber->initPos.x,
                    grabber->mat128[3][1]-grabber->initPos.y,
                    grabber->mat128[3][2]-grabber->initPos.z,
                    sEyeNets[0]->mat168[3][0], sDrivers[2]->matE8[3][0]);
            fclose(f);
        }
    }
}
void jimmie_head_capture_eye_offset(struct GdObj *net, struct GdVec3f *offset) {
    for (s32 eye = 0; eye < 2; ++eye)
        if (net == (struct GdObj *)sEyeNets[eye]) sEyeOffsets[eye] = *offset;
}
/* Capture during the actual native bind pass, before opening/grab animation. */
void jimmie_head_capture_bind(struct ObjJoint *joint) {
    if (!sEnabled) return;
    for (s32 i = 0; i < JH_DRIVER_COUNT; ++i) if (joint == sDrivers[i]) {
        gd_inverse_mat4f(&joint->matE8, &sInverseBind[i]);
        gd_copy_mat4f(&joint->mat168, &sLocalBind[i]);
        Mat4f inverseLocal;
        gd_inverse_mat4f(&joint->mat168, &inverseLocal);
        gd_mult_mat4f(&inverseLocal, &joint->matE8, &sBindParent[i]);
        sBound[i] = 1;
    }
}

/* Sample the approved face in its own UV space. The native eye offsets and
 * original lid joints drive this small derived texture; source art stays intact. */
static float jh_sample(const u8 *pixels, s32 channels, float x, float y, s32 c) {
    x=fmaxf(0, fminf(63, x)); y=fmaxf(0, fminf(63, y));
    s32 x0=(s32)x, y0=(s32)y, x1=x0<63?x0+1:63, y1=y0<63?y0+1:63;
    float dx=x-x0, dy=y-y0;
    return (1-dy)*((1-dx)*pixels[(y0*64+x0)*channels+c]+dx*pixels[(y0*64+x1)*channels+c])
         + dy*((1-dx)*pixels[(y1*64+x0)*channels+c]+dx*pixels[(y1*64+x1)*channels+c]);
}
static float jh_lid_opening(s32 side) {
    s32 target=side?215:206;
    for(s32 j=0;j<JH_DRIVER_COUNT;j++) if(sJhDriverIds[j]==target) {
        /* ROM animations rotate the local lid about Z, ~162..198 degrees.
         * Local angle ignores head pose and cap-grab translation. The engine
         * overrides atan2f with SM64 swapped-axis semantics; use libc atan2. */
        float before=(float)atan2((double)sLocalBind[j][0][1],(double)sLocalBind[j][0][0]);
        float current=(float)atan2((double)sDrivers[j]->mat168[0][1],(double)sDrivers[j]->mat168[0][0]);
        float delta=remainderf(current-before,6.283185307f)*57.29577951f;
        const char *trace=getenv("JIMMIE_HEAD_TRACE");
        if(trace && sTraceFrame%30==1) {
            FILE *f=fopen(trace,"a");
            if(f) { fprintf(f,"{\"event\":\"lid_local\",\"sample\":%u,\"side\":%d,\"before\":%.4f,\"current\":%.4f,\"delta\":%.4f}\n",sTraceFrame,side,before*57.29577951f,current*57.29577951f,delta);fclose(f); }
        }

        float value=1.0f-delta/34.0f;
        return isfinite(value)?fmaxf(0,fminf(1.5f,value)):1.0f;
    }
    return 1.0f;
}
static struct GdVec3f jh_animated_eye_offset(s32 side) {
    struct GdVec3f result={0,0,0};
    s32 target=side?122:106;
    for(s32 j=0;j<JH_DRIVER_COUNT;j++) if(sJhDriverIds[j]==target) {
        /* Compare the same original eye-axis point in local animation space,
         * then orient that delta through the captured parent. No translation
         * from the head or native grabbers becomes spurious eye movement. */
        struct GdVec3f before={300,0,0}, current=before;
        gd_mat4f_mult_vec3f(&before,&sLocalBind[j]);
        gd_mat4f_mult_vec3f(&current,&sDrivers[j]->mat168);
        result=(struct GdVec3f){current.x-before.x,current.y-before.y,current.z-before.z};
        gd_mat4f_mult_vec3f(&result,&sBindParent[j]);
    }
    if(!isfinite(result.x)||!isfinite(result.y)||!isfinite(result.z))
        return (struct GdVec3f){0,0,0};
    return result;
}
static void jh_update_face_texture(void) {
    u8 *out=sFaceTexture[gGdFrameBufNum];
    memcpy(out,sJhTexture,sizeof(sJhTexture));
    float openings[2];
    for(s32 side=0;side<2;side++) {
        float opening=openings[side]=jh_lid_opening(side);
        struct GdVec3f animated=jh_animated_eye_offset(side);
        float dx=fmaxf(-3,fminf(3,(sEyeOffsets[side].x+animated.x)*.08f));
        float dy=fmaxf(-2,fminf(2,-(sEyeOffsets[side].y+animated.y)*.08f));
        if(fabsf(opening-1)<.0001f && fabsf(dx)<.0001f && fabsf(dy)<.0001f) continue;
        s32 cx=side?43:21;
        for(s32 y=21;y<=38;y++) for(s32 x=cx-9;x<=cx+9;x++) {
            float ex=(x-cx)/8.8f, ey=(y-29.0f)/8.8f;
            if(ex*ex+ey*ey>1) continue;
            float sy=opening>.015f?35.0f+(y-35.0f)/opening:-100.0f;
            float color[3];
            if(sy<20) {
                for(s32 c=0;c<3;c++) color[c]=jh_sample(sJhTexture,4,x,24,c);
            } else {
                for(s32 c=0;c<3;c++) color[c]=jh_sample(sJhEyeBase,4,x,sy,c);
                /* Pupils are clipped to the exposed sclera by its original
                 * lower-half region. Tracking never moves them onto a lid. */
                if(sy>=28 && sy<=35) {
                    float alpha=jh_sample(sJhPupilAlpha,1,x-dx,sy-dy,0)/255.0f;
                    const float pupil[3]={31,23,25};
                    for(s32 c=0;c<3;c++) color[c]=color[c]*(1-alpha)+pupil[c]*alpha;
                }
            }
            if(opening<=.015f && y==35) { color[0]=31;color[1]=23;color[2]=25; }
            for(s32 c=0;c<3;c++) out[(y*64+x)*4+c]=(u8)fmaxf(0,fminf(255,color[c]+.5f));
        }
    }
    const char *path=getenv("JIMMIE_HEAD_TRACE");
    if(path && sTraceFrame%30==1) {
        FILE *f=fopen(path,"a");
        if(f) { fprintf(f,"{\"event\":\"face_pose\",\"sample\":%u,\"open_left\":%.4f,\"open_right\":%.4f,\"eye_x\":%.3f,\"eye_y\":%.3f}\n",
            sTraceFrame,openings[0],openings[1],sEyeOffsets[0].x,sEyeOffsets[0].y);fclose(f); }
    }
}
static void build_lists(void) {
    for (s32 frame = 0; frame < 2; ++frame) {
        Gfx *g = sLists[frame];
        gDPPipeSync(g++);
        gSPClearGeometryMode(g++, G_LIGHTING | G_TEXTURE_GEN | G_TEXTURE_GEN_LINEAR);
        gDPSetCycleType(g++, G_CYC_1CYCLE);
        gDPSetCombineMode(g++, G_CC_SHADE, G_CC_SHADE);
        gSPTexture(g++, 0, 0, 0, G_TX_RENDERTILE, G_OFF);
        for (s32 pass = 0; pass < 2; ++pass) {
            s32 start = pass ? JH_SOLID_TRIANGLES : 0;
            s32 end = pass ? JH_TRIANGLE_COUNT : JH_SOLID_TRIANGLES;
            if (pass) {
                gDPPipeSync(g++);
                gDPSetCombineMode(g++, G_CC_DECALRGBA, G_CC_DECALRGBA);
                gSPTexture(g++, 0xFFFF, 0xFFFF, 0, G_TX_RENDERTILE, G_ON);
                gDPLoadTextureBlock(g++, sFaceTexture[frame], G_IM_FMT_RGBA, G_IM_SIZ_16b, 64, 64,
                                   0, G_TX_CLAMP, G_TX_CLAMP, 6, 6, G_TX_NOLOD, G_TX_NOLOD);
            }
            for (s32 t = start; t < end;) {
                s32 count = end - t < 10 ? end - t : 10;
                gSPVertex(g++, &sVertices[frame][t * 3], count * 3, 0);
                for (s32 j = 0; j < count; ++j) {
                    gSP1Triangle(g++, j * 3, j * 3 + 1, j * 3 + 2, 0);
                }
                t += count;
            }
        }
        gDPPipeSync(g++);
        gSPTexture(g++, 0, 0, 0, G_TX_RENDERTILE, G_OFF);
        gDPSetCombineMode(g++, G_CC_SHADE, G_CC_SHADE);
        gSPSetGeometryMode(g++, G_LIGHTING);
        gSPEndDisplayList(g++);
    }
    sListsReady = 1;
}
s32 jimmie_head_draw(struct ObjShape *shape) {
    if (!sEnabled) return 0;
    if (shape == sShapes[0] && sTraceFrame++ % 30 == 0) {
        const char *trace = getenv("JIMMIE_HEAD_TRACE");
        if (trace) {
            FILE *f = fopen(trace, "a");
            if (f) {
                s32 bound = 0; for (s32 j=0;j<JH_DRIVER_COUNT;j++) bound += sBound[j]!=0;
                struct timeval wall;
                gettimeofday(&wall, NULL);
                fprintf(f, "{\"event\":\"frame\",\"sample\":%u,\"bound\":%d,\"state\":%d,\"anim_frame\":%.1f,\"wall_time\":%.6f}\n",
                        sTraceFrame, bound, sAnimator?sAnimator->state:-1, sAnimator?sAnimator->frame:-1,
                        (double)wall.tv_sec + (double)wall.tv_usec / 1e6);
                fclose(f);
            }
        }
    }
    for (s32 j = 0; j < JH_DRIVER_COUNT; ++j) if (!sBound[j]) return 0;
    if (shape != sShapes[0]) {
        for (s32 i = 1; i < 6; ++i) if (shape == sShapes[i]) return 1;
        return 0;
    }
    if (!sListsReady) build_lists();
    jh_update_face_texture();
    for (s32 i = 0; i < JH_VERTEX_COUNT; ++i) {
        const struct JhBindVertex *v = &sJhBind[i];
        f32 residual = 1.0f;
        struct GdVec3f result = {0, 0, 0};
        for (s32 k = 0; k < 4; ++k) {
            f32 w = v->weights[k];
            if (w <= 0.0f) continue;
            s32 j = v->joints[k];
            struct GdVec3f p = {v->position[0], v->position[1], v->position[2]};
            gd_rotate_and_translate_vec3f(&p, &sInverseBind[j]);
            gd_rotate_and_translate_vec3f(&p, &sDrivers[j]->matE8);
            result.x += p.x*w; result.y += p.y*w; result.z += p.z*w; residual -= w;
        }
        result.x += v->position[0]*residual;
        result.y += v->position[1]*residual;
        result.z += v->position[2]*residual;
        if (!isfinite(result.x) || !isfinite(result.y) || !isfinite(result.z)) return 0;
        sDeformed[i] = result;
    }
    for (s32 i = 0; i < JH_PACKED_COUNT; ++i) {
        s32 id = sJhPacked[i];
        const struct JhBindVertex *b = &sJhBind[id];
        Vtx *v = &sVertices[gGdFrameBufNum][i];
        struct GdVec3f p = sDeformed[id];
        v->v.ob[0] = (s16) fmaxf(-32767, fminf(32767, p.x));
        v->v.ob[1] = (s16) fmaxf(-32767, fminf(32767, p.y));
        v->v.ob[2] = (s16) fmaxf(-32767, fminf(32767, p.z));
        v->v.flag = 0; v->v.tc[0] = b->uv[0]; v->v.tc[1] = b->uv[1];
        memcpy(v->v.cn, b->color, 3); v->v.cn[3] = 255;
    }
    gd_dl_external(sLists[gGdFrameBufNum]);
    return 1;
}
#endif

