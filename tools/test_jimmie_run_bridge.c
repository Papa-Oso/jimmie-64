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
static char runs[1100];
const char *fs_get_write_path(const char *name) {
    if (strstr(name, "runs")) { snprintf(runs, sizeof(runs), "%s.runs", path); return runs; }
    return path;
}
u8 network_player_connected_count(void) { return 1; }
s32 save_file_get_total_star_count(s32 f,s32 low,s32 high) {(void)f;(void)low;(void)high;return count;}
#define PASS(text) do {printf("PASS %s\n",text);passed++;} while(0)

static void boot(const char *dir, int test) {
    snprintf(path,sizeof(path),"%s/bridge-%d.pb",dir,test);
    snprintf(runs,sizeof(runs),"%s.runs",path);
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
    assert(sClock.boot_us==5000000 && sClock.elapsed_us==0);
    assert(jimmie_run_phase()==1 && jimmie_run_stars()==0);
    PASS("menu is not a run; a chosen file is timed from that moment");

    for(int mode=0;mode<4;mode++){
        boot(dir,mode+10);
        if(mode==0)gSaveBuffer.files[0][0].flags=SAVE_FLAG_HAVE_KEY_1;
        if(mode==1)gSaveBuffer.files[0][0].courseStars[3]=0x80;
        if(mode==2)gSaveBuffer.files[0][0].courseCoinScores[2]=1;
        if(mode==3)gSaveFileUsingBackupSlot=1;
        jimmie_run_begin_file();assert(sClock.phase==JRC_INVALID);
    }PASS("a file with any progress, or the backup slot, is not timed");

    boot(dir,15);gActiveMods.entryCount=1;gServerSettings.bubbleDeath=true;
    jimmie_run_begin_file();assert(sClock.phase==JRC_RUNNING);
    jimmie_run_update();assert(sClock.phase==JRC_RUNNING);
    PASS("the mod's file list and the bubble-death setting no longer make a run ineligible");

    boot(dir,20);jimmie_run_begin_file();
    count=1;now=65000000;jimmie_run_update();count=2;now=125000000;jimmie_run_update();
    assert(jimmie_run_split_us(1)==60000000 && jimmie_run_split_us(2)==120000000 && jimmie_run_split_us(3)==0);
    arm();assert(sFinishPuff==&puff);
    assert(sClock.phase==JRC_RUNNING);assert(!fopen(path,"rb"));
    gMarioStates[0].action=ACT_JUMBO_STAR_CUTSCENE;
    jimmie_run_puff_emitted(&unrelated);assert(sClock.phase==JRC_RUNNING);
    jimmie_run_puff_emitted(&puff);assert(sClock.phase==JRC_FINISHED);
    assert(sClock.best_us==996000000);assert(sClock.elapsed_us==996000000);
    JrcState reload;jrc_boot(&reload,0);assert(jrc_load_pb(&reload,path));assert(reload.best_us==996000000);
    now+=1000;jimmie_run_puff_emitted(&puff);assert(sClock.elapsed_us==996000000);
    PASS("only the real final-star moment finishes; the best time is saved once and reloads");

    char line[700]={0},body[700]={0};unsigned check=0;
    FILE *r=fopen(runs,"rb");assert(r);assert(fgets(line,sizeof(line),r));assert(!fgets(body,sizeof(body),r));fclose(r);
    assert(!strncmp(line,"JIMMIE16RUN1 time_us=996000000 stars=16 pb=1 test=0 splits=60000000,120000000,",78));
    char *mark=strstr(line," check=");assert(mark);assert(sscanf(mark," check=%x",&check)==1);
    memcpy(body,line,(size_t)(mark-line));body[mark-line]=0;
    assert(line_check(body)==check);
    body[21]='8';assert(line_check(body)!=check);      /* 996000000 edited to 986000000 */
    PASS("a run record is written with its splits; an edited time no longer matches its check value");

    for(int mode=0;mode<5;mode++){
        boot(dir,30+mode);jimmie_run_begin_file();arm();sFinishPuff=NULL;
        if(mode==0)gCurrLevelNum=LEVEL_BOWSER_2;
        if(mode==1)star.behavior=NULL;
        if(mode==2)star.oInteractionSubtype=0;
        if(mode==3)count=15;
        jimmie_run_collection(&gMarioStates[mode==4?1:0],&star,&puff);
        assert(!sFinishPuff);
    }PASS("wrong level, object, star count or another player's Mario never arms the finish");

    for(int mode=0;mode<3;mode++){
        boot(dir,40+mode);jimmie_run_begin_file();arm();
        gMarioStates[0].action=ACT_JUMBO_STAR_CUTSCENE;
        if(mode==0)puff.parentObj=&unrelated;
        if(mode==1)gGlobalTimer+=2;
        if(mode==2)gCurrSaveFileNum=2;
        jimmie_run_puff_emitted(&puff);assert(sClock.phase==JRC_INVALID);
        assert(!fopen(path,"rb"));assert(!fopen(runs,"rb"));
    }PASS("a stale or mismatched finish, or a changed save slot, records nothing");

    for(int mode=0;mode<5;mode++){
        boot(dir,50+mode);jimmie_run_begin_file();assert(sClock.phase==JRC_RUNNING);
        if(mode==0)jimmie_run_disqualify();
        if(mode==1)gNetworkType=NT_NONE;
        if(mode==2)gServerSettings.skipIntro=1;
        if(mode==3)gMarioStates[0].action=ACT_DEBUG_FREE_MOVE;
        if(mode==4)gServerSettings.maxPlayers=2;
        jimmie_run_update();assert(sClock.phase==JRC_INVALID);
    }PASS("debug warp, leaving, skipped intro, free-move and a second player end the timed run");

    boot(dir,60);jimmie_run_begin_file();now+=5000000;jimmie_run_update();
    assert(sClock.elapsed_us==5000000);assert(sClock.phase==JRC_RUNNING);
    jimmie_run_begin_file();assert(sClock.phase==JRC_RUNNING && sClock.elapsed_us==0);
    PASS("time passes while paused or hidden; choosing the file again starts a new attempt");

    printf("%d bridge groups passed\n",passed);return 0;
}
