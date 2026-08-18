# Verilog Builder

Verilog Builder is a local Vivado workflow that lets an AI assistant create FPGA projects, build designs module-by-module, stream synthesis progress, inspect timing, pause safely for RTL changes, and generate simulation waveforms.

It contains two editions that share the same Vivado orchestration logic:

- `commands/`, `.claude-plugin/`, `mcp_server/`, and `tcl/` — the Claude Code plugin.
- [`codex/`](codex/) — the Codex plugin, with its own MCP server, Tcl assets, and skills.

## What it does

- Creates a Vivado project from new or existing Verilog/SystemVerilog sources.
- Synthesizes modules one at a time, showing live module status and Vivado log output.
- Pauses on a synthesis error, presents the failing file and error, and resumes after a confirmed fix.
- Pauses at a safe module boundary when you want to change RTL during a running build.
- Reports WNS, TNS, WHS, and THS after a completed build.
- Runs behavioral simulation and opens the generated waveform in Vivado.

## Requirements

- Xilinx Vivado installed locally and available as `vivado` on your `PATH`, or configured through the `VIVADO_BIN` environment variable.
- Python 3 with the `mcp` package available to the selected MCP-server interpreter.

## Codex edition

The Codex plugin lives in [`codex/`](codex/). Its main components are:

- [`codex/.codex-plugin/plugin.json`](codex/.codex-plugin/plugin.json) — plugin metadata.
- [`codex/.mcp.json`](codex/.mcp.json) — local MCP server configuration.
- [`codex/skills/`](codex/skills/) — seven assistant workflows:
  `verilog-new`, `verilog-build`, `verilog-status`, `verilog-timing`,
  `verilog-fix`, `verilog-modify`, and `generate-waveform`.
- [`codex/mcp_server/`](codex/mcp_server/) and [`codex/tcl/`](codex/tcl/) — the Vivado backend.

For an end-to-end example, see the [Codex walkthrough](codex/WALKTHROUGH.md).

## Claude Code edition

The original Claude Code edition exposes the same workflow as slash commands:

```text
/verilog-new
/verilog-build
/verilog-status
/verilog-timing
/verilog-fix
/verilog-modify
/generate_waveform
```

## Build lifecycle

1. Create or select a `.xpr` Vivado project.
2. Start a synthesis-only or full implementation build.
3. Watch each module progress from pending to running to complete.
4. Resolve any blocked module using a reviewed RTL fix, then resume.
5. Review timing and, when needed, generate a testbench waveform.

## Notes and limitations

- One build can run per project at a time.
- Module names are inferred from the Vivado compile order and assume roughly one module per RTL file.
- Full mode includes implementation and routing; synthesis mode is quicker and is the default for early feedback.
- Build state and logs are stored under the project's `.verilog_builder/` directory.
