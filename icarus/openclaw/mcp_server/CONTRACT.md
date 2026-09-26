# iverilog-builder MCP server — internal contract

Everything in `mcp_server/` codes against this document. Companion modules
(`yosys_runner.py`, `gtkwave_runner.py`) should not need to read
`project.py` or `iverilog_runner.py` source.

## 1. Return-shape convention

**Every MCP tool returns a JSON object with an `"ok"` boolean.**

- Success: `{"ok": true, ...payload}`
- Failure: `{"ok": false, "error": "<human-readable reason>", ...}`

A tool must never raise out to the MCP layer. Wrap the body and return
`{"ok": False, "error": str(exc)}` instead. Add `"diagnostics"` (see §4)
whenever the failure came from a toolchain invocation.

## 2. The project manifest

A project is a **directory** containing `.ivproj.json`. Every tool's
`project_path` argument accepts either the directory or the manifest file.

```json
{
  "name": "counter_demo",
  "top": "counter",
  "sources": ["sources/counter.v"],
  "testbenches": ["tb/tb_counter.v"],
  "build_dir": "build",
  "std": "2012",
  "include_dirs": [],
  "created": "2026-08-18T06:31:34.034135+00:00",
  "toolchain": {"iverilog": "/usr/bin/iverilog", "vvp": "/usr/bin/vvp"}
}
```

Paths in the manifest are **relative to the project root**; the `Project`
object exposes them as **absolute resolved `pathlib.Path`s**. `std` maps to
iverilog's `-g` flag (default `2012` → `-g2012`).

## 3. `project.py` public API

```python
@dataclass
class Project:
    root: pathlib.Path          # project directory, absolute
    name: str
    top: str                    # top module name ("" if unset)
    sources: list[pathlib.Path]      # absolute
    testbenches: list[pathlib.Path]  # absolute
    build_dir: str = "build"    # relative name
    std: str = "2012"
    include_dirs: list[pathlib.Path]
    created: str                # ISO-8601 UTC
    toolchain: dict

    build_path() -> pathlib.Path   # absolute build dir, mkdir'd on demand
    manifest_path() -> pathlib.Path
    rel(p) -> str                  # path relative to root when possible
    to_dict() -> dict              # manifest form
    summary() -> dict              # to_dict() + "path" and "manifest"
```

Module-level functions:

| Function | Behaviour |
| --- | --- |
| `load_project(path) -> Project` | `path` may be the project dir, the `.ivproj.json`, or a file inside the project dir. Raises `FileNotFoundError` if no manifest. |
| `save_project(p) -> pathlib.Path` | Atomic write of the manifest. Returns its path. |
| `create_project(name, dir, sources=None, top="") -> Project` | Makes the dir, classifies `sources` into sources/testbenches, saves, creates the build dir. Raises `FileExistsError` if a manifest is already there, `FileNotFoundError` for a missing source. |
| `list_projects(search_root="~") -> list[dict]` | Walks `search_root` and up to two levels below. Returns `{"name","path","top","sources","manifest","created"}`, newest first. |
| `add_sources(p, files) -> Project` | Registers files in place and saves. Testbench-named files go to `testbenches`. Ignores duplicates. |
| `run_cmd(argv, cwd=None, timeout=120) -> dict` | `{"rc", "stdout", "stderr"}`. Never raises: `rc=-1` on timeout, `rc=-2` if the binary could not be launched. |
| `tool_path(name) -> str` | Absolute path for `iverilog`/`vvp`/`yosys`/`gtkwave`. Honours `IVERILOG_BIN` / `VVP_BIN` / `YOSYS_BIN` / `GTKWAVE_BIN`, then `PATH`, then `/usr/bin/<name>`. |
| `looks_like_testbench(path) -> bool` | Name heuristic: `tb_*`, `*_tb.*`, `*testbench*`. |
| `module_name_for_file(path) -> str` | First `module <name>` in the file (comments stripped), else the file stem. |
| `manifest_for(path) -> pathlib.Path` | Normalises any of the accepted path forms to the manifest path. |

Constants: `MANIFEST_NAME = ".ivproj.json"`, `SOURCE_SUFFIXES`.

`project.py` is **stdlib only** — keep it that way so any companion module
can import it without pulling in dependencies.

## 4. Diagnostics

`iverilog_runner.parse_diagnostics(text) -> list[dict]` turns raw
iverilog/vvp stderr into:

```json
{"file": "/abs/path/counter.v", "line": 9, "severity": "error", "message": "syntax error"}
```

`severity` is one of `error`, `warning`, `sorry`, `note`. Lines without a
`file:line:` prefix are preserved with `file`/`line` set to `null` so no
part of a toolchain message is dropped.

## 5. Build state

Persisted at `<build_dir>/.build_state.json`, written atomically, readable
from any process:

```json
{
  "build_id": "counter_demo-1787034694",
  "project_path": "/abs/project/dir",
  "top": "counter",
  "status": "running",
  "phase": "modules",
  "modules": [
    {"name": "counter", "file": "/abs/sources/counter.v",
     "status": "pending", "error": null, "warnings": []}
  ],
  "current_module": "counter",
  "current_log": "/abs/build/logs/counter.log",
  "blocking_issue": null,
  "output": null,
  "fix_log": [{"at": "...", "file": "...", "note": "..."}],
  "pause_requested": false,
  "started_at": "...",
  "updated_at": "..."
}
```

- `status` ∈ `running` | `blocked` | `paused` | `completed` | `failed` | `cancelled`
  (plus `not_started` synthesised by `get_status` when no state file exists).
- `phase` ∈ `modules` | `elaborate` | `done`.
- per-module `status` ∈ `pending` | `running` | `done` | `error`.
- `blocking_issue`, when set: `{"module", "file", "error", "log_file", "diagnostics"}`.
- `output` is the elaborated `.vvp` path once `status == "completed"`.
- Per-module logs live at `<build_dir>/logs/<module>.log`; the whole-design
  elaboration log at `<build_dir>/logs/elaborate.log`; simulation logs at
  `<build_dir>/logs/<tb_top>_sim.log`.

The build runs on a daemon thread. `pause_requested` is honoured **between**
modules — a pause never kills an in-flight `iverilog` process.

## 6. `iverilog_runner.py` public API

```
compile_design(project: Project, top=None) -> dict
lint_file(project, file_path, extra_files=None) -> dict
lint_design(project) -> dict
start_build(project_path: str, top=None) -> dict
get_status(project_path) -> dict
get_module_log(project_path, module, tail_lines=100) -> dict
get_blocking_issue(project_path) -> dict
apply_fix(project_path, file_path, new_content, note="") -> dict
resume_build(project_path, retry_module=True) -> dict
request_pause(project_path) -> dict
cancel_build(project_path) -> dict
run_simulation(project_path, testbench=None, timeout=120) -> dict
parse_diagnostics(text) -> list[dict]
```

Note the asymmetry: `compile_design` / `lint_*` take a **`Project` object**,
while the build/simulation entry points take a **path string** (they re-load
the manifest themselves so mid-build edits are picked up).

`run_simulation` compiles the testbench together with `sources`, runs `vvp`
with `cwd = build_path()` so a relative `$dumpfile` lands in the build dir,
and returns `{"ok","testbench","top","vvp","stdout","stderr","vcd","log_file"}`.
`vcd` is resolved from the testbench's own `$dumpfile(...)` argument, falling
back to `<build_dir>/dump.vcd`, and is `null` if no VCD was written.

## 7. Adding tools from a companion module — `register(mcp)`

`server.py` ends with:

```python
for _mod in ("yosys_runner", "gtkwave_runner"):
    try:
        __import__(_mod).register(mcp)
    except Exception as _e:
        print(f"[iverilog-builder] optional module {_mod} unavailable: {_e}", file=sys.stderr)
```

So a companion module must:

1. Live at `mcp_server/<name>.py` (the server puts its own directory on
   `sys.path`, so plain `import project` works from it).
2. Expose **`register(mcp)`** taking the `FastMCP` instance and declaring its
   tools inside with `@mcp.tool()`.
3. Do nothing expensive or failure-prone at import time — probe for `yosys` /
   `gtkwave` inside the tool call and return `{"ok": False, "error": ...}`,
   not at import.
4. Follow §1's return shape.

An unavailable or broken companion module logs one line to stderr and the
server starts anyway with the core tools intact.

```python
# yosys_runner.py
import project as pj

def register(mcp):
    @mcp.tool()
    def show_schematic(project_path: str, module: str = "") -> dict:
        """..."""
        p = pj.load_project(project_path)
        ...
        return {"ok": True, "svg": str(svg_path)}
```
