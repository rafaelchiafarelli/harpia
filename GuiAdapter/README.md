# GuiAdapter Prototype README

This folder contains a Stage-1 prototype skeleton for a GUI DSL backend (GuiAdapter) for Harpia.

Contents:
- DESIGN.md — comprehensive design (authoritative, English).
- tool/generator.py — minimal Python generator (YAML => C structs + resources).
- runtime/gui_runtime.h, runtime/gui_runtime.c — minimal runtime API and basic state machine.
- Assets/gui_demo/demo.yml — example GUI definition.

How to run (host, quick test):

1. Ensure Python environment has PyYAML. On Linux:
   pip install pyyaml

2. Run the generator against the demo YAML:
   python3 GuiAdapter/tool/generator.py Assets/gui_demo/demo.yml /tmp/gui_out

   This will create two files in /tmp/gui_out: gui_defs.h and gui_resources.c

3. Inspect the generated files. They are a starting point for wiring into a C project.

Notes:
- This prototype focuses on the generator and a minimal runtime API. It does not implement compression, tiling optimizations or full widget rendering.
- The runtime is intentionally small and uses a static tile buffer sized for very constrained RAM (2 KiB target). Adjust the buffer by editing GUI_TILE_BUFFER_SIZE in gui_runtime.c

