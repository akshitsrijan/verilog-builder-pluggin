<p align="center">
  <img src="docs/assets/banner.svg" alt="Verilog Builder" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Vivado-2023.2-E5312B?logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyBmaWxsPSIjZmZmZmZmIiByb2xlPSJpbWciIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48dGl0bGU%2BWGlsaW54PC90aXRsZT48cGF0aCBkPSJNOCAxOGw1LjI0MSA2SDUuNTg2TC4zNDUgMThsNS4yNDEtNkwuMzQ1IDZsNS4yNDEtNmg3LjY1NUw4IDZsNS4yNDEgNkw4IDE4ek0yMy42NTUgMEgxMy4yNDFsNS4yNDEgNiA1LjE3My02ek0xMy4yNDEgMjRoMTAuNDE0bC01LjE3Mi02LTUuMjQyIDZ6Ii8%2BPC9zdmc%2B" alt="Vivado">
  <img src="https://img.shields.io/badge/Icarus_Verilog-iverilog%20%7C%20vvp-0F766E" alt="Icarus Verilog">
  <img src="https://img.shields.io/badge/Yosys-schematics-2563EB" alt="Yosys">
  <img src="https://img.shields.io/badge/GTKWave-waveforms-7C3AED?logo=gtk&logoColor=white" alt="GTKWave">
  <img src="https://img.shields.io/badge/Verilog-SystemVerilog-1F2937" alt="Verilog">
  <img src="https://img.shields.io/badge/Tcl-scripting-E4A11B" alt="Tcl">
  <img src="https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/MCP-server-000000?logo=modelcontextprotocol&logoColor=white" alt="MCP">
  <br>
  <img src="https://img.shields.io/badge/Claude_Code-plugin-D97757?logo=claude&logoColor=white" alt="Claude Code">
  <img src="https://img.shields.io/badge/Codex-plugin-412991?logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyBmaWxsPSIjZmZmZmZmIiByb2xlPSJpbWciIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48dGl0bGU%2BT3BlbkFJPC90aXRsZT48cGF0aCBkPSJNMjIuMjgxOSA5LjgyMTFhNS45ODQ3IDUuOTg0NyAwIDAgMC0uNTE1Ny00LjkxMDggNi4wNDYyIDYuMDQ2MiAwIDAgMC02LjUwOTgtMi45QTYuMDY1MSA2LjA2NTEgMCAwIDAgNC45ODA3IDQuMTgxOGE1Ljk4NDcgNS45ODQ3IDAgMCAwLTMuOTk3NyAyLjkgNi4wNDYyIDYuMDQ2MiAwIDAgMCAuNzQyNyA3LjA5NjYgNS45OCA1Ljk4IDAgMCAwIC41MTEgNC45MTA3IDYuMDUxIDYuMDUxIDAgMCAwIDYuNTE0NiAyLjkwMDFBNS45ODQ3IDUuOTg0NyAwIDAgMCAxMy4yNTk5IDI0YTYuMDU1NyA2LjA1NTcgMCAwIDAgNS43NzE4LTQuMjA1OCA1Ljk4OTQgNS45ODk0IDAgMCAwIDMuOTk3Ny0yLjkwMDEgNi4wNTU3IDYuMDU1NyAwIDAgMC0uNzQ3NS03LjA3Mjl6bS05LjAyMiAxMi42MDgxYTQuNDc1NSA0LjQ3NTUgMCAwIDEtMi44NzY0LTEuMDQwOGwuMTQxOS0uMDgwNCA0Ljc3ODMtMi43NTgyYS43OTQ4Ljc5NDggMCAwIDAgLjM5MjctLjY4MTN2LTYuNzM2OWwyLjAyIDEuMTY4NmEuMDcxLjA3MSAwIDAgMSAuMDM4LjA1MnY1LjU4MjZhNC41MDQgNC41MDQgMCAwIDEtNC40OTQ1IDQuNDk0NHptLTkuNjYwNy00LjEyNTRhNC40NzA4IDQuNDcwOCAwIDAgMS0uNTM0Ni0zLjAxMzdsLjE0Mi4wODUyIDQuNzgzIDIuNzU4MmEuNzcxMi43NzEyIDAgMCAwIC43ODA2IDBsNS44NDI4LTMuMzY4NXYyLjMzMjRhLjA4MDQuMDgwNCAwIDAgMS0uMDMzMi4wNjE1TDkuNzQgMTkuOTUwMmE0LjQ5OTIgNC40OTkyIDAgMCAxLTYuMTQwOC0xLjY0NjR6TTIuMzQwOCA3Ljg5NTZhNC40ODUgNC40ODUgMCAwIDEgMi4zNjU1LTEuOTcyOFYxMS42YS43NjY0Ljc2NjQgMCAwIDAgLjM4NzkuNjc2NWw1LjgxNDQgMy4zNTQzLTIuMDIwMSAxLjE2ODVhLjA3NTcuMDc1NyAwIDAgMS0uMDcxIDBsLTQuODMwMy0yLjc4NjVBNC41MDQgNC41MDQgMCAwIDEgMi4zNDA4IDcuODcyem0xNi41OTYzIDMuODU1OEwxMy4xMDM4IDguMzY0IDE1LjExOTIgNy4yYS4wNzU3LjA3NTcgMCAwIDEgLjA3MSAwbDQuODMwMyAyLjc5MTNhNC40OTQ0IDQuNDk0NCAwIDAgMS0uNjc2NSA4LjEwNDJ2LTUuNjc3MmEuNzkuNzkgMCAwIDAtLjQwNy0uNjY3em0yLjAxMDctMy4wMjMxbC0uMTQyLS4wODUyLTQuNzczNS0yLjc4MThhLjc3NTkuNzc1OSAwIDAgMC0uNzg1NCAwTDkuNDA5IDkuMjI5N1Y2Ljg5NzRhLjA2NjIuMDY2MiAwIDAgMSAuMDI4NC0uMDYxNWw0LjgzMDMtMi43ODY2YTQuNDk5MiA0LjQ5OTIgMCAwIDEgNi42ODAyIDQuNjZ6TTguMzA2NSAxMi44NjNsLTIuMDItMS4xNjM4YS4wODA0LjA4MDQgMCAwIDEtLjAzOC0uMDU2N1Y2LjA3NDJhNC40OTkyIDQuNDk5MiAwIDAgMSA3LjM3NTctMy40NTM3bC0uMTQyLjA4MDVMOC43MDQgNS40NTlhLjc5NDguNzk0OCAwIDAgMC0uMzkyNy42ODEzem0xLjA5NzYtMi4zNjU0bDIuNjAyLTEuNDk5OCAyLjYwNjkgMS40OTk4djIuOTk5NGwtMi41OTc0IDEuNDk5Ny0yLjYwNjctMS40OTk3WiIvPjwvc3ZnPg%3D%3D" alt="Codex">
  <img src="https://img.shields.io/badge/Hermes-agent-F59E0B" alt="Hermes">
  <img src="https://img.shields.io/badge/OpenClaw-agent-DC2626" alt="OpenClaw">
  <img src="https://img.shields.io/badge/Custom_LLM-OpenAI--compatible-10A37F?logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyBmaWxsPSIjZmZmZmZmIiByb2xlPSJpbWciIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48dGl0bGU%2BT3BlbkFJPC90aXRsZT48cGF0aCBkPSJNMjIuMjgxOSA5LjgyMTFhNS45ODQ3IDUuOTg0NyAwIDAgMC0uNTE1Ny00LjkxMDggNi4wNDYyIDYuMDQ2MiAwIDAgMC02LjUwOTgtMi45QTYuMDY1MSA2LjA2NTEgMCAwIDAgNC45ODA3IDQuMTgxOGE1Ljk4NDcgNS45ODQ3IDAgMCAwLTMuOTk3NyAyLjkgNi4wNDYyIDYuMDQ2MiAwIDAgMCAuNzQyNyA3LjA5NjYgNS45OCA1Ljk4IDAgMCAwIC41MTEgNC45MTA3IDYuMDUxIDYuMDUxIDAgMCAwIDYuNTE0NiAyLjkwMDFBNS45ODQ3IDUuOTg0NyAwIDAgMCAxMy4yNTk5IDI0YTYuMDU1NyA2LjA1NTcgMCAwIDAgNS43NzE4LTQuMjA1OCA1Ljk4OTQgNS45ODk0IDAgMCAwIDMuOTk3Ny0yLjkwMDEgNi4wNTU3IDYuMDU1NyAwIDAgMC0uNzQ3NS03LjA3Mjl6bS05LjAyMiAxMi42MDgxYTQuNDc1NSA0LjQ3NTUgMCAwIDEtMi44NzY0LTEuMDQwOGwuMTQxOS0uMDgwNCA0Ljc3ODMtMi43NTgyYS43OTQ4Ljc5NDggMCAwIDAgLjM5MjctLjY4MTN2LTYuNzM2OWwyLjAyIDEuMTY4NmEuMDcxLjA3MSAwIDAgMSAuMDM4LjA1MnY1LjU4MjZhNC41MDQgNC41MDQgMCAwIDEtNC40OTQ1IDQuNDk0NHptLTkuNjYwNy00LjEyNTRhNC40NzA4IDQuNDcwOCAwIDAgMS0uNTM0Ni0zLjAxMzdsLjE0Mi4wODUyIDQuNzgzIDIuNzU4MmEuNzcxMi43NzEyIDAgMCAwIC43ODA2IDBsNS44NDI4LTMuMzY4NXYyLjMzMjRhLjA4MDQuMDgwNCAwIDAgMS0uMDMzMi4wNjE1TDkuNzQgMTkuOTUwMmE0LjQ5OTIgNC40OTkyIDAgMCAxLTYuMTQwOC0xLjY0NjR6TTIuMzQwOCA3Ljg5NTZhNC40ODUgNC40ODUgMCAwIDEgMi4zNjU1LTEuOTcyOFYxMS42YS43NjY0Ljc2NjQgMCAwIDAgLjM4NzkuNjc2NWw1LjgxNDQgMy4zNTQzLTIuMDIwMSAxLjE2ODVhLjA3NTcuMDc1NyAwIDAgMS0uMDcxIDBsLTQuODMwMy0yLjc4NjVBNC41MDQgNC41MDQgMCAwIDEgMi4zNDA4IDcuODcyem0xNi41OTYzIDMuODU1OEwxMy4xMDM4IDguMzY0IDE1LjExOTIgNy4yYS4wNzU3LjA3NTcgMCAwIDEgLjA3MSAwbDQuODMwMyAyLjc5MTNhNC40OTQ0IDQuNDk0NCAwIDAgMS0uNjc2NSA4LjEwNDJ2LTUuNjc3MmEuNzkuNzkgMCAwIDAtLjQwNy0uNjY3em0yLjAxMDctMy4wMjMxbC0uMTQyLS4wODUyLTQuNzczNS0yLjc4MThhLjc3NTkuNzc1OSAwIDAgMC0uNzg1NCAwTDkuNDA5IDkuMjI5N1Y2Ljg5NzRhLjA2NjIuMDY2MiAwIDAgMSAuMDI4NC0uMDYxNWw0LjgzMDMtMi43ODY2YTQuNDk5MiA0LjQ5OTIgMCAwIDEgNi42ODAyIDQuNjZ6TTguMzA2NSAxMi44NjNsLTIuMDItMS4xNjM4YS4wODA0LjA4MDQgMCAwIDEtLjAzOC0uMDU2N1Y2LjA3NDJhNC40OTkyIDQuNDk5MiAwIDAgMSA3LjM3NTctMy40NTM3bC0uMTQyLjA4MDVMOC43MDQgNS40NTlhLjc5NDguNzk0OCAwIDAgMC0uMzkyNy42ODEzem0xLjA5NzYtMi4zNjU0bDIuNjAyLTEuNDk5OCAyLjYwNjkgMS40OTk4djIuOTk5NGwtMi41OTc0IDEuNDk5Ny0yLjYwNjctMS40OTk3WiIvPjwvc3ZnPg%3D%3D" alt="Custom LLM">
  <img src="https://img.shields.io/badge/Linux-supported-FCC624?logo=linux&logoColor=black" alt="Linux">
</p>

<p align="center">
  <img src="docs/ARCHITECTURE.png" alt="Verilog Builder architecture block diagram" width="90%">
</p>

# Verilog Builder

Verilog Builder is a local FPGA workflow that lets an AI assistant create
projects, build designs module-by-module, stream synthesis progress, inspect
timing, pause safely for RTL changes, and generate simulation waveforms — all
by prompting, with no manual GUI steps.

## Editions

The same orchestration logic is packaged for three frontends:

- **[`vivado/claude-code/`](vivado/claude-code/README.md)** — the Claude Code plugin
  (and standalone MCP server) that started this project. Exposes the workflow
  as slash commands, and works from Claude Desktop too.
- **[`vivado/codex/`](vivado/codex/README.md)** — the Codex port, with its own
  MCP server, Tcl assets, and skills.
- **[`vivado/hermes/`](vivado/hermes/README.md)** and
  **[`vivado/openclaw/`](vivado/openclaw/README.md)** — Hermes Agent and OpenClaw
  ports (MCP server + skills).
- **[`vebu/`](vebu/README.md)** — a VS Code extension that talks to the same
  `mcp_server` orchestrator, for driving builds without leaving the editor.
- **Icarus Verilog edition** — the same workflow on a fully open-source
  toolchain, packaged for both frontends:
  [`icarus/claude-code/`](icarus/claude-code/README.md) and
  [`icarus/codex/`](icarus/codex/README.md), plus Hermes and OpenClaw ports in
  [`icarus/hermes/`](icarus/hermes/README.md) and
  [`icarus/openclaw/`](icarus/openclaw/README.md).

## What it does

- Creates a Vivado project from new or existing Verilog/SystemVerilog sources.
- Synthesizes modules one at a time, showing live module status and Vivado log output.
- Pauses on a synthesis error, presents the failing file and error, and resumes after a confirmed fix.
- Pauses at a safe module boundary when you want to change RTL during a running build.
- Reports WNS, TNS, WHS, and THS after a completed build.
- Runs behavioral simulation and opens the generated waveform in Vivado.

## Requirements

- Xilinx Vivado installed locally and available as `vivado` on your `PATH`, or
  configured through the `VIVADO_BIN` environment variable.
- Python 3 with the `mcp` package available to the selected MCP-server interpreter.

## Claude Code edition

Installed from [`vivado/claude-code/`](vivado/claude-code/), it exposes the workflow as
slash commands:

```text
/verilog-new
/verilog-build
/verilog-status
/verilog-timing
/verilog-fix
/verilog-modify
/generate_waveform
```

Its backend lives in [`vivado/claude-code/mcp_server/`](vivado/claude-code/mcp_server/)
and [`vivado/claude-code/tcl/`](vivado/claude-code/tcl/).

## Codex edition

The Codex plugin lives in [`vivado/codex/`](vivado/codex/). Its main components:

- [`vivado/codex/.vivado/codex/plugin.json`](vivado/codex/.vivado/codex/plugin.json) — plugin metadata.
- [`vivado/codex/.mcp.json`](vivado/codex/.mcp.json) — local MCP server configuration.
- [`vivado/codex/skills/`](vivado/codex/skills/) — seven assistant workflows:
  `verilog-new`, `verilog-build`, `verilog-status`, `verilog-timing`,
  `verilog-fix`, `verilog-modify`, and `generate-waveform`.
- [`vivado/codex/mcp_server/`](vivado/codex/mcp_server/) and
  [`vivado/codex/tcl/`](vivado/codex/tcl/) — the Vivado backend.

For an end-to-end example, see the [Codex walkthrough](vivado/codex/WALKTHROUGH.md).

## Icarus Verilog edition

A vendor-free port of the same product, for people without a Vivado licence. It
keeps the prompt-driven workflow — describe a module, get RTL on disk, build
module-by-module, pause-to-fix on errors — and swaps the toolchain:

| Job | Vivado edition | Icarus edition |
|---|---|---|
| Compile / elaborate | `vivado` synth | `iverilog` |
| Simulate | Vivado simulator | `vvp` |
| Schematic view | Open Elaborated Design | `yosys` + `netlistsvg` |
| Waveform view | Vivado waveform window | `.vcd` + `.gtkw` + GTKWave |
| Timing (WNS/TNS) | yes | no — nothing places or routes |

Requirements: `sudo apt install iverilog gtkwave yosys graphviz` plus
`sudo npm install -g netlistsvg`. No vendor tooling and no licence.

Both ports expose the same seven workflows — `iverilog-new`, `iverilog-build`,
`iverilog-status`, `iverilog-fix`, `iverilog-modify`, `iverilog-waveform`, and
`iverilog-schematic` — as slash commands in
[`icarus/claude-code/commands/`](icarus/claude-code/commands/) and as skills
in [`icarus/codex/skills/`](icarus/codex/skills/), backed by an
`iverilog-builder` MCP server in each port's `mcp_server/`.

Documentation:

- [Beginner tutorial](docs/icarus/beginner-tutorial.md) — install the toolchain
  and go from a prompt to a waveform and a schematic in one sitting.
- [Pipeline and flow diagrams](docs/icarus/pipeline.md) — what runs when, the
  build state machine, and the files a project accumulates.
- Port READMEs: [Claude Code](icarus/claude-code/README.md) ·
  [Codex](icarus/codex/README.md).

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
