# Codex walkthrough

This walkthrough creates, synthesizes, and simulates a small Verilog design through the Codex plugin.

## Before you start

1. Make sure Vivado is installed and that `vivado` can be run from a terminal.
2. Make sure the MCP server's Python environment has the `mcp` package installed.
3. Install or load the local `codex` plugin in Codex.

## 1. Create a project

Ask Codex to use the `verilog-new` skill. For example:

> Create a Vivado project named `full_adder` for a 1-bit full adder with inputs `a`, `b`, and `cin`, and outputs `sum` and `cout`.

Codex will ask whether to create RTL from the description or use existing source files. For a new design, it writes the RTL, shows it for review, and then creates the `.xpr` project. The default target part is `xc7a35tcpg236-1`; change it if your board uses another part.

## 2. Start a build

Ask:

> Build the `full_adder` Vivado project with synthesis and show live progress.

The `verilog-build` skill resolves the project, starts the build, and reports each module's state. Choose one of these modes if prompted:

- `synth` — synthesis and timing analysis only; fastest option.
- `full` — includes implementation and routing; slower but closer to final hardware results.

Leave the GUI enabled if you want Vivado to display the synthesized schematic and final run.

## 3. Handle an error or make a change

If synthesis fails, Codex shows the failing module, source file, and Vivado error. Review the suggested fix, then explicitly approve it or provide your own instruction. Codex applies the revised file and resumes the build.

To change RTL while a build is running, ask:

> Pause the `full_adder` build and change the design to use structural gate instances.

The `verilog-modify` skill waits for the current module to finish before pausing, so it does not interrupt Vivado mid-synthesis.

## 4. Check status and timing

At any time, ask:

> Show the status of the `full_adder` build.

After the build completes, ask:

> Analyze timing for the `full_adder` project.

The timing report explains WNS, TNS, WHS, and THS. Negative slack indicates a timing violation.

## 5. Generate a waveform

Ask:

> Generate a behavioral waveform for `full_adder`.

Provide an existing testbench or ask Codex to create one. The simulation output is written by Vivado and can be opened in its GUI for waveform inspection.

## Useful prompts

- “Create a Vivado project from these existing Verilog files.”
- “Build this project in full mode without opening the GUI.”
- “Why is the current build blocked? Propose a fix but wait for my approval.”
- “Show the module log for the failed module.”
- “Generate a waveform with a testbench that tests every input combination.”
