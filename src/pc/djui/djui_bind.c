#include <stdio.h>
#include <string.h>
#include "djui.h"
#include "pc/controller/controller_api.h"
#include "pc/controller/controller_bind_mapping.h"
#include "sounds.h"
#include "audio/external.h"

#define VK_ESCAPE 1

static void djui_bind_button_on_click(struct DjuiBase* caller) {
    struct DjuiButton* button = (struct DjuiButton*)caller;
    djui_text_set_text(button->text, "...");
    controller_get_raw_key(); // consume lingering controller button press
    djui_interactable_set_binding(caller);
}

static void djui_bind_button_on_bind(struct DjuiBase* caller) {
    struct DjuiButton* button = (struct DjuiButton*)caller;
    struct DjuiBind* bind = (struct DjuiBind*) caller->parent->parent;

    // get key
    u32 key = controller_get_raw_key();
    if (key == VK_INVALID) { return; }

    for (int i = 0; i < bind->buttonCount; i++) {
        if (i == button->base.tag) { continue; }
        if (bind->configKey[i] == key) {
            if (key == VK_RSTICK_UP || key == VK_RSTICK_DOWN || key == VK_RSTICK_LEFT || key == VK_RSTICK_RIGHT) {
                // A default stick bind may already occupy the last slot. Move it to the selected slot.
                bind->configKey[i] = VK_INVALID;
            } else {
                key = VK_INVALID;
            }
        }
    }

    // set key
    bind->configKey[button->base.tag] = key;
    djui_bind_refresh(bind);
    djui_interactable_set_binding(NULL);
    play_sound(SOUND_MENU_CHANGE_SELECT, gGlobalSoundSource);
    controller_reconfigure();
}

static void djui_bind_destroy(struct DjuiBase* base) {
    struct DjuiBind* bind = (struct DjuiBind*)base;
    free(bind);
}

struct DjuiBind* djui_bind_create(struct DjuiBase* parent, const char* message, unsigned int configKey[]) {
    struct DjuiBind* bind = calloc(1, sizeof(struct DjuiBind));
    struct DjuiBase* base     = &bind->base;

    bind->configKey = configKey;
    bind->buttonCount = configfile_bind_count(configKey);

    djui_base_init(parent, base, NULL, djui_bind_destroy);
    djui_base_set_size_type(&bind->base, DJUI_SVT_RELATIVE, DJUI_SVT_ABSOLUTE);
    djui_base_set_size(&bind->base, 1.0f, 28);
    djui_base_set_color(&bind->base, 0, 0, 0, 0);

    struct DjuiText* text = djui_text_create(&bind->base, message);
    djui_base_set_alignment(&text->base, DJUI_HALIGN_LEFT, DJUI_VALIGN_CENTER);
    djui_base_set_size_type(&text->base, DJUI_SVT_RELATIVE, DJUI_SVT_RELATIVE);
    djui_base_set_size(&text->base, 0.3f, 1.0f);
    djui_text_set_alignment(text, DJUI_HALIGN_LEFT, DJUI_VALIGN_BOTTOM);
    djui_text_set_drop_shadow(text, 64, 64, 64, 100);
    djui_base_set_color(&text->base, 220, 220, 220, 255);
    bind->text = text;

    struct DjuiRect* rect = djui_rect_create(&bind->base);
    djui_base_set_alignment(&rect->base, DJUI_HALIGN_RIGHT, DJUI_VALIGN_CENTER);
    djui_base_set_size_type(&rect->base, DJUI_SVT_RELATIVE, DJUI_SVT_RELATIVE);
    djui_base_set_size(&rect->base, 0.7f, 1.0f);
    djui_base_set_color(&rect->base, 0, 0, 0, 0);
    bind->rect = rect;

    f32 buttonWidth = 0.99f / bind->buttonCount;
    f32 buttonSpacing = (1.0f - buttonWidth) / (bind->buttonCount - 1);
    for (int i = 0; i < bind->buttonCount; i++) {
        unsigned int key = configKey[i];
        struct DjuiButton* button = djui_button_create(&rect->base, translate_bind_to_name(key), DJUI_BUTTON_STYLE_NORMAL, djui_bind_button_on_click);
        djui_base_set_size_type(&button->base, DJUI_SVT_RELATIVE, DJUI_SVT_RELATIVE);
        djui_base_set_size(&button->base, buttonWidth, 1.0f);
        djui_base_set_alignment(&button->base, DJUI_HALIGN_LEFT, DJUI_VALIGN_CENTER);
        djui_base_set_location_type(&button->base, DJUI_SVT_RELATIVE, DJUI_SVT_ABSOLUTE);
        djui_base_set_location(&button->base, i * buttonSpacing, 0);
        djui_text_set_font_scale(button->text, button->text->fontScale * MAX_BINDS / bind->buttonCount);
        button->base.tag = i;
        djui_interactable_hook_bind(&button->base, djui_bind_button_on_bind);

        bind->buttons[i] = button;
    }

    return bind;
}

void djui_bind_refresh(struct DjuiBind *bind) {
    if (!bind || !bind->configKey) { return; }

    for (s32 i = 0; i < bind->buttonCount; ++i) {
        struct DjuiButton *button = bind->buttons[i];
        if (!button) { continue; }

        u32 key = bind->configKey[i];
        djui_text_set_text(button->text, translate_bind_to_name(key));
    }
}

void djui_bind_unbind(struct DjuiBase* caller) {
    if (!caller || !caller->interactable || !caller->parent || !caller->parent->parent) { return; }

    struct DjuiInteractable *interactable = caller->interactable;
    if (interactable->on_bind != djui_bind_button_on_bind) {
        return; // not a bind
    }

    struct DjuiBind *bind = (struct DjuiBind *) caller->parent->parent;
    for (s32 i = 0; i < bind->buttonCount; ++i) {
        if (&bind->buttons[i]->base == caller) {
            bind->configKey[i] = VK_INVALID;

            // refresh bind
            djui_bind_refresh(bind);
            play_sound(SOUND_MENU_CHANGE_SELECT, gGlobalSoundSource);
            controller_reconfigure();
            return;
        }
    }
}
