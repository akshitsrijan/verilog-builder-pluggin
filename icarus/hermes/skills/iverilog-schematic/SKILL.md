---
name: iverilog-schematic
description: Draw the RTL schematic of a Verilog design with yosys - the open-source equivalent of Vivado's elaborated-design view.
---

# Iverilog Schematic

Turn the user's Verilog into a picture. "Show me the schematic of my adder" should
end with a schematic on screen and an explanation of what's in it - no yosys
scripts, no GUI steps, nothing for the user to run by hand.

Project argument: `the user's supplied request`

1. **Resolve the project.** Same as `the `iverilog-build` skill`: a directory holding
   `.ivproj.json` (or the manifest) is used directly; a bare name is matched via
   `list_projects`; if empty, call `list_projects` and ask which project.

2. **Pick the top module.** If the user named a module ("the schematic of the full
   adder"), pass it as `top`. Otherwise omit `top` and let the project's own top be
   used. If you're unsure what exists, call `list_design_modules` first - it's cheap.

3. **Generate.** Call `generate_schematic` with the project path.
   - Leave `level` at `"rtl"` unless the user explicitly asks for gates. The RTL view
     keeps adders, muxes and registers as recognisable blocks; the gate view
     (`level="gate"`) flattens the design into AND/OR/XOR primitives and is only
     readable for small modules.
   - Leave `fmt` at `"svg"`. Use `"png"` only if the user asks for an image file they
     want to paste somewhere, `"dot"`/`"json"` only if they want the raw data.
   - Output lands in `<project>/build/schematic/<top>_<level>.svg`.

4. **Show it.** Call `open_schematic` with the returned `path` so it pops up in the
   user's viewer. If it comes back `ok: false` with a no-display message, that is not
   a failure - just tell the user where the file is and carry on.

5. **Explain the picture.** This is the part that makes the schematic useful. Use the
   returned `stats` (also available on its own from `get_netlist_stats`) and say, in
   plain terms:
   - how many instances of each sub-module the top contains (`cell_types` - e.g. an
     `adder4` showing `full_adder: 4` is the ripple-carry chain the user wrote);
   - whether anything is sequential - `dff`/`adff`/`sdff` cells mean flip-flops, so
     the design is clocked; a design with none is purely combinational;
   - `memories` / `memory_bits` when a RAM or register file was inferred;
   - anything surprising: far more cells than expected usually means a wide operator
     or an accidental replication inside a loop.

6. **On failure.** `generate_schematic` returns `ok: false` with `diagnostics` in the
   same `{file, line, severity, message}` shape the build tools use. Read the offending
   source around that line and explain it. The two common ones:
   - **top module not found** - the reply lists the `modules` yosys did see; offer them
     and re-run with the right `top`.
   - **elaboration errors** (undeclared identifier, port width mismatch, a module
     instantiated but never defined) - these are real design errors and worth fixing
     via `the `iverilog-fix` skill` even though they surfaced here.

Keep `warnings` in mind but don't dump them all - mention only ones that change what
the schematic means (an inferred latch, a truncated assignment, an undriven wire).
