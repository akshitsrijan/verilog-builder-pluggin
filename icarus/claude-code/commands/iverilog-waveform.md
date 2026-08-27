---
description: Simulate a module and open its waveform in GTKWave - the testbench is written for you
argument-hint: "[project-path-or-name] [optional: module to simulate / stimulus description]"
---

Arguments: `$ARGUMENTS` (project path/name, optionally followed by which module to look
at and/or a description of the stimulus you want)

This simulates a module with Icarus Verilog and opens the resulting waveform in GTKWave
with the signals already added. The user does not need to write a testbench or drag
anything into the viewer - `generate_waveform` does both.

1. **Resolve the project** the same way `/iverilog-build` does: a directory containing
   `.ivproj.json`, a name matched via `list_projects`, or ask if it's empty/ambiguous.

2. **Figure out which module to show.** If `$ARGUMENTS` doesn't say, use the project's
   `top`, or call `list_projects`/`get_build_status` and ask if there are several
   candidates. Read the module's source so you can explain its ports afterwards.

3. **Decide where the stimulus comes from:**
   - If the user described the stimulus they want, write that testbench yourself with
     `write_module` (name it `tb_<module>.v`, and it must call `$dumpfile`/`$dumpvars`
     and `$finish`), show it to them, then pass it as `testbench` to `generate_waveform`.
   - Otherwise let the tool generate one. Call `ensure_testbench` first if you want to
     read the generated stimulus and describe it before anything runs; otherwise
     `generate_waveform` will write it as part of the same call. The generated testbench
     drives a clock if the module has one, pulses any reset, sweeps every input
     combination for small combinational designs, and runs `cycles` clocked iterations
     otherwise.

4. **Call `generate_waveform`** with `project_path` and `module`. Leave `open_viewer`
   true so GTKWave pops up; raise `cycles` if the design needs longer to show something
   interesting.

5. **Report the result:**
   - On failure, quote the `errors` list (or `stderr`) plainly and stop - don't rewrite
     the testbench and retry without asking.
   - On success, say whether the testbench was generated (`testbench_generated`) and
     where it lives, summarise `sim_stdout`, and name the `vcd` and `gtkw` paths.
   - If `viewer_launched` is false, the waveform data is still on disk: report
     `viewer_error`, then describe the waveform in words using `signals` (and
     `list_vcd_signals` for anything else in the dump) so a headless user still gets the
     answer. They can open it later themselves with `gtkwave <vcd> <gtkw>`.

6. To try different stimulus, edit the testbench (it is a normal project file) or call
   `ensure_testbench` with `force=true` to regenerate it, then run `generate_waveform`
   again. Use `open_waveform` on its own to re-open a VCD that was already produced by
   `/iverilog-build`.
