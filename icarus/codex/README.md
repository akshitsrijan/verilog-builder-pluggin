# Verilog Builder — Icarus edition (Codex plugin)

The Codex port of `verilog-builder-icarus`: describe hardware in English, get RTL
on disk, built and simulated with pause-to-fix on errors — entirely on
open-source tooling. It is the same product as the Vivado Codex plugin one level
up, with the vendor stack swapped out:

| Job | Vivado edition | Icarus edition |
|---|---|---|
| Compile / elaborate | `vivado` synth | `iverilog` |
| Simulate | Vivado simulator | `vvp` |
| Schematic view | Open Elaborated Design | `yosys` + `netlistsvg` |
| Waveform view | Vivado waveform window | `.vcd` + `.gtkw` + GTKWave |
| Timing (WNS/TNS) | yes | **no** — nothing here places or routes |

## Requirements

```bash
sudo apt install iverilog gtkwave yosys graphviz
sudo npm install -g netlistsvg      # optional but strongly recommended
```

- `iverilog` and `vvp` are required.
- `yosys` is required for schematics; `netlistsvg` renders the readable ones and
  `graphviz` (`dot`) is the automatic fallback.
- `gtkwave` is needed only to *view* waveforms — the `.vcd` is written regardless.
- Python 3.10+ with `mcp` installed (`pip install -r mcp_server/requirements.txt`).
  `.mcp.json` invokes plain `python`, so make sure the interpreter on `PATH` has
  `mcp` available, or point the command at a venv interpreter.

Binaries resolve through `project.tool_path()`, which checks `IVERILOG_BIN`,
`VVP_BIN`, `YOSYS_BIN`, `GTKWAVE_BIN`, `DOT_BIN` and `NETLISTSVG_BIN` first, then
`/usr/bin` / `/usr/local/bin`, then `PATH`. Add an `env` block to `.mcp.json` to
retarget the toolchain.

## Install

Install this directory as a Codex plugin. `.codex-plugin/plugin.json` points at
`./skills` and `./.mcp.json`, which registers the MCP server **`iverilog-builder`**
(`${CODEX_PLUGIN_ROOT}/mcp_server/server.py`).

## Skills

| Skill | What it does |
|---|---|
| `iverilog-new` | Create a project from a description — writes the RTL, or adopts existing `.v`/`.sv` files. |
| `iverilog-build` | Lint each module, elaborate the design, run testbenches; live progress and pause-to-fix. |
| `iverilog-status` | Report the current build state without starting or resuming anything. |
| `iverilog-fix` | Explain a blocked build's error, apply a confirmed fix, resume. |
| `iverilog-modify` | Pause a running build at a safe boundary, change RTL by prompt, resume. |
| `iverilog-waveform` | Simulate a module and open GTKWave — the testbench is generated if there isn't one. |
| `iverilog-schematic` | Draw the RTL (or gate-level) schematic with yosys. |

Skills are triggered by describing what you want; you rarely name them directly.

## MCP tool reference

Server name: `iverilog-builder`. Every tool returns a dict with `ok: bool`, plus
`error: str` when `ok` is false.

### Project and sources — `server.py`

| Tool | Arguments |
|---|---|
| `list_projects` | `search_root="~"` |
| `create_project` | `project_name`, `project_dir=""`, `source_files=None`, `top=""` |
| `write_module` | `project_path`, `module_name`, `verilog_code`, `is_testbench=False`, `subdir=""` |
| `add_sources` | `project_path`, `files: list[str]` |
| `lint_design` | `project_path`, `file_path=""` |
| `compile_design` | `project_path`, `top=""` |
| `run_simulation` | `project_path`, `testbench=""`, `timeout=120` |

`write_module` takes a **module name**, not a file name — `counter` is written as
`counter.v`. Design modules default to `<project>/sources/`, testbenches to
`<project>/tb/`; `subdir` overrides both. An existing file is backed up to
`<file>.bak` before being overwritten, so re-calling `write_module` is the normal
way to revise a module.

### Build control

| Tool | Arguments |
|---|---|
| `start_build` | `project_path`, `top=""` |
| `get_build_status` | `project_path`, `wait_seconds=2` |
| `get_module_log` | `project_path`, `module`, `tail_lines=100` |
| `get_blocking_issue` | `project_path` |
| `apply_fix` | `project_path`, `file_path`, `new_content`, `note=""` |
| `resume_build` | `project_path`, `retry_module=True` |
| `pause_build` | `project_path` |
| `cancel_build` | `project_path` |

### Waveforms — `gtkwave_runner.py`

| Tool | Arguments |
|---|---|
| `generate_waveform_for_module` | `project_path`, `module=""`, `testbench=""`, `open_viewer=True`, `cycles=32` |
| `ensure_waveform_testbench` | `project_path`, `module=""`, `force=False`, `cycles=32` |
| `list_waveform_signals` | `vcd_path` |
| `open_waveform_viewer` | `vcd_path`, `gtkw_path=""` |

`generate_waveform_for_module` is the one-call path: testbench (written into
`<project>/tb/` if missing) → `iverilog` → `vvp` → `<build>/<module>.vcd` → a
`<build>/<module>.gtkw` save file with the interesting signals already selected →
GTKWave. Pass `open_viewer=False` on a headless machine; the VCD, the `.gtkw` and
the signal listing still come back.

### Schematics — `yosys_runner.py`

| Tool | Arguments |
|---|---|
| `generate_schematic` | `project_path`, `top=""`, `level="rtl"`, `fmt="svg"` |
| `get_netlist_stats` | `project_path`, `top=""` |
| `list_design_modules` | `project_path` |
| `open_schematic` | `path=""`, `project_path=""` |

- `level="rtl"` (default) keeps adders, muxes and registers as recognisable
  blocks — the analogue of Vivado's elaborated-design view.
- `level="gate"` runs `synth -top <top> -flatten`. The `-flatten` is what makes
  the gate view useful: without it a hierarchical design renders as one opaque
  box rather than gates.
- `fmt` is `svg` (default, via netlistsvg), `png`, `dot` or `json`. Output lands
  in `<build_dir>/schematic/<top>_<level>.svg`, next to the yosys JSON netlist,
  the run log, and the `schematic.ys` script that produced it.
- The rendered path comes back under `svg` (or the matching format key), with
  `renderer` naming whichever of netlistsvg/graphviz drew it.
- `open_schematic` accepts either an explicit `path` or just `project_path`, in
  which case it opens the most recently rendered schematic.

## What a project looks like on disk

```text
counter_demo/
  .ivproj.json               manifest: name, top, sources, testbenches, std, toolchain
  sources/counter.v          design RTL
  tb/tb_counter.v            testbenches, including generated ones
  build/
    counter.vvp              elaborated design
    tb_counter.vvp           compiled testbench
    counter.vcd              simulation dump
    counter.gtkw             GTKWave save file
    .build_state.json        build state machine, rewritten atomically
    logs/{<module>.log, elaborate.log, <tb>_sim.log}
    schematic/{counter_rtl.svg, counter_rtl.json, counter_rtl.dot, schematic.ys}
```

Build phases are `modules` → `elaborate` → `done`, and build status is one of
`running`, `blocked`, `paused`, `completed`, `failed`, `cancelled` (plus
`not_started` before the first build). See
[`docs/icarus/pipeline.md`](../../docs/icarus/pipeline.md).

## Extending it

`mcp_server/CONTRACT.md` documents the internal API: the `Project` model, the
shared `tool_path()`/`run_cmd()` helpers, the build-state schema, and the
`register(mcp)` convention `yosys_runner.py` and `gtkwave_runner.py` use to
attach tools without `server.py` knowing about them.

## More

- [Beginner tutorial](../../docs/icarus/beginner-tutorial.md) — zero to waveform.
- [Pipeline and flow diagrams](../../docs/icarus/pipeline.md).
