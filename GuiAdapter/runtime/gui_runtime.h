/* Minimal GUI runtime header - Stage 1 prototype */
#ifndef GUI_RUNTIME_H
#define GUI_RUNTIME_H

#include <stdint.h>
#include <stdbool.h>

typedef enum { GUI_ROT_0=0, GUI_ROT_90=1, GUI_ROT_180=2, GUI_ROT_270=3 } gui_rotation_t;
typedef enum { GUI_OK=0, GUI_ERR=1 } gui_result_t;

typedef struct display_driver_t {
    gui_result_t (*draw_area_sync)(const uint8_t* data, int x, int y, int width, int height);
    gui_result_t (*draw_area_async)(const uint8_t* data, int x, int y, int width, int height);
    bool (*display_busy)(void);
} display_driver_t;

void gui_init(const display_driver_t* drv, int screen_width, int screen_height);
void gui_set_rotation(gui_rotation_t rot);
void gui_render_blocking(const void* gui_screen);
bool gui_render_start_async(const void* gui_screen);
void gui_poll(void);
void gui_cancel_async(void);

typedef void (*gui_render_complete_cb_t)(void* ctx, int result);
void gui_register_complete_cb(gui_render_complete_cb_t cb, void* ctx);

typedef void (*gui_event_cb_t)(int widget_id_hash, int event_type, void* ctx);
void gui_register_event_cb(gui_event_cb_t cb, void* ctx);

#endif // GUI_RUNTIME_H
