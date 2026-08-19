/* Minimal GUI runtime - Stage 1 prototype */
#include "gui_runtime.h"
#include <stdio.h>
#include <string.h>

static const display_driver_t* g_driver = NULL;
static int g_screen_w = 240;
static int g_screen_h = 320;
static gui_rotation_t g_rotation = GUI_ROT_0;

#define GUI_TILE_BUFFER_SIZE 2048
static uint8_t g_tile_buffer[GUI_TILE_BUFFER_SIZE];

static bool g_rendering = false;
static const void* g_active_screen = NULL;
static gui_render_complete_cb_t g_complete_cb = NULL;
static void* g_complete_ctx = NULL;

void gui_init(const display_driver_t* drv, int screen_width, int screen_height) {
    g_driver = drv;
    g_screen_w = screen_width;
    g_screen_h = screen_height;
}

void gui_set_rotation(gui_rotation_t rot) {
    g_rotation = rot;
}

void gui_render_blocking(const void* gui_screen) {
    // Very small demo: walk widgets and call driver sync (no real parsing here)
    if (!g_driver || !g_driver->draw_area_sync) return;
    // For prototype, we simply call the driver with an empty buffer to indicate a draw
    (void)gui_screen;
    g_driver->draw_area_sync(g_tile_buffer, 0, 0, g_screen_w, g_screen_h);
}

bool gui_render_start_async(const void* gui_screen) {
    if (!g_driver) return false;
    if (g_rendering) return false;
    g_rendering = true;
    g_active_screen = gui_screen;
    // Kick off first tile in gui_poll
    return true;
}

void gui_poll(void) {
    if (!g_rendering) return;
    if (g_driver && g_driver->display_busy && g_driver->display_busy()) return;
    // Prototype: issue a single async draw to cover the full screen
    if (g_driver && g_driver->draw_area_async) {
        g_driver->draw_area_async(g_tile_buffer, 0, 0, g_screen_w, g_screen_h);
    }
    g_rendering = false;
    if (g_complete_cb) g_complete_cb(g_complete_ctx, GUI_OK);
}

void gui_cancel_async(void) {
    g_rendering = false;
}

void gui_register_complete_cb(gui_render_complete_cb_t cb, void* ctx) {
    g_complete_cb = cb;
    g_complete_ctx = ctx;
}

void gui_register_event_cb(gui_event_cb_t cb, void* ctx) {
    (void)cb; (void)ctx;
    // Prototype: no event system implemented
}
