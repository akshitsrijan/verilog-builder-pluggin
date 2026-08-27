---
name: iverilog-new
description: Create a new Icarus Verilog project from a design description or existing Verilog sources.
---

# Iverilog New

Create a new Icarus Verilog project end-to-end from a prompt, using the iverilog-builder MCP
tools. This is the counterpart to `the `iverilog-build` skill`: that one only works on a project that
already exists on disk; this one creates the project in the first place.

A "project" here is just a directory with a `.ivproj.json` manifest in it - no vendor tooling,
no GUI, nothing for the user to install or click through. The whole point is that a beginner
can describe what they want in plain English and end up with working, simulated Verilog.

Arguments: `the user's supplied request` (optional project name and/or a description of the design)

1. **Figure out where the RTL comes from.** Unless `the user's supplied request` already makes it
   obvious, ask the user whether they want to:
   - **describe a design in English** and have you write the Verilog for it (the common case -
     they never have to create a file themselves), or
   - point you at existing `.v`/`.sv` file(s) already on disk to wrap in a new project.

2. **Resolve project name and location.** If not given, ask for a project name. Default the
   directory to `~/<project_name>/` unless the user wants somewhere else.

3. **Create the project first, empty.** Call `create_project` with `project_name` and
   `project_dir`. Leave `source_files` empty if you're about to write the modules yourself;
   pass the absolute paths if you're adopting existing files. If it returns
   `ok: false`, show the `error` plainly (common cause: a project already exists there) and
   stop - don't retry blindly.

4. **If writing new RTL: use `write_module`, one call per module.** Do not create files with
   the Write tool - `write_module` writes the file *and* registers it in the manifest in one
   step, which is what keeps the "never touch a build file" promise.
   - Show the user each module's Verilog and explain briefly what it does, in beginner terms
     (what the ports mean, what the always/assign block is doing). They should be able to
     follow the design, not just receive it.
   - Ask before moving on if the design has real choices in it (bit width, reset polarity,
     synchronous vs asynchronous reset) rather than silently picking.

5. **Write a testbench too**, with `write_module(..., is_testbench=True)`. Name it `tb_<module>`.
   A beginner-friendly testbench should:
   - drive a clear, short stimulus sequence,
   - `$display` what it's checking so the simulation prints readable results,
   - call `$dumpfile("<name>.vcd")` and `$dumpvars(0, tb_<module>)` so a waveform exists,
   - end with `$finish` (a testbench with no `$finish` runs forever).

6. **Build it.** Call `start_build` and stream progress exactly like `the `iverilog-build` skill`
   does from its step 3 onward. If a module errors, follow the fix flow there.

7. **Simulate it.** Once the build completes, call `run_simulation`. Show the user the
   `stdout` - that's their `$display` output, the proof the design actually works - and
   mention the `vcd` path if one was produced, so they can view the waveform.

8. **Wrap up** by telling the user the project path and that they can re-run
   `the `iverilog-build` skill` or `the `iverilog-status` skill` on it any time.
