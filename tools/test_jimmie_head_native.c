/* Native source tests. Rendering/audio/object lookup are stubs; the rig math,
 * Goddard spring, eye behavior and matrix functions are the actual sources. */
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include <time.h>
#include <math.h>
#include <stdlib.h>
#include "goddard/gd_main.h"
#undef printf
#include "goddard/joints.h"
#include "goddard/objects.h"
#include "goddard/sfx.h"
#include "../src/goddard/jimmie_head.c"

struct GdControl gGdCtrl;
struct ObjCamera *sCurrentMoveCamera;
struct ObjView *sCurrentMoveView;
s32 gGdFrameBufNum;
static struct ObjJoint sJoint[JH_DRIVER_COUNT], sAttached;
static struct ObjShape sFace;
static struct GdObj *sCurrent;
static int sSubmitted;
void gd_dl_external(Gfx *dl) { assert(dl); sSubmitted++; }
struct GdObj *d_use_obj(DynObjName name) { (void)name; return NULL; }
void grabbable_joint_update_func(struct ObjJoint *joint);
void set_cur_dynobj(struct GdObj *obj) { sCurrent=obj; }
Mat4f *d_get_matrix_ptr(void) { return &((struct ObjJoint *)sCurrent)->matE8; }
Mat4f *d_get_rot_mtx_ptr(void) { return &((struct ObjJoint *)sCurrent)->mat128; }
void gd_play_sfx(enum GdSfx sfx) { (void)sfx; }
f64 gd_sqrt_d(f64 x) { return sqrt(x); }
f64 gd_sin_d(f64 x) { return sin(x); }
f64 gd_cos_d(f64 x) { return cos(x); }
void fatal_print(const char *s) { fprintf(stderr,"%s",s); abort(); }
void fatal_printf(const char *s,...) { (void)s; abort(); }
void imin(const char *s) { (void)s; }
void imout(void) {}
void gd_printf(const char *s,...) { (void)s; }
void world_pos_to_screen_coords(struct GdVec3f *v,struct ObjCamera *c,struct ObjView *w) {
    (void)c;(void)w; v->x=160;v->y=120;v->z=0;
}
static void setup_rig(void) {
    jimmie_head_reset();sEnabled=1;sShapes[0]=&sFace;
    for(int j=0;j<JH_DRIVER_COUNT;j++) {
        sDrivers[j]=&sJoint[j];gd_set_identity_mat4(&sJoint[j].matE8);gd_set_identity_mat4(&sJoint[j].mat168);
        sJoint[j].matE8[3][0]=(float)(j*7);
        jimmie_head_capture_bind(&sJoint[j]);
    }
}
int main(void) {
    int checks=0;
    jimmie_head_reset();assert(!jimmie_head_draw(&sFace));checks++;
    setup_rig();sBound[0]=0;assert(!jimmie_head_draw(&sFace));checks++;
    setup_rig();assert(jimmie_head_draw(&sFace));checks++;
    for(int i=0;i<JH_VERTEX_COUNT;i++) {
        const struct JhBindVertex *v=&sJhBind[i];float sum=0;
        for(int k=0;k<4;k++){assert(v->joints[k]<JH_DRIVER_COUNT);assert(v->weights[k]>=0);sum+=v->weights[k];}
        assert(sum<=1.00001f);
        assert(fabsf(sDeformed[i].x-v->position[0])<.02f);
        assert(fabsf(sDeformed[i].y-v->position[1])<.02f);
        assert(fabsf(sDeformed[i].z-v->position[2])<.02f);
    }
    checks++;
    /* Actual full atlas includes the approved grin and exact neutral eyes. */
    assert(JH_VERTEX_COUNT==JH_SOURCE_VERTEX_COUNT);
    assert(sizeof(sJhTexture)==64*64*4);
    assert(memcmp(sFaceTexture[gGdFrameBufNum],sJhTexture,sizeof(sJhTexture))==0);
    assert(jimmie_head_texture(sFaceTexture[0])==sFaceTexture[0]);
    assert(jimmie_head_texture(sJhTexture)==NULL);checks++;
    struct ObjNet testEye={0};sEyeNets[0]=&testEye;
    struct GdVec3f testOffset={30,0,0};
    jimmie_head_capture_eye_offset(&testEye.header,&testOffset);
    assert(jimmie_head_draw(&sFace));
    assert(memcmp(sFaceTexture[gGdFrameBufNum],sJhTexture,sizeof(sJhTexture))!=0);
    assert(memcmp(sFaceTexture[gGdFrameBufNum]+40*64*4,sJhTexture+40*64*4,24*64*4)==0);
    u8 previous[64*64*4];memcpy(previous,sFaceTexture[gGdFrameBufNum],sizeof(previous));
    testOffset.x=-30;jimmie_head_capture_eye_offset(&testEye.header,&testOffset);
    assert(jimmie_head_draw(&sFace));
    assert(memcmp(previous,sFaceTexture[gGdFrameBufNum],sizeof(previous))!=0);checks++;
    setup_rig();int lid=-1,eye=-1;
    for(int j=0;j<JH_DRIVER_COUNT;j++) {
        if(sJhDriverIds[j]==206)lid=j;
        if(sJhDriverIds[j]==106)eye=j;
    }
    assert(lid>=0 && eye>=0);
    sJoint[lid].matE8[3][1]+=400;sJoint[lid].mat168[3][1]+=400;
    assert(fabsf(jh_lid_opening(0)-1)<.0001f);
    assert(jimmie_head_draw(&sFace));
    assert(memcmp(sFaceTexture[gGdFrameBufNum],sJhTexture,sizeof(sJhTexture))==0);checks++;
    struct GdVec3f closed={0,0,34};gd_rot_mat_about_vec(&sJoint[lid].mat168,&closed);
    assert(jh_lid_opening(0)<.001f);assert(jimmie_head_draw(&sFace));
    assert(memcmp(sFaceTexture[gGdFrameBufNum],sJhTexture,sizeof(sJhTexture))!=0);
    assert(memcmp(sFaceTexture[gGdFrameBufNum]+40*64*4,sJhTexture+40*64*4,24*64*4)==0);checks++;
    setup_rig();struct GdVec3f eyeTurn={0,0,5};gd_rot_mat_about_vec(&sJoint[eye].mat168,&eyeTurn);
    struct GdVec3f animated=jh_animated_eye_offset(0);
    assert(fabsf(animated.x)+fabsf(animated.y)>.01f);
    assert(jimmie_head_draw(&sFace));assert(memcmp(sFaceTexture[gGdFrameBufNum],sJhTexture,sizeof(sJhTexture))!=0);checks++;
    setup_rig();
    int nose=-1;for(int j=0;j<JH_DRIVER_COUNT;j++)if(sJhDriverIds[j]==185)nose=j;
    assert(nose>=0);sJoint[nose].matE8[3][0]+=120;
    assert(jimmie_head_draw(&sFace));int changed=0;
    for(int i=0;i<JH_VERTEX_COUNT;i++) {
        float weight=0;for(int k=0;k<4;k++)if(sJhBind[i].joints[k]==nose)weight+=sJhBind[i].weights[k];
        assert(fabsf(sDeformed[i].x-sJhBind[i].position[0]-120*weight)<.03f);
        changed+=weight>.5f;
    }
    assert(changed>10);checks++;
    gGdFrameBufNum=1;assert(jimmie_head_draw(&sFace));
    assert(sVertices[0]!=sVertices[1]);checks++;
    setup_rig();sJoint[nose].matE8[3][0]=NAN;assert(!jimmie_head_draw(&sFace));checks++;
    setup_rig();clock_t begin=clock();for(int i=0;i<10000;i++){gGdFrameBufNum=i&1;assert(jimmie_head_draw(&sFace));}
    double us=1e6*(clock()-begin)/CLOCKS_PER_SEC/10000;checks++;
    /* Actual upstream spring: seven handles, repeated drag/freeze/release. */
    struct ObjJoint grab={0};struct ObjGroup group={0};struct ListNode node={0};
    node.obj=&sAttached.header;group.firstMember=&node;grab.attachedObjsGrp=&group;
    for(int handle=0;handle<7;handle++)for(int cycle=0;cycle<20;cycle++) {
        gd_set_identity_mat4(&grab.mat128);grab.mat128[3][0]=300+handle*10;
        grab.velocity=(struct GdVec3f){0,0,0};grab.header.drawFlags=OBJ_PICKED;gGdCtrl.trgR=0;
        gd_set_identity_mat4(&sAttached.matE8);grabbable_joint_update_func(&grab);
        assert(fabsf(grab.mat128[3][0]-(300+handle*10)*.75f)<.001f);
        grab.header.drawFlags=0;gGdCtrl.trgR=1;float held=grab.mat128[3][0];
        for(int frame=0;frame<30;frame++){gd_set_identity_mat4(&sAttached.matE8);grabbable_joint_update_func(&grab);}
        assert(grab.mat128[3][0]==held);gGdCtrl.trgR=0;
        for(int frame=0;frame<150;frame++){gd_set_identity_mat4(&sAttached.matE8);grabbable_joint_update_func(&grab);}
        assert(fabsf(grab.mat128[3][0])<1);assert(grab.velocity.x==0);
    }
    checks+=3;
    struct ObjCamera camera={0};struct ObjView view={0};struct ObjAnimator animator={0};
    sCurrentMoveCamera=&camera;sCurrentMoveView=&view;grab.rootAnimator=&animator;
    gd_set_identity_mat4(&sAttached.mat128);animator.state=2;gGdCtrl.csrX=10000;gGdCtrl.csrY=-10000;
    eye_joint_update_func(&grab);assert(sAttached.mat128[3][0]==0);checks++;
    animator.state=7;eye_joint_update_func(&grab);
    float x=sAttached.mat128[3][0],y=sAttached.mat128[3][1];
    assert(x>0&&y>0);assert(fabsf(sqrtf(x*x+y*y)-30)<.001f);checks++;
    for(int n=0;n<100;n++){setup_rig();assert(jimmie_head_draw(&sFace));jimmie_head_reset();assert(!jimmie_head_draw(&sFace));}
    checks++;
    printf("PASS %d native checks; 140 drag/freeze/release cycles; 100 rig resets; adapter %.2f us/frame (CPU only)\n",checks,us);
    return 0;
}
