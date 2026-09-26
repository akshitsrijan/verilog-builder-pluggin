---
name: iverilog-waveform
description: Simulate an Icarus Verilog module and open its waveform in GTKWave, writing the testbench if there isn't one.
---

# Iverilog Waveform

Show the user what their design actually *does* over time: simulate a module and open a
populated GTKWave window. The user does not need to have written a testbench - if the
project doesn't have one for the module, the tooling writes it.

Arguments: `the user's supplied request` (project path/name, optionally which module to look at
and/or a description of the stimulus they want)

1. **Resolve the project** the same way `the `iverilog-build` skill` does: a directory
   containing `.ivproj.json` (or the manifest itself) is used directly; a bare name is
   matched via `list_projects`; if it's empty or ambiguous, call `list_projects` and ask.

2. **Decide which module.** If `the user's supplied request` names one, use it. Otherwise use the
   project's `top` and say which one you picked. Read that module's source so you can
   describe its ports, and note whether it has a `clk`/`clock` port - that's what makes it
   sequential rather than combinational, and it changes what the stimulus looks like.

3. **Handle stimulus.** The default is auto-generated, and for a beginner that is usually
   the right answer - say so rather than making them invent vectors.
   - If they described the stimulus they want (e.g. "reset for 4 cycles then count to 15",
     "cycle through all 4 select values"), write that testbench yourself with the Write
     tool under `<project>/tb/tb_<module>.v`, show it to them, and pass its path as
     `testbench`.
   - Otherwise let `generate_waveform_for_module` write it. It parses the module's ports
     and produces: a 100 MHz clock if there's a clock port, a reset pulse held for four
     cycles if there's a reset, an exhaustive sweep of every input combination for a small
     combinational design, or a counted clocked run for a sequential one - plus the
     `$dumpfile`/`$dumpvars`/`$finish` a VCD needs.

4. **Call `generate_waveform_for_module`** with `project_path` and `module`. It does the
   whole chain in one call: testbench -> compile -> `vvp` -> VCD -> GTKWave save file ->
   viewer. Use `cycles` to run a sequential design longer than the default 32 clocks.
   Pass `open_viewer=false` on a machine with no display.

   To write the testbench without simulating - so the user can read or edit it first -
   call `ensure_waveform_testbench` on its own, show them the file, then run
   `generate_waveform_for_module` with that `testbench`.

5. **Report the result.**
   - On failure with `diagnostics`, show them as `file:line: severity: message` and
     explain what iverilog is objecting to. Don't blindly regenerate the testbench; if the
     *design* is what's broken, point at `the `iverilog-fix` skill`.
   - On success, say whether the testbench was generated or already existed
     (`generated_testbench`), give the `vcd` and `gtkw` paths, and relay any `sim_stdout`
     (that's the design's own `$display` output).
   - **Describe the waveform in words too** - don't rely on the user seeing the window.
     Use `signals` (or `list_waveform_signals` on the VCD) to name what is being shown,
     and tie it back to what the design should do: "count runs 0->15 and wraps, one step
     per rising clock edge while `en` is high".
   - If `viewer.launched` is false, the waveform is still saved. Give them the exact
     command to open it later: `gtkwave <vcd> <gtkw>`.

6. **To look again later** without re-simulating, call `open_waveform_viewer` with the
   VCD (and the `.gtkw`, so the signals come back pre-added). To try different stimulus,
   edit the testbench under `<project>/tb/` and re-run step 4 - the project itself never
   needs touching.
