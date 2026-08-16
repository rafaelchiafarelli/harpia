# GUI DSL Design for Harpia — Draft

This file documents a proposed metalinguage (DSL), the generator tool and a minimal runtime to support GUI generation for memory constrained embedded systems (8-bit or similar) with 240×320 displays.

This document is intended to be comprehensive for Stage 1 (prototype skeleton). It covers architecture, DSL format, runtime API, driver contract, update modes (blocking / non-blocking), memory targets, rotation, asset pre-generation, build integration and next steps.

1. Goals and constraints

- Provide a small, deterministic GUI runtime in C compatible with Harpia-generated projects.
- Tool-off-device: a generator converts an authoring file (YAML/.gui) to C sources (.h/.c) and binary resources placed in flash.
- Target extremely memory constrained devices: default baseline = 2 KiB RAM available for GUI transient buffers; prefer smaller when possible.
- Display: 240×320 (portrait default), rotations 0/90/180/270 at runtime.
- Two render modes: blocking and non-blocking. The runtime MUST NOT disable global interrupts.
- Low-level display transfers (SPI/parallel) are platform responsibility. The runtime relies on a small driver contract.
- Assets (fonts, sprites) are pre-generated for the target color/depth by another conversion layer. This runtime treats them as opaque byte arrays in flash.

2. High level architecture

- GuiAdapter/ (new Harpia backend)
  - tool/ — Python generator (reads YAML/.gui and emits C sources)
  - templates/ — C/CMake templates used by the generator
  - runtime/ — minimal C runtime (gui_runtime.c/h) implementing the API and state machine for non-blocking rendering
  - docs/ — DESIGN.md, README
- Output from tool-off-device
  - gui_defs.h - const data structures describing screens and widgets
  - gui_resources.c - const arrays with bitmaps, glyph atlases, palette tables
  - gui_gen.c - optional glue helpers to instantiate screens
  - CMakeLists.txt snippet to include in generated project

3. DSL (recommended YAML)

- Simple, declarative. Example:

screen:
  id: main
  size: [240, 320]
  background: "#000000"
  widgets:
    - type: label
      id: title
      pos: [10,8]
      text: "Status"
      font: font_6x8
      color: "#FFFFFF"
    - type: image
      id: logo
      pos: [80,40]
      src: assets/logo.png
    - type: button
      id: btn_ok
      pos: [70,260]
      size: [100,40]
      text: "OK"
      on_press: app_on_ok

- Widgets supported (initial set): label, button, image, progress, rectangle, container (absolute), list (static), spacer.
- Resources: images and fonts are referenced by name; the tool will convert to arrays and emit indices.
- Event binding: widgets can reference application callback names (symbols) which the application implements in C.

4. Output data structures (C)

- gui_defs.h will declare lightweight structures living in flash (const):
  - GuiScreen { id, width, height, pointer to widget array, widget_count }
  - GuiWidget { type, id_hash, x, y, w, h, resource_index }
- Strings are stored in const char arrays if necessary; prefer IDs/indices over strings to save RAM.

5. Runtime API

Header-level prototypes (C):

// types
typedef enum { GUI_ROT_0=0, GUI_ROT_90=1, GUI_ROT_180=2, GUI_ROT_270=3 } gui_rotation_t;

typedef enum { GUI_OK=0, GUI_ERR=1 } gui_result_t;

// driver contract
typedef struct display_driver_t {
    // Synchronous write of a rectangular region. Must not disable global IRQs.
    // Implementations must keep writes short when blocking. Returns GUI_OK on success.
    gui_result_t (*draw_area_sync)(const uint8_t* data, int x, int y, int width, int height);
    // Non-blocking: start an asynchronous transfer. If transfer queued/started, return GUI_OK.
    // The driver must provide a display_busy() function to indicate activity.
    gui_result_t (*draw_area_async)(const uint8_t* data, int x, int y, int width, int height);
    bool (*display_busy)(void);
} display_driver_t;

// runtime API
void gui_init(const display_driver_t* drv, int screen_width, int screen_height);
void gui_set_rotation(gui_rotation_t rot);

// Blocking render: draws a whole screen synchronously (may call draw_area_sync).
void gui_render_blocking(const void* gui_screen);

// Non-blocking render: starts an async render; must call gui_poll repeatedly until completion.
// Returns true if started successfully.
bool gui_render_start_async(const void* gui_screen);

// Call periodically to advance the rendering state machine. It performs at most one tile/step and returns immediately.
// When rendering completes, an optional completion callback (registered by gui_register_complete_cb) is called.
void gui_poll(void);

void gui_cancel_async(void);

typedef void (*gui_render_complete_cb_t)(void* ctx, gui_result_t result);
void gui_register_complete_cb(gui_render_complete_cb_t cb, void* ctx);

// Event handling
// GUI runtime recognizes raw input events (touch, button) and maps them to widget id or event id.
// The application provides a callback:
typedef void (*gui_event_cb_t)(int widget_id_hash, int event_type, void* ctx);
void gui_register_event_cb(gui_event_cb_t cb, void* ctx);

6. Non-blocking rendering model

- State machine iterates widgets and primitives; each draw operation is subdivided into tiles or scanlines limited by a configurable buffer.
- Default tile configuration for 2 KiB RAM target: tile width = 16px, tile height = 8px. For RGB565 (2 bytes/pixel) a 16×8 tile = 512 bytes which fits within 2 KiB with room for other transient data.
- Steps per gui_poll()
  1. If display_busy(), return immediately (optionally call driver display_busy to wait short periods).
  2. Prepare next tile: decode sprite/glyph data for the tile into a small static buffer.
  3. Call driver->draw_area_async(buffer, x, y, w, h).
  4. Return to caller quickly.
- The driver may not support async. In that case, draw_area_async should call draw_area_sync internally but must keep writes limited in size. gui_poll still slices work to small tiles.
- Important: The runtime MUST NOT disable interrupts. Any waiting must be cooperative.

7. Memory and resources

- All static GUI definitions and assets are const in flash (ROM). The runtime uses a small static tile buffer (configurable via macro) allocated as a single static array.
- No dynamic allocation: runtime avoids malloc/free.
- Font rendering: pre-generated glyph atlas with per-glyph offset table. The tool will pack glyphs for the configured fonts.
- Images: stored as palettized or direct color arrays. Color conversion is out-of-scope for this runtime: an earlier pipeline should convert assets into target color format.
- Compression: Stage 1 tool will not implement advanced compression. Later stages can add RLE or block decompression.

8. Rotation

- Default: runtime stores rotation enum and applies coordinate transforms when issuing draw_area ops.
- Because CPU is very constrained, the generator will pre-generate rotated variants of assets for 0/90/180/270 when pre_generate_rotation = true.
- When pre-generated assets exist, the runtime simply references the proper asset variant and issues same-coordinate writes (faster, simpler).

9. Driver contract detail

- The driver is responsible for: framing commands, managing SPI/parallel timing, handling chip select, and optional DMA.
- The driver must implement both sync and async functions (async can be a wrapper to sync).
- The driver MUST NOT disable global IRQs and should keep SPI transfers short. If platform requires large blocking transfers, the driver should internally slice them.

10. Build and Harpia integration

- The generator will follow Harpia patterns: it will emit code under the generated project's Assets/ folder and add a CMakeLists snippet to include runtime sources.
- GuiAdapter/templates/CMakeLists.txt will expose variables to control tile buffer size and include gui_runtime.c/h.
- The runtime is plain C and integrates into CMake-based projects. Harpia's generated project will include gui_runtime sources and gui_defs.h.

11. Testing strategy (Stage 1)

- Host mock driver: a small display driver that records draw calls and simulates display_busy. This allows unit tests on the host (Linux) without MCU hardware.
- Golden outputs: the generator will have golden snapshots for gui_defs.h and small resources created from example YAML.

12. Step 1 prototype scope (what will be committed on branch)

- a minimal generator (Python) that parses a small YAML example and emits gui_defs.h and gui_resources.c with simple C structs.
- a minimal gui_runtime.h/.c with API stubs and a simple state machine for non-blocking rendering using a small static tile buffer.
- a mock display driver in C for host testing.
- a sample YAML file in Assets/gui_demo/demo.yml.
- DESIGN.md (this document) and README.md to explain how to run the prototype.

13. Next steps (future work)

- implement asset packing (glyph atlas, sprite atlas), compression and block decompression in the runtime.
- add pre-generation of rotated assets during the tool-off-device step.
- implement advanced widgets (lists with scrolling, simple animations) and layout engine with anchors.
- add CI tests (golden) and a CMake test harness that compiles a host mock driver demo.

Appendix: sample YAML (same as above)

screen:
  id: main
  size: [240, 320]
  background: "#000000"
  widgets:
    - type: label
      id: title
      pos: [10,8]
      text: "Status"
      font: font_6x8
      color: "#FFFFFF"
    - type: button
      id: btn_ok
      pos: [70,260]
      size: [100,40]
      text: "OK"
      on_press: app_on_ok


