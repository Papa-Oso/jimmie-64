#include "jimmie_run_clock.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <inttypes.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#else
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#endif
static uint32_t checksum(uint64_t value) {
    return (uint32_t)value ^ (uint32_t)(value >> 32) ^ UINT32_C(0x4a313642);
}
void jrc_invalidate(JrcState *s, const char *reason) {
    if (s->phase == JRC_FINISHED) return;
    s->phase=JRC_INVALID; s->reason=reason;
}
void jrc_boot(JrcState *s, int64_t now_us) {
    memset(s,0,sizeof(*s)); s->best_us=JRC_SEED_US;
    s->boot_us=s->last_us=now_us; s->phase=JRC_BOOT;
    if(now_us<0) jrc_invalidate(s,"monotonic clock unavailable");
}
void jrc_tick(JrcState *s, int64_t now_us) {
    if(s->phase==JRC_FINISHED || s->phase==JRC_INVALID) return;
    if(now_us<0 || now_us<s->last_us || now_us<s->boot_us) {
        jrc_invalidate(s,"monotonic clock moved backwards/unavailable"); return;
    }
    uint64_t elapsed=(uint64_t)(now_us-s->boot_us);
    if(elapsed>=JRC_MAX_US) { jrc_invalidate(s,"attempt exceeded 24 hours"); return; }
    s->last_us=now_us; s->elapsed_us=elapsed;
}
bool jrc_load_pb(JrcState *s,const char *path) {
    if(s->storage_ready || s->storage_fault) return false;
    if(!path || !*path || strlen(path)>=sizeof(s->path)-5) {
        s->storage_fault=true; return false;
    }
    memcpy(s->path,path,strlen(path)+1);
    errno=0; FILE *f=fopen(path,"rb");
    if(!f) {
        if(errno==ENOENT) {s->storage_ready=true;return true;}
        s->storage_fault=true;return false;
    }
    char data[128]; size_t n=fread(data,1,sizeof(data)-1,f);
    bool read_ok=!ferror(f) && feof(f); fclose(f); data[n]='\0';
    uint64_t value=0; uint32_t check=0; int end=0;
    int fields=sscanf(data,"JIMMIE16PB1\n%" SCNu64 "\n%" SCNx32 "\n%n",&value,&check,&end);
    char canonical[128];
    int expected=snprintf(canonical,sizeof(canonical),"JIMMIE16PB1\n%" PRIu64 "\n%08" PRIx32 "\n",value,check);
    if(!read_ok || fields!=2 || end!=(int)n || expected!=(int)n || strcmp(canonical,data)!=0 || value==0 || value>JRC_SEED_US || check!=checksum(value)) {
        s->storage_fault=true;return false; /* Never overwrite an unreadable existing record. */
    }
    s->best_us=value;s->storage_ready=true;return true;
}
bool jrc_begin_file(JrcState *s,int64_t now_us,int file,bool clean,bool eligible) {
    /* Every file selection starts a new attempt, timed from this moment (the usual
       real-time rule: the clock starts when the file is chosen). The stored best time
       and its storage state carry over; nothing else from an earlier attempt does. */
    if(now_us<0) { jrc_invalidate(s,"monotonic clock unavailable");return false; }
    s->boot_us=s->last_us=now_us; s->elapsed_us=0; s->file=0; s->stars=0;
    s->phase=JRC_BOOT; s->reason=NULL;
    memset(s->split_us,0,sizeof(s->split_us));
    if(!clean || !eligible || file<1 || file>4) {
        jrc_invalidate(s,"not a supported clean-file run");return false;
    }
    s->file=file;s->phase=JRC_RUNNING;return true;
}
void jrc_observe(JrcState *s,int64_t now_us,int file,int stars,bool eligible) {
    jrc_tick(s,now_us);
    if(s->phase!=JRC_RUNNING) return;
    if(!eligible || file!=s->file || stars<s->stars || stars>16 || stars<0) {
        jrc_invalidate(s,"profile, save slot or star progress changed");return;
    }
    for(int i=s->stars;i<stars && i<16;++i) s->split_us[i]=s->elapsed_us; /* time at each new star */
    s->stars=stars;
}
static bool write_record(JrcState *s,uint64_t value) {
    if(!s->storage_ready || s->storage_fault) return false;
    char tmp[sizeof(s->path)+5]; snprintf(tmp,sizeof(tmp),"%s.tmp",s->path);
    FILE *f=fopen(tmp,"wb");if(!f)return false;
    bool ok=fprintf(f,"JIMMIE16PB1\n%" PRIu64 "\n%08" PRIx32 "\n",value,checksum(value))>0;
    if(fflush(f)!=0)ok=false;
#ifdef _WIN32
    if(_commit(_fileno(f))!=0)ok=false;
#else
    if(fsync(fileno(f))!=0)ok=false;
#endif
    if(fclose(f)!=0)ok=false;
    if(!ok)return false; /* Old PB is never removed on a failed write. */
#ifdef _WIN32
    return MoveFileExA(tmp,s->path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
#else
    return rename(tmp,s->path)==0;
#endif
}
static JrcResult save_if_better(JrcState *s,uint64_t value) {
    if(!s->storage_ready || s->storage_fault)return JRC_STORE_FAILED;
    char lockpath[sizeof(s->path)+6];snprintf(lockpath,sizeof(lockpath),"%s.lock",s->path);
#ifdef _WIN32
    HANDLE lock=CreateFileA(lockpath,GENERIC_READ|GENERIC_WRITE,0,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(lock==INVALID_HANDLE_VALUE)return JRC_STORE_FAILED;
#else
    int lock=open(lockpath,O_CREAT|O_RDWR,0600);
    if(lock<0)return JRC_STORE_FAILED;
    struct flock spec={0};spec.l_type=F_WRLCK;spec.l_whence=SEEK_SET;
    if(fcntl(lock,F_SETLK,&spec)==-1){close(lock);return JRC_STORE_FAILED;}
#endif
    /* Another process may have improved the same PB since we loaded it. */
    JrcState disk;jrc_boot(&disk,0);
    JrcResult result=JRC_STORE_FAILED;
    if(jrc_load_pb(&disk,s->path)) {
        uint64_t previous=disk.best_us<s->best_us?disk.best_us:s->best_us;
        if(value>=previous){s->best_us=previous;result=JRC_NO_CHANGE;}
        else if(write_record(s,value)){s->best_us=value;result=JRC_NEW_PB;}
    }
#ifdef _WIN32
    CloseHandle(lock);
#else
    close(lock);
#endif
    return result;
}
JrcResult jrc_finish(JrcState *s,int64_t now_us,int file,int stars,bool proof,bool eligible) {
    if(s->phase!=JRC_RUNNING)return JRC_REJECTED;
    jrc_observe(s,now_us,file,stars,eligible);
    if(s->phase!=JRC_RUNNING)return JRC_REJECTED;
    if(!proof || stars!=16 || s->elapsed_us==0) {
        jrc_invalidate(s,"finish is not the local 16-star grand-star collection");return JRC_REJECTED;
    }
    s->phase=JRC_FINISHED;
    if(s->elapsed_us>=s->best_us)return JRC_NO_CHANGE;
    JrcResult result=save_if_better(s,s->elapsed_us);
    if(result==JRC_STORE_FAILED)s->reason="PB persistence failed; previous PB retained";
    return result;
}
void jrc_format(uint64_t us,char *out,size_t capacity) {
    uint64_t cs=us/10000;
    snprintf(out,capacity,"%02" PRIu64 "'%02" PRIu64 "\"%02" PRIu64,cs/6000,(cs/100)%60,cs%100);
}
int64_t jrc_monotonic_us(void) {
#ifdef _WIN32
    LARGE_INTEGER c,f;
    if(!QueryPerformanceFrequency(&f)||!QueryPerformanceCounter(&c)||f.QuadPart<=0||c.QuadPart<0)return -1;
    return (c.QuadPart/f.QuadPart)*INT64_C(1000000)+((c.QuadPart%f.QuadPart)*INT64_C(1000000))/f.QuadPart;
#else
#ifdef CLOCK_MONOTONIC
    struct timespec ts;
    if(clock_gettime(CLOCK_MONOTONIC,&ts)!=0)return -1;
    return (int64_t)ts.tv_sec*INT64_C(1000000)+ts.tv_nsec/1000;
#else
    return -1;
#endif
#endif
}
