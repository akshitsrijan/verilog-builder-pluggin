---
description: Create a new Icarus Verilog project just by describing the design in English - no files to write by hand, no vendor tools
argument-hint: "[optional: project name and/or what you want to build]"
---

Create a new Icarus Verilog project end-to-end from a prompt, using the iverilog-builder MCP
tools. Nothing here needs Vivado or any vendor toolchain - just `iverilog` and `vvp`.

A "project" is deliberately simple: a directory with a `.ivproj.json` manifest listing the
sources. There is no wizard and no `.xpr`.

Arguments: `$ARGUMENTS` (optional project name and/or a description of the design)

**Assume the user is new to Verilog unless they show otherwise.** Don't ask them about
things they have no basis to answer (Verilog standard, include dirs, which file is "top") -
pick a sensible default and say what you picked in one short line.

1. **Work out what they want to build.** If `$ARGUMENTS` already describes a design ("a 4-bit
   ripple carry adder", "a traffic light FSM"), go with it. If it's just a name or empty, ask
   what they want the circuit to do, in plain English. Only ask about the interface (inputs,
   outputs, widths, clocked or not) if their description genuinely leaves it open - otherwise
   choose the conventional interface and state your choice.

2. **Pick a project name and location.** Derive the name from the design if not given. Default
   the location to `~/<project_name>/` - this matches every other project on this machine.
   Don't ask about the path unless they want it somewhere specific.

3. **Call `create_project`** with `project_name` and `project_dir`. Leave `source_files` empty -
   you're about to write the RTL with `write_module`, which is the normal path for a new
   design. Only pass `source_files` if the user is wrapping `.v` files they already have.

4. **Write the RTL with `write_module`.** One call per module, `filename` like `adder.v`
   (it lands under `<project>/sources/` automatically). Then:
   - **Show the user the Verilog you wrote and explain it briefly** - a couple of lines on
     what each part does. This is the moment a beginner actually learns something, and it's
     their chance to say "no, I wanted it to reset synchronously" before anything is built.
   - If the design naturally splits into several modules (e.g. a full adder instantiated by a
     ripple-carry adder), write each as its own module and say why it's split that way.

5. **Write a testbench too, with `write_module`.** Don't ask whether they want one - a design
   nobody simulated is a design nobody knows works. Name it `tb_<module>.v` and make sure it:
   - drives a sensible set of stimulus for this specific design (all input combinations for
     small combinational logic; reset then a run of clock cycles for sequential logic),
   - calls `$dumpfile("<name>.vcd")` and `$dumpvars(0, tb_<module>);` so a waveform exists,
   - `$display`s what happened so the simulation output is readable,
   - **always ends with `$finish`** - without it `vvp` runs forever and hits the timeout.

6. **Build and simulate it right away.** Call `start_build` and poll `get_build_status` the
   same way `/iverilog-build` does (see that command for the live-progress rendering and the
   blocked/fix/resume flow). Don't make the user run a second command to find out whether
   what you just wrote actually compiles.

7. **When it completes**, show the simulation output from `simulation.stdout` and explain what
   it proves in plain English ("the counter reached 15 and wrapped to 0, so the rollover
   works"). Mention the `.vcd` path if one was produced, and tell them they can re-run any
   time with `/iverilog-build <project_name>`.
