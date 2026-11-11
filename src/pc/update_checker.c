#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#include <windows.h>
#include <wininet.h>
#else
#include <curl/curl.h>
#endif

#include "update_checker.h"
#include "pc/djui/djui.h"
#include "pc/network/version.h"
#include "pc/loading.h"
#include "pc/jimmie_version.h"

// Jimmie 64: the check is against this fork's own releases, not the upstream port's.
// It is a plain download of one small public file; nothing about the player is sent.
#define URL "https://raw.githubusercontent.com/Papa-Oso/jimmie-64/refs/heads/main/src/pc/jimmie_version.h"
#define VERSION_IDENTIFIER "#define JIMMIE_VERSION \""
#define UPDATE_TIMEOUT_MS 3000

/*

NOTE: This entire update checker process should be replaced with one that uses GitHub's API
to check for the latest release version. This would be more reliable and efficient than
downloading and parsing a source file.

*/

static char sVersionUpdateTextBuffer[256] = { 0 };
static char sRemoteVersionStr[16] = { 0 };

struct Version {
    int maj, min, fix;
};

bool is_version_newer(struct Version client, struct Version remote) {
    if (remote.maj != client.maj) return remote.maj > client.maj;
    if (remote.min != client.min) return remote.min > client.min;
    return remote.fix > client.fix;
}

static struct Version sClientVersion = { 0 };
static struct Version sRemoteVersion = { 0 };

bool gUpdateMessage = false;

void show_update_popup(void) {
    if (sVersionUpdateTextBuffer[0] == '\0') { return; }
    djui_popup_create(sVersionUpdateTextBuffer, 3);
}

#if !(defined(_WIN32) || defined(_WIN64))
typedef struct { char *str; size_t size; } Buffer;
size_t write_callback(char *ptr, size_t size, size_t nmemb, void *userdata) {
    size_t realsize = size * nmemb;
    Buffer *buf = (Buffer *) userdata;

    // allocate memory for the received data and copy it into the buffer
    char *data = realloc(buf->str, buf->size + realsize + 1);
    if (data == NULL) { return 0; }

    memcpy(&data[buf->size], ptr, realsize);
    buf->size += realsize;
    buf->str = data;
    buf->str[buf->size] = '\0'; // null-terminate the string

    return realsize;
}
#endif

void string_to_version(const char *str, struct Version *ver) {
    char* end;
    ver->maj = strtol(str+1, &end, 10);
    ver->min = 0; ver->fix = 0;
    if (end) ver->min = strtol(end+1, &end, 10);
    if (end) ver->fix = strtol(end+1, &end, 10);
}

void version_to_string(struct Version ver, char* str, size_t size) {
    int len;
    snprintf(str, size, "v%i", ver.maj);
    if (ver.min || ver.fix) {
        len = strlen(str);
        snprintf(str + len, size - len, ".%i", ver.min);
        if (ver.fix) {
            len = strlen(str);
            snprintf(str + len, size - len, ".%i", ver.fix);
        }
    }
}

void parse_version(const char *data) {
    const char *version = strstr(data, VERSION_IDENTIFIER);
    if (version == NULL) { return; }
    size_t len = strlen(VERSION_IDENTIFIER);
    version += len;
    const char *end = strchr(version, '"');
    if (end == NULL) { return; }
    size_t versionLength = (size_t)(end - version);
    if (versionLength > sizeof(sRemoteVersionStr) - 1) { return; }
    memcpy(sRemoteVersionStr, version, versionLength);
    sRemoteVersionStr[versionLength] = '\0';

    string_to_version(sRemoteVersionStr, &sRemoteVersion);
    string_to_version(JIMMIE_VERSION, &sClientVersion);
}

// function to download a text file from the internet
void get_version_remote(void) {
    sRemoteVersionStr[0] = '\0';

#if defined(_WIN32)
    char buffer[0x400] = { 0 };

    // initialize WinINet
    HINTERNET hInternet = InternetOpenA("sm64coopdx", INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
    if (!hInternet) {
        printf("Failed to check for updates!\n");
        return;
    }
    // give up after three seconds: no internet must never hold the game up
    DWORD timeout = UPDATE_TIMEOUT_MS;
    InternetSetOptionA(hInternet, INTERNET_OPTION_CONNECT_TIMEOUT, &timeout, sizeof(timeout));
    InternetSetOptionA(hInternet, INTERNET_OPTION_SEND_TIMEOUT, &timeout, sizeof(timeout));
    InternetSetOptionA(hInternet, INTERNET_OPTION_RECEIVE_TIMEOUT, &timeout, sizeof(timeout));

    // open the URL
    // JIMMIE_UPDATE_URL lets a test point the check at a stand-in file; players never set it.
    const char *url = getenv("JIMMIE_UPDATE_URL");
    if (url == NULL || url[0] == '\0') { url = URL; }
    HINTERNET hUrl = InternetOpenUrlA(hInternet, url, NULL, 0, INTERNET_FLAG_RELOAD, 0);
    if (!hUrl) {
        printf("Failed to check for updates!\n");
        InternetCloseHandle(hInternet);
        return;
    }

    // calculate the size of the file
    DWORD contentLength;
    DWORD dwSize = sizeof(contentLength);
    HttpQueryInfo(hUrl, HTTP_QUERY_CONTENT_LENGTH | HTTP_QUERY_FLAG_NUMBER, &contentLength, &dwSize, NULL);

    // read data from the URL, making room in the buffer for the null-terminator
    DWORD bytesRead;
    if (!InternetReadFile(hUrl, buffer, sizeof(buffer) - 1, &bytesRead)) {
        printf("Failed to check for updates!\n");
        InternetCloseHandle(hInternet);
        InternetCloseHandle(hUrl);
        return;
    }

    buffer[bytesRead] = '\0';

    // close handles
    InternetCloseHandle(hUrl);
    InternetCloseHandle(hInternet);
#else
    Buffer data = { .str = NULL, .size = 0 };

    // initialize libcurl
    CURL *curl = curl_easy_init();
    if (!curl || curl_global_init(CURL_GLOBAL_ALL) != CURLE_OK) {
        printf("Failed to check for updates!\n");
        return;
    }

    // set properties
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &data);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 3); // only allow 3 seconds
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 3);
    curl_easy_setopt(curl, CURLOPT_URL, URL);

    // perform the request
    CURLcode res = curl_easy_perform(curl);
    if (res != CURLE_OK) {
        printf("Failed to check for updates!\n");
        curl_easy_cleanup(curl);
        return;
    }
    char* buffer = data.str;

    // Clean up
    curl_easy_cleanup(curl);
#endif
    parse_version(buffer);
#if !(defined(_WIN32) || defined(_WIN64))
    free(buffer);
#endif
}

void check_for_updates(void) {
    LOADING_SCREEN_MUTEX(loading_screen_set_segment_text("Checking For Updates"));

    get_version_remote();
    if (sRemoteVersionStr[0] == 'v' && is_version_newer(sClientVersion, sRemoteVersion)) {
        snprintf(
            sVersionUpdateTextBuffer, 256,
            "\\#ffffa0\\A new Jimmie 64 is out\n\\#dcdcdc\\Latest: %s   Yours: %s\nRun \"Update Jimmie 64\" in the game folder",
            sRemoteVersionStr,
            JIMMIE_VERSION
        );
        printf("Jimmie 64 update available: %s (this is %s)\n", sRemoteVersionStr, JIMMIE_VERSION);
        gUpdateMessage = true;
    }
}
