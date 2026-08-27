---
name: generate-waveform
description: Run Vivado behavioral simulation and open the generated waveform.
---

# Generate Waveform

Arguments: `the user's supplied request` (project path/name, optionally followed by which module to
simulate and/or a description of the stimulus)

This drives a behavioral simulation of a design and shows the resulting waveform in
Vivado's waveform viewer, using the `generate_waveform` MCP tool. It works the same way
regardless of whether the target module is combinational or sequential — only the
stimulus a testbench applies differs.

1. **Resolve the project** the same way `the `verilog-build` skill` does: if `the user's supplied request` gives a
   path to an existing `.xpr`, use it directly; if it's a bare name, call `list_projects`
   and match by name; if empty/ambiguous, call `list_projects` and ask.

2. **Figure out which module to simulate.** If not obvious from `the user's supplied request`, ask. Read
   the module's source file so you know its ports (names, widths, and whether it has a
   `clk`/`clock` port — that's what determines combinational vs. sequential below).

3. **Ask the user how they want stimulus provided** — this is the required first choice:
   - **User-supplied input**: ask them to describe the input sequence/vectors they want
     (e.g. "cycle through all 4 mux select values", "reset for 20ns then count for 10
     cycles"), and write a testbench implementing exactly that.
   - **Auto-generated stimulus**: write sensible default stimulus yourself, based on the
     module's ports:
     - **Combinational** (no `clk`/`clock` port): exhaustively toggle every input
       combination if total input width is small (roughly ≤ 6 bits); otherwise sweep
       each input independently plus a handful of representative combinations, with a
       short delay between each so transitions are visible on the waveform.
     - **Sequential** (has a `clk`/`clock` port): generate a clock (e.g. 10ns period)
       and, if there's a `reset`/`rst` port, assert it for a few cycles then release it,
       then drive the remaining inputs through enough cycles to show real state
       transitions.
   If the user has no preference, default to auto-generated.

4. **Write the testbench** with the Write tool under `<project_dir>/sim/` (create the
   directory if it doesn't exist), named `tb_<module>.v` or `.sv` to match the DUT's
   language. Show it to the user before simulating — don't run stimulus they haven't
   seen.

5. **Call `generate_waveform`** with `project_path`, `testbench_file` (the new file's
   absolute path), `top_module` (the testbench module's own name, not the DUT), and a
   `sim_time` sized to cover every vector/cycle the testbench drives plus a little
   margin. Default `gui=true` so the waveform opens in Vivado.

6. **Report the result:**
   - If it returns an `error`, show the `log_tail` plainly and stop — don't retry
     blindly or rewrite the testbench without asking.
   - On success, confirm the simulation ran for `sim_time`, mention the `waveform_db`
     and `wave_config` paths, and report `gui_status`. If `gui_status` starts with
     `ERROR`, say the waveform data is still saved to disk and can be opened manually in
     Vivado (open the project, then use the Tcl console: `open_wave_database
     <waveform_db>`) even though the live window didn't pop up.

7. To re-run with different stimulus, just repeat from step 3 with a new or edited
   testbench file — no need to touch the Vivado project itself.

