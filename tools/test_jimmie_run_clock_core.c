/* Run-clock core tests. Timing rule since 2026-11-10: an attempt is timed from the moment its
   file is chosen, and choosing a file again starts a new attempt. No game launch. */
#include "jimmie_run_clock.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#endif
#define START 5000000
static int passed=0;
#define PASS(name) do {printf("PASS %s\n",name);++passed;} while(0)
static void boot(JrcState *s,const char *path) {
    jrc_boot(s,1000000);assert(jrc_load_pb(s,path));
    assert(jrc_begin_file(s,START,1,true,true));
}
static void progress(JrcState *s,int count) {
    for(int i=1;i<=count;i++)jrc_observe(s,START+i*1000000,1,i,true);
}
static void path(char *out,const char *dir,const char *name) {sprintf(out,"%s/%s",dir,name);}
int main(int argc,char **argv) {
    assert(argc==2);char p[1024],text[40];JrcState s,t;
    path(p,argv[1],"seed.pb");jrc_boot(&s,1000000);assert(jrc_load_pb(&s,p));
    assert(s.best_us==JRC_SEED_US);jrc_format(s.best_us,text,sizeof(text));assert(!strcmp(text,"19'09\"57"));
    FILE *f=fopen(p,"rb");assert(!f);PASS("hardcoded seed; no bootstrap write");

    assert(jrc_begin_file(&s,START,1,true,true));assert(s.elapsed_us==0);
    jrc_tick(&s,START+6000000);assert(s.elapsed_us==6000000);PASS("timed from file selection, not from program start");

    jrc_observe(&s,START+7000000,1,1,true);jrc_observe(&s,START+9000000,1,3,true);
    assert(s.split_us[0]==7000000 && s.split_us[1]==9000000 && s.split_us[2]==9000000 && s.split_us[3]==0);
    PASS("the time at each new star is kept");

    assert(jrc_begin_file(&s,START+20000000,2,true,true));
    assert(s.phase==JRC_RUNNING && s.elapsed_us==0 && s.stars==0 && s.file==2 && s.split_us[0]==0);
    jrc_tick(&s,START+21000000);assert(s.elapsed_us==1000000);
    assert(!jrc_begin_file(&s,START+30000000,1,false,true));assert(s.phase==JRC_INVALID);
    assert(jrc_begin_file(&s,START+40000000,1,true,true));assert(s.phase==JRC_RUNNING);
    PASS("choosing a file again starts a new attempt; a used file is not timed");

    boot(&s,p);jrc_tick(&s,START+10000000);jrc_observe(&s,START+1000000,1,1,true); /* clock went backwards */
    assert(s.phase==JRC_INVALID);assert(jrc_finish(&s,1000000000,1,16,true,true)==JRC_REJECTED);assert(s.best_us==JRC_SEED_US);
    PASS("backwards clock invalidates and retains seed");

    path(p,argv[1],"faster.pb");boot(&s,p);progress(&s,16);
    assert(jrc_finish(&s,START+1100000000,1,16,true,true)==JRC_NEW_PB);assert(s.best_us==1100000000);
    assert(jrc_finish(&s,START+1000000000,1,16,true,true)==JRC_REJECTED);
    jrc_boot(&t,0);assert(jrc_load_pb(&t,p));assert(t.best_us==1100000000);PASS("completed faster run persists and reloads once");
    for(int add=0;add<=1;add++) {boot(&s,p);progress(&s,16);assert(jrc_finish(&s,START+1100000000+add,1,16,true,true)==JRC_NO_CHANGE);assert(s.best_us==1100000000);}
    PASS("tie and slower never replace PB");

    path(p,argv[1],"concurrent.pb");boot(&s,p);boot(&t,p);progress(&s,16);progress(&t,16);
    assert(jrc_finish(&s,START+1080000000,1,16,true,true)==JRC_NEW_PB);
    assert(jrc_finish(&t,START+1110000000,1,16,true,true)==JRC_NO_CHANGE);assert(t.best_us==1080000000);
    jrc_boot(&s,0);assert(jrc_load_pb(&s,p));assert(s.best_us==1080000000);PASS("stale second instance cannot replace faster disk PB");

    path(p,argv[1],"unfinished.pb");boot(&s,p);progress(&s,16);jrc_tick(&s,800000000);f=fopen(p,"rb");assert(!f);
    jrc_invalidate(&s,"exit/abort");assert(jrc_finish(&s,801000000,1,16,true,true)==JRC_REJECTED);PASS("unfinished and aborted runs never write");
    for(int mode=0;mode<4;mode++) {boot(&s,p);progress(&s,15);
        assert(jrc_finish(&s,800000000,mode==0?2:1,mode==1?15:16,mode!=2,mode!=3)==JRC_REJECTED);assert(s.best_us==JRC_SEED_US);}
    PASS("wrong slot/count/event/profile cannot finish");
    for(int mode=0;mode<3;mode++){boot(&s,p);progress(&s,3);jrc_observe(&s,100000000,1,mode==0?2:mode==1?17:3,mode!=2);assert(s.phase==JRC_INVALID);}
    jrc_boot(&s,0);assert(!jrc_begin_file(&s,1,1,false,true));jrc_boot(&s,0);assert(!jrc_begin_file(&s,1,1,true,false));PASS("dirty file and progress/profile changes invalidate");
    jrc_boot(&s,-1);assert(s.phase==JRC_INVALID);jrc_boot(&s,0);jrc_tick(&s,JRC_MAX_US);assert(s.phase==JRC_INVALID);PASS("missing clock and 24h bound fail closed");

    path(p,argv[1],"corrupt.pb");f=fopen(p,"wb");assert(f);fputs("existing damaged record",f);fclose(f);
    jrc_boot(&s,1000000);assert(!jrc_load_pb(&s,p));assert(s.storage_fault);assert(jrc_begin_file(&s,START,1,true,true));progress(&s,16);
    assert(jrc_finish(&s,START+900000000,1,16,true,true)==JRC_STORE_FAILED);assert(s.best_us==JRC_SEED_US);
    f=fopen(p,"rb");assert(f);memset(text,0,sizeof(text));fread(text,1,39,f);fclose(f);assert(!strcmp(text,"existing damaged record"));PASS("corrupt record is preserved, not silently overwritten");
    path(p,argv[1],"absent-directory/pb.txt");boot(&s,p);progress(&s,16);assert(jrc_finish(&s,START+900000000,1,16,true,true)==JRC_STORE_FAILED);assert(s.best_us==JRC_SEED_US);PASS("failed persistence retains previous PB");
    int64_t a=jrc_monotonic_us();assert(a>=0);
#ifdef _WIN32
    Sleep(30);
#endif
    int64_t b=jrc_monotonic_us();assert(b>=a);
#ifdef _WIN32
    assert(b-a>=20000 && b-a<2000000);
#endif
    PASS("real platform monotonic clock advances");
    printf("%d focused groups passed\n",passed);return 0;
}
