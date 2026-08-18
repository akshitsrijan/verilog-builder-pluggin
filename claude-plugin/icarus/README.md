# Verilog Builder — Icarus edition (Claude Code plugin)

`verilog-builder-icarus` is the open-source counterpart to the Vivado edition of
Verilog Builder. Same idea — describe hardware in English, get RTL on disk, built
and simulated with pause-to-fix on errors — but with no vendor toolchain anywhere
in the loop:

| Job | Vivado edition | Icarus edition |
|---|---|---|
| Compile / elaborate | `vivado` synth | `iverilog` |
| Simulate | Vivado simulator | `vvp` |
| Schematic view | Open Elaborated Design | `yosys` + `netlistsvg` |
| Waveform view | Vivado waveform window | `.vcd` + `.gtkw` + GTKWave |
| Timing (WNS/TNS) | yes | **no** — there is no place-and-route step |

## Requirements

```bash
sudo apt install iverilog gtkwave yosys graphviz
sudo npm install -g netlistsvg      # optional but strongly recommended
```

- `iverilog` and `vvp` are required.
- `yosys` is required for schematics; `netlistsvg` draws the good ones and
  `graphviz` (`dot`) is the automatic fallback.
- `gtkwave` is required only to *view* waveforms — the `.vcd` is produced either way.
- Python 3.10+ with the `mcp` package. A ready venv lives at
  `mcp_server/venv/`; otherwise `pip install -r mcp_server/requirements.txt`.

Every binary is resolved through `project.tool_path()`, which honours the
environment variables `IVERILOG_BIN`, `VVP_BIN`, `YOSYS_BIN`, `GTKWAVE_BIN`,
`DOT_BIN` and `NETLISTSVG_BIN` before falling back to `/usr/bin`, `/usr/local/bin`
and then `PATH`. Set them in `.mcp.json` to retarget the toolchain.

## Install

From Claude Code:

```text
/plugin marketplace add <repo>/claude-plugin/icarus
/plugin install verilog-builder-icarus
```

The plugin ships its own MCP server (`.mcp.json` → `mcp_server/server.py`,
registered as **`iverilog-builder`**), so no extra MCP wiring is needed.

## Slash commands

| Command | What it does |
|---|---|
| `/iverilog-new [name and/or what to build]` | Create a project from a description — writes the RTL for you, or adopts existing `.v`/`.sv` files. |
| `/iverilog-build [project]` | Lint each module, compile the design, run testbenches; live progress, pause-to-fix on error. |
| `/iverilog-status [project]` | Report the current build state without starting or resuming anything. |
| `/iverilog-fix [project] [instructions]` | Explain a blocked build's error, apply a confirmed fix, resume. |
| `/iverilog-modify [project] [what to change]` | Pause a running build at a safe boundary, change RTL by prompt, resume. |
| `/iverilog-waveform [project] [module]` | Simulate a module and open GTKWave — the testbench is generated if there isn't one. |
| `/iverilog-schematic [project] [module]` | Draw the RTL (or gate-level) schematic with yosys. |

Commands are a convenience; plain English ("build my counter and show me the
waveform") reaches the same tools.

## MCP tool reference

Server name: `iverilog-builder`. Every tool returns a dict with `ok: bool`, plus
`error: str` when `ok` is false.

### Project and sources — `server.py`

| Tool | Arguments |
|---|---|
| `list_projects` | `search_root="~"` |
| `create_project` | `project_name`, `project_dir=""`, `source_files=[]`, `top=""`, `std="2012"` |
| `write_module` | `project_path`, `filename`, `content`, `is_testbench` |
| `add_sources` | `project_path`, `files: list[str]` |
| `lint_design` | `project_path`, `file_path=""` |
| `compile_design` | `project_path`, `top=""` |
| `run_simulation` | `project_path`, `testbench=""`, `run_seconds=60` |

`write_module` takes a **file name** (`counter.v`); a bare name lands in
`<project>/sources/`. Testbenches are auto-detected by name and by the presence
of `$dumpfile`/`$finish`, so `is_testbench` is usually unnecessary.

### Build control

| Tool | Arguments |
|---|---|
| `start_build` | `project_path`, `gui=False` |
| `get_build_status` | `project_path`, `wait_seconds=3` |
| `get_module_log` | `project_path`, `module`, `tail_lines=100` |
| `get_blocking_issue` | `project_path` |
| `apply_fix` | `project_path`, `file_path`, `new_content`, `note=""` |
| `resume_build` | `project_path`, `retry_module=True` |
| `pause_build` | `project_path` |
| `cancel_build` | `project_path` |

### Waveforms — `gtkwave_runner.py`

| Tool | Arguments |
|---|---|
| `generate_waveform` | `project_path`, `module=""`, `testbench=""`, `open_viewer=True`, `run_seconds=60`, `cycles=20` |
| `ensure_testbench` | `project_path`, `module=""`, `cycles=20`, `force=False` |
| `list_vcd_signals` | `vcd_path` |
| `open_waveform` | `vcd_path`, `gtkw_path=""` |

`generate_waveform` is the one-call path: testbench (written if missing) →
`iverilog` → `vvp` → `<build>/<module>.vcd` → a `<build>/<module>.gtkw` save file
with the interesting signals already picked and buses flagged as hex → GTKWave.
Set `open_viewer=False` on a headless machine; the VCD, the `.gtkw` and the
`signals` listing all still come back.

### Schematics — `yosys_runner.py`

| Tool | Arguments |
|---|---|
| `generate_schematic` | `project_path`, `top=""`, `level="rtl"`, `fmt="svg"` |
| `get_netlist_stats` | `project_path`, `top=""`, `level="rtl"` |
| `list_design_modules` | `project_path` |
| `open_schematic` | `schematic_path` |

- `level="rtl"` keeps adders, muxes and registers as recognisable blocks — this
  is the view you normally want, and the analogue of Vivado's elaborated design.
- `level="gate"` runs `synth -top <top> -flatten`. The `-flatten` matters: without
  it, a hierarchical design renders as a single opaque box instead of gates.
- `fmt` is `svg` (default, via netlistsvg), `png`, or `dot`. Output lands in
  `<build_dir>/schematic/<top>_<level>.svg`, alongside the yosys JSON netlist and
  the `schematic.ys` script that produced it.
- The result path comes back under the key `schematic`, with `renderer` naming
  whichever of netlistsvg/graphviz drew it.

## What a project looks like on disk

```text
counter_demo/
  .ivproj.json               manifest: name, top, sources, testbenches, std, toolchain
  sources/
    counter.v                design RTL
    tb_counter.v             testbench (generated ones land here too)
  build/
    counter.vvp              compiled design
    tb_counter.vvp           compiled testbench
    counter.vcd              simulation dump
    counter.gtkw             GTKWave save file
    .build_state.json        build state machine, rewritten atomically
    logs/{<module>.log, compile.log, simulate.log}
    schematic/{counter_rtl.svg, counter_rtl.json, schematic.ys}
```

Build phases are `modules` → `compile` → `simulate` → `done`, and build status is
one of `running`, `blocked`, `paused`, `completed`, `failed`, `cancelled` (plus
`not_started`). See [`docs/icarus/pipeline.md`](../../docs/icarus/pipeline.md).

## Extending it

`mcp_server/CONTRACT.md` is the internal API — the `Project` model, the shared
`tool_path()`/`run_cmd()` helpers, the build-state schema and the `register(mcp)`
convention that `yosys_runner.py` and `gtkwave_runner.py` use to attach their
tools without touching `server.py`.

## More

- [Beginner tutorial](../../docs/icarus/beginner-tutorial.md) — zero to waveform.
- [Pipeline and flow diagrams](../../docs/icarus/pipeline.md).
