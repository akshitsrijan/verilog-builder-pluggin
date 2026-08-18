---
description: Draw the RTL schematic of an Icarus Verilog design with yosys - the open-source equivalent of Vivado's elaborated-design view
argument-hint: "[project-path-or-name] [module]"
---

Generate and show a schematic of a Verilog design using the iverilog-builder MCP tools.
No Vivado, no GUI wizard - yosys elaborates the design and netlistsvg draws it.

Argument: `$ARGUMENTS` - may name a project, a module, both, or be empty.

1. **Resolve the project.**
   - A path to a directory containing `.ivproj.json` is used directly.
   - A bare name: call `list_projects` and match by name.
   - Empty: call `list_projects` (default search root `~`) and ask which project.
   - Nothing found: point at `/iverilog-new` rather than constructing a project by hand.

2. **Resolve the module.** If `$ARGUMENTS` names a module as well, use it as `top`.
   Otherwise leave `top` empty - the project's own top module is used. If the user asked
   about a specific block ("show me the full adder inside it"), pass that module name:
   any module in the design can be drawn on its own, not just the top.

3. **Generate it.** Call `generate_schematic` with the project path and `level="rtl"` -
   this is the default and it is what you want. RTL level shows adders, muxes, and
   registers as recognisable blocks. Only pass `level="gate"` if the user explicitly asks
   about gates, LUTs, or the synthesised netlist; that view runs a full synthesis and is
   much larger.
   - Default `fmt="svg"`. Use `"png"` if the user wants something to paste into a
     document, `"dot"` if they want to explore it in `xdot`, `"json"` only if they asked
     for the raw netlist.

4. **Show it.** Report the absolute `schematic` path, then call `open_schematic` with it.
   If that returns `ok: false` because there's no display, that's not a failure worth
   apologising for - just tell them where the file is and that any browser opens an SVG.

5. **Explain what they're looking at.** This is the part that matters for a beginner:
   - Say what the top-level boxes are and how many of each, using `get_netlist_stats`
     (`cell_types` gives you the counts - e.g. four `full_adder` instances, twelve `$and`).
   - Point out that instance names in the drawing are the ones from their Verilog.
   - If a cell they expected is missing, say so - `opt_clean` removes logic that drives
     nothing, which is usually a real bug in the design worth mentioning.

6. **On failure.** `generate_schematic` returns `errors` as `{file, line, severity,
   message}`, same shape as the build tools:
   - Quote the file and line, read that part of the source, and show the offending line.
   - Explain the message in plain English. yosys says things like "Module `\\foo'
     referenced ... is not part of the design", which just means a source file wasn't
     registered - offer `add_sources`.
   - If the error is that the module name isn't in the project, `list_design_modules`
     gives you the real names; show them and ask which one they meant.

Keep it short: the schematic is the answer, and a couple of sentences saying what it shows.
