# Integration contract — `verilog-builder-icarus`

This is the API the Icarus plugin's core exposes to the optional tool modules
(`yosys_runner.py`, `gtkwave_runner.py`, …). Code against this document; you
should not need to read `project.py` or `iverilog_runner.py` to build on them.

Everything here is stdlib-only except `server.py` itself, which needs `mcp`
from `mcp_server/venv/`.

---

## 1. `project.py` — the project model

A **project** is a directory containing a `.ivproj.json` manifest:

```json
{
  "name": "counter_demo",
  "top": "counter",
  "sources": ["sources/counter.v"],
  "testbenches": ["sources/tb_counter.v"],
  "build_dir": "build",
  "std": "2012",
  "include_dirs": [],
  "created": "2026-08-18T10:00:00+00:00",
  "toolchain": {"iverilog": "/usr/bin/iverilog", "vvp": "/usr/bin/vvp"}
}
```

Paths in the manifest are **relative to the project root** where possible and
absolute otherwise. On a loaded `Project` they are always **resolved absolute
`pathlib.Path` objects**.

### The `Project` dataclass

| Field | Type | Meaning |
|---|---|---|
| `name` | `str` | Project name |
| `root` | `Path` | Project directory (absolute) — the manifest's parent |
| `top` | `str` | Top module name; may be `""` |
| `sources` | `list[Path]` | Design sources (no testbenches) |
| `testbenches` | `list[Path]` | Testbench sources |
| `build_dir` | `str` | Build dir name relative to `root`, default `"build"` |
| `std` | `str` | Verilog standard, passed as `-g<std>`, default `"2012"` |
| `include_dirs` | `list[Path]` | Extra `-I` directories |
| `created` | `str` | ISO-8601 UTC creation timestamp |
| `toolchain` | `dict` | Resolved tool paths recorded at creation |

Methods:

- `project.manifest_path -> Path` — the `.ivproj.json` (property).
- `project.build_path() -> Path` — absolute build dir, **created on demand**.
  Put your artifacts here (e.g. `project.build_path() / "schematic.svg"`).
- `project.rel(path) -> str` — path relative to root when possible.
- `project.all_files() -> list[Path]` — sources then testbenches.
- `project.modules() -> list[dict]` — `[{"name", "file"}]` per design source
  (testbenches excluded); `name` is the first `module <name>` in the file.
- `project.to_dict() -> dict` — the manifest form.
- `project.summary() -> dict` — `to_dict()` plus `path`, `manifest`,
  `build_path`. **Return this from tools that report project state.**

### Module-level functions

```python
load_project(path) -> Project
```
Accepts a project directory, a `.ivproj.json` path, or a source file sitting
next to one. Raises `ProjectError` if no manifest is found.

```python
save_project(project) -> Path
```
Writes the manifest atomically. Returns its path. Call this after mutating a
`Project`; nothing auto-saves.

```python
create_project(name, dir="", sources=None, top="", std="2012") -> Project
```
`dir` defaults to `~/<name>/`. Creates `<root>/sources/`. Files that look like
testbenches are sorted into `testbenches` automatically. Raises `ProjectError`
if a project already exists there or a listed source is missing.

```python
add_sources(project, files) -> Project
```
Registers more files, skipping duplicates, saving the manifest. Mutates and
returns the same instance.

```python
write_module(project, filename, content, is_testbench=None) -> Path
```
Writes Verilog into the project and registers it. A bare `filename` lands in
`<root>/sources/`; a relative path resolves against `root`. An unrecognised
suffix becomes `.v`. `is_testbench=None` uses the heuristic. Returns the
written path.

```python
list_projects(search_root="~") -> list[dict]
```
Walks up to two levels below `search_root`. Returns
`[{"name", "path", "manifest", "top", "source_count"}]`, skipping unparseable
manifests.

### Shared helpers — use these rather than rolling your own

```python
tool_path(name) -> str
```
Resolves a toolchain binary. Known names: `iverilog`, `vvp`, `yosys`,
`gtkwave`, `dot`, `netlistsvg`. Honours `IVERILOG_BIN`, `VVP_BIN`,
`YOSYS_BIN`, `GTKWAVE_BIN`, `DOT_BIN`, `NETLISTSVG_BIN`, then the known
`/usr/bin` (or `/usr/local/bin`) location, then the bare name via `PATH`.
**Always call this instead of hardcoding a path** — it is how the user
retargets the toolchain from `.mcp.json`.

```python
run_cmd(argv, cwd=None, timeout=120) -> {"rc": int, "stdout": str, "stderr": str}
```
Never raises. A timeout gives `rc=124`, a missing binary `rc=127`, with the
reason in `stderr`.

```python
module_name_for_file(path) -> str      # first `module <name>`, else file stem
looks_like_testbench(path) -> bool     # name heuristic + $dumpfile/$finish
```

`ProjectError` — raised for a missing/bad project. Catch it and turn it into
`{"ok": False, "error": str(exc)}`.

---

## 2. `iverilog_runner.py` — what you can reuse

- `compile_design(project, top="") -> dict` — `{"ok", "top", "output",
  "command", "errors", "warnings", "stderr"}`. `output` is the `.vvp` path.
- `lint_file(path, std="2012", include_dirs=None) -> dict`
- `lint_design(project) -> dict`
- `run_simulation(project, testbench="", run_seconds=60) -> dict` — returns
  `{"ok", "top", "testbench", "vvp_binary", "command", "stdout", "stderr",
  "vcd"}`. **`vcd` is the VCD path or `None`** — this is the handoff point for
  a waveform viewer. It is read from the testbench's `$dumpfile(...)`, falling
  back to `<build>/dump.vcd`; `vvp` runs with cwd set to the build dir so
  relative dump paths land there.
- `parse_diagnostics(text) -> list` — parses iverilog stderr into
  `[{"file", "line", "severity", "message"}]`, `severity` one of `error`,
  `warning`, `sorry`, `info`. Reuse this for yosys output only if the format
  matches; it is tuned for `file:line: severity: message`.

Build control (all take a project path string, all return dicts with `"ok"`):
`start_build`, `get_status`, `get_module_log`, `get_blocking_issue`,
`apply_fix`, `resume_build`, `request_pause`, `cancel_build`.

---

## 3. Build-state JSON schema

Persisted at `<project>/<build_dir>/.build_state.json`, rewritten atomically
after every transition so it can be read from any process. Per-module logs are
`<build_dir>/logs/<module>.log`, plus `compile.log` and `simulate.log`.

```json
{
  "build_id": "counter_demo-1750000000",
  "project_path": "/home/user/counter_demo",
  "project_name": "counter_demo",
  "status": "running",
  "phase": "modules",
  "modules": [
    {"name": "counter", "file": "/abs/sources/counter.v",
     "status": "done", "error": null}
  ],
  "testbenches": ["/abs/sources/tb_counter.v"],
  "current_module": "counter",
  "current_log": "/abs/build/logs/counter.log",
  "blocking_issue": null,
  "compile": {"ok": true, "top": "counter", "output": "...vvp",
              "command": "...", "errors": []},
  "simulation": { "…run_simulation() result…" },
  "vvp_binary": "/abs/build/counter.vvp",
  "fix_log": [{"at": "…", "file": "…", "note": "…", "backup": "…"}],
  "gui_enabled": false,
  "pause_requested": false,
  "started_at": "…",
  "finished_at": "…",
  "updated_at": "…"
}
```

- **`status`**: `running` | `blocked` | `paused` | `completed` | `failed` |
  `cancelled`. Also `not_started` from `get_status` when no build has run.
- **`phase`**: `modules` → `compile` → `simulate` → `done`.
- **`modules[].status`**: `pending` | `running` | `done` | `error`.
- **`blocking_issue`** (set only when `status == "blocked"`):
  `{"module", "file", "error", "errors": [diagnostic…], "log_file"}`.

`get_status()` additionally returns `log_tail` — the last 20 lines of
`current_log` — and `ok: true`. It does **not** persist those.

State machine: an error during phase 1 or 2 sets `blocked`; `resume_build`
resets the failing module to `pending` (or leaves it failed with
`retry_module=False`) and restarts the orchestrator thread.
`request_pause` sets `pause_requested`, which the orchestrator honours between
modules — it never kills an in-flight process.

---

## 4. The `register(mcp)` convention

`server.py` ends with:

```python
for _mod in ("yosys_runner", "gtkwave_runner"):
    try:
        __import__(_mod).register(mcp)
    except Exception as _e:
        print(f"[iverilog-builder] optional module {_mod} unavailable: {_e}", file=sys.stderr)
```

So your module must:

1. Live at `mcp_server/<name>.py` (the directory is already on `sys.path`).
2. Expose exactly `def register(mcp) -> None`.
3. Declare its tools **inside** `register`, using `@mcp.tool()` with a typed
   signature and a docstring — the docstring is the tool description Claude
   reads, so write it for Claude, not for a maintainer.
4. Not fail at import time if its binary is missing. Check with `tool_path()`
   at **call** time and return `{"ok": False, "error": ...}`; a raise inside
   `register` silently drops all of your tools.

```python
import project as pj

def register(mcp):
    @mcp.tool()
    def show_schematic(project_path: str, module: str = "") -> dict:
        """One-line summary, then the details Claude needs."""
        try:
            project = pj.load_project(project_path)
        except pj.ProjectError as exc:
            return {"ok": False, "error": str(exc)}
        out = project.build_path() / f"{module or project.top}.svg"
        ...
        return {"ok": True, "svg": str(out)}
```

Do not edit `server.py`, `project.py`, or `iverilog_runner.py` to wire
yourself in — the loop above is the whole integration surface.

---

## 5. Return-shape conventions

Every MCP tool returns a **dict** (never a bare list or string) containing:

- `"ok": bool` — always present.
- `"error": str` — present **iff** `ok` is false; a plain sentence the user
  can read, not a traceback.

Beyond that:

- Return **absolute paths as strings**, under keys named for what they are
  (`vcd`, `svg`, `output`, `log_file`).
- Report compiler/tool diagnostics as a list under `"errors"` in the
  `{"file", "line", "severity", "message"}` shape, and keep the raw text under
  `"stderr"` — Claude quotes the structured form and falls back to the raw.
- Include the command you ran under `"command"` so failures are debuggable.
- Never raise out of a tool. A traceback reaching the MCP layer becomes an
  opaque protocol error; a returned `{"ok": False, "error": …}` is something
  Claude can act on.
- Long-running work follows the build pattern: return immediately with an id
  and let the caller poll, rather than blocking the MCP call.
