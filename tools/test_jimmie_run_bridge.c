/* Actual bridge + engine types. Engine state and time are explicit fixtures.
 * Actual core persistence writes only into the supplied disposable directory. */
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "../src/pc/jimmie_companion_profile.c"
#include "../src/pc/jimmie_run_bridge.c"
#undef main /* Engine platform headers may remap this to SDL_main. */

struct SaveBuffer gSaveBuffer;
u8 gSaveFileUsingBackupSlot;
s8 gDebugLevelSelect;
struct MarioState gMarioStates[MAX_PLAYERS];
struct MarioState *gMarioState = &gMarioStates[0];
struct LevelValues gLevelValues;
struct ServerSettings gServerSettings;
struct NetworkPlayer gNetworkPlayers[MAX_PLAYERS];
struct NetworkPlayer *gNetworkPlayerLocal = &gNetworkPlayers[0];
enum NetworkType gNetworkType;
struct Mods gActiveMods;
s16 gCurrSaveFileNum, gCurrLevelNum;
struct DemoInput *gCurrDemoInput;
struct CreditsEntry *gCurrCreditsEntry;
u32 gGlobalTimer;
const BehaviorScript bhvGrandStar[] = {0};
static int count, passed;
static int64_t now;
static char path[1024];
static struct Object mario, star, puff, unrelated;
int64_t jrc_monotonic_us(void) { return now; }
const char *fs_get_write_path(const char *unused) { (void)unused; return path; }
u8 network_player_connected_count(void) { return 1; }
s32 save_file_get_total_star_count(s32 f,s32 low,s32 high) {(void)f;(void)low;(void)high;return count;}
#define PASS(text) do {printf("PASS %s\n",text);passed++;} while(0)

static void boot(const char *dir, int test) {
    snprintf(path,sizeof(path),"%s/bridge-%d.pb",dir,test);
    memset(&gSaveBuffer,0,sizeof(gSaveBuffer));
    memset(&gServerSettings,0,sizeof(gServerSettings));
    memset(gMarioStates,0,sizeof(gMarioStates));
    memset(&puff,0,sizeof(puff));memset(&star,0,sizeof(star));
    gNetworkType=NT_SERVER;gServerSettings.maxPlayers=1;
    gNetworkPlayerLocal->connected=true;
    gSaveFileUsingBackupSlot=gDebugLevelSelect=0;gActiveMods.entryCount=0;
    gActiveMods.entries=NULL;sVerifiedMod=NULL;sVerifiedFiles=NULL;sVerifiedTextMod=NULL;sRejected=false;
    gCurrSaveFileNum=1;gCurrLevelNum=LEVEL_CASTLE_GROUNDS;
    gLevelValues.entryLevel=LEVEL_CASTLE_GROUNDS;
    gMarioStates[0].marioObj=&mario;count=0;gGlobalTimer=100;now=1000000;
    jimmie_run_boot();jimmie_run_load();now=5000000;
}
static void arm(void) {
    count=16;gCurrLevelNum=LEVEL_BOWSER_3;
    star.behavior=bhvGrandStar;star.oInteractionSubtype=INT_SUBTYPE_GRAND_STAR;
    puff.parentObj=&mario;now=1001000000;
    jimmie_run_update();
    jimmie_run_collection(&gMarioStates[0],&star,&puff);
}
int main(int argc,char **argv) {
    assert(argc==2);const char *dir=argv[1];char text[24];
    boot(dir,0);jimmie_run_best_text(text,sizeof(text));assert(!strcmp(text,"19'09\"57"));
    gNetworkType=NT_NONE;jimmie_run_begin_file();assert(sClock.phase==JRC_BOOT);
    gNetworkType=NT_SERVER;jimmie_run_begin_file();assert(sClock.phase==JRC_RUNNING);
    assert(sClock.boot_us==1000000);PASS("seed and menu versus selected-file lifecycle");

    for(int mode=0;mode<4;mode++){
        boot(dir,mode+10);
        if(mode==0)gSaveBuffer.files[0][0].flags=SAVE_FLAG_HAVE_KEY_1;
        if(mode==1)gSaveBuffer.files[0][0].courseStars[3]=0x80;
        if(mode==2)gSaveBuffer.files[0][0].courseCoinScores[2]=1;
        if(mode==3)gSaveFileUsingBackupSlot=1;
        jimmie_run_begin_file();assert(sClock.phase==JRC_INVALID);
    }PASS("raw save progress, cannon, coin and backup masks rejected");

    boot(dir,20);jimmie_run_begin_file();arm();assert(sFinishPuff==&puff);
    assert(sClock.phase==JRC_RUNNING);assert(!fopen(path,"rb"));
    gMarioStates[0].action=ACT_JUMBO_STAR_CUTSCENE;
    jimmie_run_puff_emitted(&unrelated);assert(sClock.phase==JRC_RUNNING);
    jimmie_run_puff_emitted(&puff);assert(sClock.phase==JRC_FINISHED);
    assert(sClock.best_us==1000000000);assert(sClock.elapsed_us==1000000000);
    JrcState reload;jrc_boot(&reload,0);assert(jrc_load_pb(&reload,path));assert(reload.best_us==1000000000);
    now+=1000;jimmie_run_puff_emitted(&puff);assert(sClock.elapsed_us==1000000000);
    PASS("only matched native puff completes and persists once; disk reload agrees");

    for(int mode=0;mode<5;mode++){
        boot(dir,30+mode);jimmie_run_begin_file();arm();sFinishPuff=NULL;
        if(mode==0)gCurrLevelNum=LEVEL_BOWSER_2;
        if(mode==1)star.behavior=NULL;
        if(mode==2)star.oInteractionSubtype=0;
        if(mode==3)count=15;
        jimmie_run_collection(&gMarioStates[mode==4?1:0],&star,&puff);
        assert(!sFinishPuff);
    }PASS("wrong level, behavior, subtype, count and remote Mario never arm");

    for(int mode=0;mode<4;mode++){
        boot(dir,40+mode);jimmie_run_begin_file();arm();
        gMarioStates[0].action=ACT_JUMBO_STAR_CUTSCENE;
        if(mode==0)puff.parentObj=&unrelated;
        if(mode==1)gGlobalTimer+=2;
        if(mode==2)gCurrSaveFileNum=2;
        if(mode==3)gActiveMods.entryCount=1;
        jimmie_run_puff_emitted(&puff);assert(sClock.phase==JRC_INVALID);
        assert(!fopen(path,"rb"));
    }PASS("stale puff, parent mismatch, changed slot or mod profile cannot record");

    for(int mode=0;mode<6;mode++){
        boot(dir,50+mode);jimmie_run_begin_file();assert(sClock.phase==JRC_RUNNING);
        if(mode==0)jimmie_run_begin_file();
        if(mode==1)jimmie_run_disqualify();
        if(mode==2)gNetworkType=NT_NONE;
        if(mode==3)gServerSettings.skipIntro=1;
        if(mode==4)gMarioStates[0].action=ACT_DEBUG_FREE_MOVE;
        if(mode==5)gServerSettings.maxPlayers=2;
        jimmie_run_update();assert(sClock.phase==JRC_INVALID);
    }PASS("reload, debug warp, leave, skipped intro, free-move and multiplayer invalidate");

    boot(dir,60);jimmie_run_begin_file();now+=5000000;jimmie_run_update();
    assert(sClock.elapsed_us==9000000);assert(sClock.phase==JRC_RUNNING);
    PASS("hidden/pause time counts without reset or gameplay-frame dependence");

    boot(dir,70);
    struct Mod mod = {0}; struct Mod *mods[] = {&mod};
    mod.isDirectory=true;strcpy(mod.relativePath,"jimmie");
    mod.fileCount=sizeof(sProfileFiles)/sizeof(sProfileFiles[0]);
    mod.files=calloc(mod.fileCount,sizeof(struct ModFile));assert(mod.files);
    for(int i=0;i<mod.fileCount;i++) {
        assert(sProfileFiles[i].dynamic==0); /* No legacy AI/route mailbox in this fork slice. */
        strcpy(mod.files[i].relativePath,sProfileFiles[i].path);
        for(char *slash=mod.files[i].relativePath;*slash;slash++) if(*slash=='/') *slash='\\';
        memcpy(mod.files[i].dataHash,sProfileFiles[i].md5,16);
    }
    gActiveMods.entries=mods;gActiveMods.entryCount=1;
    jimmie_run_begin_file();assert(sClock.phase==JRC_RUNNING);
    jimmie_run_update();assert(sClock.phase==JRC_RUNNING);
    PASS("exact static original companion profile remains eligible");
    jimmie_companion_before_reload(&mod,NULL);assert(sClock.phase==JRC_INVALID);
    PASS("missing or unrecognized reload invalidates the static profile");
    sRejected=false;sVerifiedMod=NULL;sVerifiedFiles=NULL;
    mod.files[0].dataHash[0]^=1;assert(!jimmie_companion_profile_ok());
    mod.files[0].dataHash[0]^=1;assert(jimmie_companion_profile_ok());
    jimmie_companion_before_reload(&mod,&mod.files[0]);assert(sRejected);
    PASS("altered static source and static hot reload reject the profile");

    struct Mod textMod = {0}, unknownMod = {0}; struct ModFile textFile = {0};
    textMod.isDirectory=true;strcpy(textMod.relativePath,"jimmie_text");
    textMod.fileCount=1;textMod.files=&textFile;
    strcpy(textFile.relativePath,sTextProfileFiles[0].path);
    memcpy(textFile.dataHash,sTextProfileFiles[0].md5,16);
    unknownMod.isDirectory=true;strcpy(unknownMod.relativePath,"gameplay_helper");
    struct Mod *pair[]={&mod,&textMod}, *reverse[]={&textMod,&mod};
    struct Mod *textOnly[]={&textMod}, *duplicates[]={&textMod,&textMod};
    struct Mod *unknown[]={&textMod,&unknownMod};
    struct Mod *three[]={&mod,&textMod,&unknownMod};
    for(int mode=0;mode<3;mode++) {
        boot(dir,80+mode);gActiveMods.entries=mode==0?textOnly:mode==1?pair:reverse;
        gActiveMods.entryCount=mode==0?1:2;
        jimmie_run_begin_file();assert(sClock.phase==JRC_RUNNING);
        jimmie_run_update();assert(sClock.phase==JRC_RUNNING);
        arm();gMarioStates[0].action=ACT_JUMBO_STAR_CUTSCENE;
        jimmie_run_puff_emitted(&puff);assert(sClock.phase==JRC_FINISHED);
        jrc_boot(&reload,0);assert(jrc_load_pb(&reload,path));assert(reload.best_us==1000000000);
    }
    PASS("exact text alone and with static companion in either order can finish and persist");

    for(int mode=0;mode<8;mode++) {
        boot(dir,90+mode);gActiveMods.entries=pair;gActiveMods.entryCount=2;
        if(mode==0)textFile.dataHash[0]^=1;
        if(mode==1)strcpy(textFile.relativePath,"other.lua");
        if(mode==2)textMod.fileCount=2;
        if(mode==3)strcpy(textMod.relativePath,"jimmie_text_copy");
        if(mode==4)textMod.isDirectory=false;
        if(mode==5)gActiveMods.entries=duplicates;
        if(mode==6)gActiveMods.entries=unknown;
        if(mode==7){gActiveMods.entries=three;gActiveMods.entryCount=3;}
        jimmie_run_begin_file();assert(sClock.phase==JRC_INVALID);assert(!fopen(path,"rb"));
        if(mode==0)textFile.dataHash[0]^=1;
        strcpy(textFile.relativePath,"main.lua");strcpy(textMod.relativePath,"jimmie_text");
        textMod.fileCount=1;textMod.isDirectory=true;
    }
    PASS("changed text hash/name/inventory, renamed/archive/duplicate/unknown/third mods cannot record");

    for(int mode=0;mode<4;mode++) {
        boot(dir,100+mode);gActiveMods.entries=pair;gActiveMods.entryCount=2;
        if(mode==0)gServerSettings.bubbleDeath=true;
        if(mode==1)gSaveBuffer.files[0][0].courseStars[0]=1;
        if(mode==2)gSaveBuffer.files[0][0].courseCoinScores[0]=1;
        if(mode==3)gSaveFileUsingBackupSlot=true;
        jimmie_run_begin_file();assert(sClock.phase==JRC_INVALID);assert(!fopen(path,"rb"));
    }
    PASS("approved text does not relax normal-death, clean-save or primary-slot requirements");

    for(int mode=0;mode<5;mode++) {
        boot(dir,110+mode);gActiveMods.entries=pair;gActiveMods.entryCount=2;
        jimmie_run_begin_file();assert(sClock.phase==JRC_RUNNING);
        if(mode==0)jimmie_companion_before_reload(&textMod,&textFile);
        if(mode==1)gActiveMods.entries=unknown;
        if(mode==2){gActiveMods.entries=mods;gActiveMods.entryCount=1;}
        if(mode==3){gActiveMods.entries=textOnly;gActiveMods.entryCount=1;}
        if(mode==4)mod.fileCount++;
        jimmie_run_update();assert(sClock.phase==JRC_INVALID);assert(!fopen(path,"rb"));
        if(mode==4)mod.fileCount--;
    }
    PASS("text hot reload, unknown mod, removal and changed companion inventory invalidate active attempts");
    free(mod.files);
    printf("%d bridge groups passed\n",passed);return 0;
}
