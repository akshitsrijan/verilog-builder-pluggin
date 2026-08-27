"""Compile / simulate / build-state orchestration for the Icarus flow.

Mirrors the shape of the Vivado plugin's vivado_runner.py, but on top of the
open-source toolchain: `iverilog` compiles, `vvp` simulates. The build is
still driven module-by-module so progress is visible per file and so a single
bad module blocks with a precise, quotable error instead of a wall of output.

Build state is persisted to <build_dir>/.build_state.json so status can be
polled independently of which process is asking.
"""

import json
import pathlib
import re
import threading
import time
from datetime import datetime, timezone

import project as pj

STATE_NAME = ".build_state.json"

_active_builds = {}
_lock = threading.Lock()

# iverilog diagnostics look like:  path/to/file.v:12: syntax error
#                                  path/to/file.v:12: error: msg
#                                  path/to/file.v:12: warning: msg
_DIAG_RE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
    r"(?:(?P<severity>error|warning|sorry)\s*:\s*)?(?P<message>.*)$"
)

# Trailing summary chatter that restates diagnostics already reported above.
# Counting these as errors in their own right would hide the real one.
_NOISE_RE = re.compile(
    r"^(\d+\s+error\(s\)|\*\*\*|These modules were missing|"
    r"\S+\s+referenced\s+\d+\s+times)", re.I)


# --------------------------------------------------------------------------
# diagnostics
# --------------------------------------------------------------------------

def parse_diagnostics(text: str) -> list:
    """Parse iverilog stderr into [{file, line, severity, message}].

    Lines that don't match the compiler's diagnostic shape are kept as a
    severity="error" entry with file/line None only when they clearly signal
    a failure, so nothing meaningful is silently dropped.
    """
    out = []
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line.strip() or _NOISE_RE.match(line.strip()):
            continue
        m = _DIAG_RE.match(line)
        if m:
            sev = m.group("severity") or ("error" if "error" in line.lower() else "info")
            out.append({
                "file": m.group("file"),
                "line": int(m.group("line")),
                "severity": sev,
                "message": m.group("message").strip() or line.strip(),
            })
        elif re.search(r"\b(error|fatal|cannot|no such file)\b", line, re.I):
            out.append({"file": None, "line": None, "severity": "error",
                        "message": line.strip()})
    return out


def _errors_only(diags: list) -> list:
    return [d for d in diags if d["severity"] in ("error", "sorry")]


def _iverilog_argv(project: pj.Project, output=None, files=None, null_target=False) -> list:
    argv = [pj.tool_path("iverilog"), f"-g{project.std or '2012'}"]
    for inc in project.include_dirs:
        argv += ["-I", str(inc)]
    if null_target:
        argv += ["-t", "null"]
    if output is not None:
        argv += ["-o", str(output)]
    argv += [str(f) for f in (files if files is not None else project.all_files())]
    return argv


# --------------------------------------------------------------------------
# compile / lint
# --------------------------------------------------------------------------

def compile_design(project: pj.Project, top: str = "") -> dict:
    """Compile the whole design (sources + testbenches) into a vvp binary.

    Returns {"ok", "output", "command", "errors", "warnings", "stderr"}.
    """
    files = project.all_files()
    if not files:
        return {"ok": False, "error": "project has no sources to compile"}

    top_name = top or project.top or pj.module_name_for_file(files[-1])
    output = project.build_path() / f"{top_name}.vvp"

    argv = _iverilog_argv(project, output=output, files=files)
    if top:
        argv[1:1] = ["-s", top]
    res = pj.run_cmd(argv, cwd=project.root, timeout=180)
    diags = parse_diagnostics(res["stderr"])
    errors = _errors_only(diags)
    ok = res["rc"] == 0 and output.exists()

    return {
        "ok": ok,
        "top": top_name,
        "output": str(output) if ok else None,
        "command": " ".join(argv),
        "errors": errors,
        "warnings": [d for d in diags if d["severity"] == "warning"],
        "stderr": res["stderr"].strip(),
        **({} if ok else {"error": errors[0]["message"] if errors
                          else res["stderr"].strip() or "iverilog failed"}),
    }


# --------------------------------------------------------------------------
# an unresolved-instance error is not a real per-file lint failure
# --------------------------------------------------------------------------

_UNRESOLVED_RE = re.compile(
    r"(unknown module type|unable to (?:bind|elaborate)|has no definition|"
    r"unresolved|is not a module)", re.I)


def _only_unresolved(errors: list) -> bool:
    return bool(errors) and all(_UNRESOLVED_RE.search(e["message"]) for e in errors)


def lint_file(path, std: str = "2012", include_dirs=None) -> dict:
    """Syntax-check a single file with `iverilog -t null`.

    A file that instantiates modules defined elsewhere will report unresolved
    instances; those are reported as errors here but the module-by-module
    build treats them as expected and defers to the whole-design compile.
    """
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists():
        return {"ok": False, "error": f"file not found: {p}"}
    argv = [pj.tool_path("iverilog"), f"-g{std or '2012'}", "-t", "null"]
    for inc in include_dirs or []:
        argv += ["-I", str(inc)]
    argv.append(str(p))
    res = pj.run_cmd(argv, cwd=p.parent, timeout=60)
    diags = parse_diagnostics(res["stderr"])
    errors = _errors_only(diags)
    # A file that only fails because it instantiates modules defined in other
    # files is not a lint failure - the whole-design compile resolves those.
    deferred = _only_unresolved(errors)
    return {
        "ok": res["rc"] == 0 or deferred,
        "file": str(p),
        "command": " ".join(argv),
        "errors": [] if deferred else errors,
        "unresolved_instances": [e["message"] for e in errors] if deferred else [],
        "warnings": [d for d in diags if d["severity"] == "warning"],
        "stderr": res["stderr"].strip(),
    }


def lint_design(project: pj.Project) -> dict:
    """Syntax-check every file in the project individually."""
    results = [lint_file(f, project.std, project.include_dirs) for f in project.all_files()]
    return {
        "ok": all(r["ok"] for r in results),
        "files": results,
        "failed": [r["file"] for r in results if not r["ok"]],
    }



# --------------------------------------------------------------------------
# build state
# --------------------------------------------------------------------------

def _state_path(project: pj.Project) -> pathlib.Path:
    return project.build_path() / STATE_NAME


def _read_state(project: pj.Project):
    p = _state_path(project)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _write_state(project: pj.Project, state: dict):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    p = _state_path(project)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(p)


def _resolve(project_path) -> pj.Project:
    """Load a project, raising ProjectError for a bad path."""
    return pj.load_project(project_path)


def _append_log(project: pj.Project, name: str, lines):
    logdir = project.build_path() / "logs"
    logdir.mkdir(exist_ok=True)
    with open(logdir / f"{name}.log", "a") as f:
        for line in lines:
            f.write(line.rstrip("\n") + "\n")


# --------------------------------------------------------------------------
# the orchestrator
# --------------------------------------------------------------------------

def _orchestrate(project_root: str, stop_event: threading.Event, resume: bool = False):
    try:
        _orchestrate_inner(project_root, stop_event, resume)
    except Exception as exc:  # never leave state stuck at "running"
        try:
            project = _resolve(project_root)
            state = _read_state(project) or {}
            state["status"] = "failed"
            state["blocking_issue"] = {
                "module": state.get("current_module"), "file": None,
                "error": f"orchestrator crashed: {exc!r}", "errors": [],
            }
            _write_state(project, state)
        except pj.ProjectError:
            pass


def _orchestrate_inner(project_root: str, stop_event: threading.Event, resume: bool):
    project = _resolve(project_root)
    state = _read_state(project)
    if state is None:
        return

    # -- phase 1: lint each design module on its own ------------------------
    state["phase"] = "modules"
    _write_state(project, state)

    for mod in state["modules"]:
        if stop_event.is_set():
            state["status"] = "cancelled"
            state["current_module"] = None
            _write_state(project, state)
            return
        if state.get("pause_requested"):
            state["status"] = "paused"
            state["pause_requested"] = False
            state["current_module"] = None
            _write_state(project, state)
            return
        if mod["status"] == "done":
            continue

        mod["status"] = "running"
        mod["error"] = None
        state["current_module"] = mod["name"]
        state["current_log"] = str(project.build_path() / "logs" / f"{mod['name']}.log")
        _write_state(project, state)

        result = lint_file(mod["file"], project.std, project.include_dirs)
        _append_log(project, mod["name"],
                    [f"$ {result.get('command', '')}"] +
                    (result.get("stderr", "") or "").splitlines() +
                    [f"-> {'ok' if result['ok'] else 'FAILED'}"])

        errors = result.get("errors", [])
        # A module that only fails because its submodules live in other files
        # is fine at this stage - the whole-design compile resolves those.
        if not result["ok"] and not _only_unresolved(errors):
            mod["status"] = "error"
            mod["error"] = errors[0]["message"] if errors else result.get("stderr", "lint failed")
            state["status"] = "blocked"
            state["blocking_issue"] = {
                "module": mod["name"], "file": mod["file"],
                "error": result.get("stderr") or mod["error"],
                "errors": errors,
                "log_file": state["current_log"],
            }
            _write_state(project, state)
            return

        mod["status"] = "done"
        mod["error"] = None
        _write_state(project, state)

    if state.get("pause_requested"):
        state["status"] = "paused"
        state["pause_requested"] = False
        state["current_module"] = None
        _write_state(project, state)
        return

    # -- phase 2: compile the whole design ---------------------------------
    state["phase"] = "compile"
    state["current_module"] = None
    state["current_log"] = str(project.build_path() / "logs" / "compile.log")
    _write_state(project, state)

    comp = compile_design(project)
    _append_log(project, "compile",
                [f"$ {comp.get('command', '')}"] +
                (comp.get("stderr", "") or "").splitlines() +
                [f"-> {'ok' if comp['ok'] else 'FAILED'}"])
    state["compile"] = {k: comp.get(k) for k in ("ok", "top", "output", "command", "errors")}

    if not comp["ok"]:
        first = (comp.get("errors") or [{}])[0]
        state["status"] = "blocked"
        state["blocking_issue"] = {
            "module": comp.get("top"), "file": first.get("file"),
            "error": comp.get("stderr") or comp.get("error", "compile failed"),
            "errors": comp.get("errors", []),
            "log_file": state["current_log"],
        }
        _write_state(project, state)
        return

    state["vvp_binary"] = comp["output"]
    _write_state(project, state)

    # -- phase 3: simulate any testbenches ---------------------------------
    if project.testbenches and not stop_event.is_set():
        state["phase"] = "simulate"
        state["current_log"] = str(project.build_path() / "logs" / "simulate.log")
        _write_state(project, state)

        sim = run_simulation(project)
        _append_log(project, "simulate",
                    [f"$ {sim.get('command', '')}"] +
                    (sim.get("stdout", "") or "").splitlines())
        state["simulation"] = sim
        if not sim.get("ok"):
            state["status"] = "blocked"
            state["blocking_issue"] = {
                "module": sim.get("top"), "file": None,
                "error": sim.get("error", "simulation failed"),
                "errors": [], "log_file": state["current_log"],
            }
            _write_state(project, state)
            return

    state["phase"] = "done"
    state["status"] = "completed"
    state["current_module"] = None
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_state(project, state)


def start_build(project_path: str, gui: bool = False) -> dict:
    """Start a module-by-module build in a background thread.

    Returns immediately with a build_id; poll `get_status` for progress.
    `gui` is accepted for parity with the Vivado plugin and recorded in the
    state so an optional viewer module can act on it; the build itself is
    always headless.
    """
    try:
        project = _resolve(project_path)
    except pj.ProjectError as exc:
        return {"ok": False, "error": str(exc)}

    if not project.all_files():
        return {"ok": False, "error": "project has no sources; add some with write_module or add_sources"}

    key = str(project.root)
    with _lock:
        existing = _active_builds.get(key)
        if existing and existing["thread"].is_alive():
            return {"ok": False, "error": "a build is already running for this project",
                    "build_id": existing["build_id"]}

    build_id = f"{project.name}-{int(time.time())}"
    logdir = project.build_path() / "logs"
    logdir.mkdir(exist_ok=True)
    for old in logdir.glob("*.log"):
        old.unlink()

    state = {
        "build_id": build_id,
        "project_path": key,
        "project_name": project.name,
        "status": "running",
        "phase": "modules",
        "modules": [{"name": m["name"], "file": m["file"], "status": "pending", "error": None}
                    for m in project.modules()],
        "testbenches": [str(t) for t in project.testbenches],
        "current_module": None,
        "current_log": None,
        "blocking_issue": None,
        "compile": None,
        "simulation": None,
        "vvp_binary": None,
        "fix_log": [],
        "gui_enabled": bool(gui),
        "pause_requested": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_state(project, state)

    stop_event = threading.Event()
    t = threading.Thread(target=_orchestrate, args=(key, stop_event, False), daemon=True)
    with _lock:
        _active_builds[key] = {"thread": t, "stop_event": stop_event, "build_id": build_id}
    t.start()
    return {"ok": True, "build_id": build_id, "status": "started",
            "state_file": str(_state_path(project))}


def get_status(project_path: str) -> dict:
    """Full build state plus a tail of whatever log is live right now."""
    try:
        project = _resolve(project_path)
    except pj.ProjectError as exc:
        return {"ok": False, "error": str(exc)}

    state = _read_state(project)
    if state is None:
        return {"ok": True, "status": "not_started", "project_path": str(project.root)}

    tail = []
    log = state.get("current_log")
    if log and pathlib.Path(log).exists():
        tail = [l.rstrip("\n") for l in pathlib.Path(log).read_text(errors="ignore").splitlines()[-20:]]

    out = dict(state)
    out["ok"] = True
    out["log_tail"] = tail
    return out


def get_module_log(project_path: str, module: str, tail_lines: int = 100) -> dict:
    try:
        project = _resolve(project_path)
    except pj.ProjectError as exc:
        return {"ok": False, "error": str(exc)}
    log = project.build_path() / "logs" / f"{module}.log"
    if not log.exists():
        return {"ok": False, "error": f"no log found for module '{module}'"}
    lines = log.read_text(errors="ignore").splitlines()
    return {"ok": True, "module": module, "lines": [l.rstrip() for l in lines[-tail_lines:]]}


def get_blocking_issue(project_path: str) -> dict:
    try:
        project = _resolve(project_path)
    except pj.ProjectError as exc:
        return {"ok": False, "error": str(exc)}
    state = _read_state(project)
    if not state:
        return {"ok": False, "error": "no build found for this project"}
    issue = state.get("blocking_issue")
    if not issue:
        return {"ok": True, "blocked": False,
                "note": f"build is not currently blocked (status={state.get('status')})"}
    return {"ok": True, "blocked": True, **issue}


def apply_fix(project_path: str, file_path: str, new_content: str, note: str = "") -> dict:
    """Overwrite a source file to fix a blocking issue, backing up the
    original to <file>.bak first. Does not resume the build."""
    target = pathlib.Path(file_path).expanduser().resolve()
    if not target.exists():
        return {"ok": False, "error": f"file not found: {target}"}

    backup = target.with_suffix(target.suffix + ".bak")
    backup.write_text(target.read_text(errors="ignore"))
    target.write_text(new_content if new_content.endswith("\n") else new_content + "\n")

    try:
        project = _resolve(project_path)
    except pj.ProjectError:
        return {"ok": True, "status": "applied", "backup": str(backup),
                "note": "file written; project manifest not found so no fix log recorded"}

    state = _read_state(project)
    if state is not None:
        state.setdefault("fix_log", []).append({
            "at": datetime.now(timezone.utc).isoformat(),
            "file": str(target), "note": note, "backup": str(backup),
        })
        _write_state(project, state)
    return {"ok": True, "status": "applied", "backup": str(backup)}


def resume_build(project_path: str, retry_module: bool = True) -> dict:
    """Resume a blocked or paused build.

    If blocked and retry_module is true, the module that caused the block is
    retried; otherwise it stays failed and the build moves on."""
    try:
        project = _resolve(project_path)
    except pj.ProjectError as exc:
        return {"ok": False, "error": str(exc)}

    state = _read_state(project)
    if state is None:
        return {"ok": False, "error": "no build found for this project"}
    if state["status"] not in ("blocked", "paused"):
        return {"ok": False, "error": f"build is not blocked or paused (status={state['status']})"}

    if state["status"] == "blocked" and retry_module:
        blocked_name = (state.get("blocking_issue") or {}).get("module") or state.get("current_module")
        for mod in state["modules"]:
            if mod["name"] == blocked_name or mod["status"] == "error":
                mod["status"] = "pending"
                mod["error"] = None

    state["status"] = "running"
    state["blocking_issue"] = None
    _write_state(project, state)

    key = str(project.root)
    stop_event = threading.Event()
    t = threading.Thread(target=_orchestrate, args=(key, stop_event, True), daemon=True)
    with _lock:
        _active_builds[key] = {"thread": t, "stop_event": stop_event,
                               "build_id": state.get("build_id")}
    t.start()
    return {"ok": True, "status": "resumed"}


def request_pause(project_path: str) -> dict:
    """Ask a running build to pause once the current module finishes."""
    try:
        project = _resolve(project_path)
    except pj.ProjectError as exc:
        return {"ok": False, "error": str(exc)}
    state = _read_state(project)
    if state is None:
        return {"ok": False, "error": "no build found for this project"}
    if state["status"] != "running":
        return {"ok": False, "error": f"build is not running (status={state['status']}); nothing to pause"}
    state["pause_requested"] = True
    _write_state(project, state)
    return {"ok": True, "status": "pause_requested",
            "note": "build will pause once the current module finishes checking"}


def cancel_build(project_path: str) -> dict:
    try:
        project = _resolve(project_path)
    except pj.ProjectError as exc:
        return {"ok": False, "error": str(exc)}
    key = str(project.root)
    with _lock:
        b = _active_builds.get(key)
    if not b or not b["thread"].is_alive():
        return {"ok": False, "error": "no active build for this project"}
    b["stop_event"].set()
    return {"ok": True, "status": "cancel_requested"}


# --------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------

_DUMPFILE_RE = re.compile(r"\$dumpfile\s*\(\s*\"([^\"]+)\"\s*\)")


def _vcd_for_testbench(project: pj.Project, tb: pathlib.Path):
    """The VCD path a testbench will write, from its $dumpfile call."""
    try:
        m = _DUMPFILE_RE.search(tb.read_text(errors="ignore"))
    except OSError:
        return None
    if not m:
        return None
    p = pathlib.Path(m.group(1))
    return p if p.is_absolute() else project.build_path() / p


def run_simulation(project: pj.Project, testbench: str = "", run_seconds: int = 60) -> dict:
    """Compile (if needed) and run a testbench under vvp.

    `testbench` picks one of the project's testbenches by path or module
    name; omitted, the first registered testbench is used. Returns the
    simulator's stdout and the path of any VCD it produced - `vcd` is what a
    waveform viewer module wants.
    """
    tbs = list(project.testbenches)
    if not tbs:
        return {"ok": False, "error": "project has no testbenches; write one with write_module"}

    if testbench:
        want = pathlib.Path(testbench).expanduser()
        chosen = None
        for t in tbs:
            if t == want.resolve() or t.name == want.name or pj.module_name_for_file(t) == testbench:
                chosen = t
                break
        if chosen is None:
            return {"ok": False, "error": f"testbench not found in project: {testbench}",
                    "available": [str(t) for t in tbs]}
    else:
        chosen = tbs[0]

    top = pj.module_name_for_file(chosen)
    output = project.build_path() / f"{top}.vvp"

    files = list(project.sources) + [chosen]
    comp = pj.run_cmd(_iverilog_argv(project, output=output, files=files) ,
                      cwd=project.root, timeout=180)
    if comp["rc"] != 0 or not output.exists():
        diags = parse_diagnostics(comp["stderr"])
        return {"ok": False, "top": top, "phase": "compile",
                "error": comp["stderr"].strip() or "iverilog failed",
                "errors": _errors_only(diags)}

    # vvp resolves relative $dumpfile paths against its cwd, so run it in the
    # build directory to keep VCDs out of the source tree.
    argv = [pj.tool_path("vvp"), str(output)]
    res = pj.run_cmd(argv, cwd=project.build_path(), timeout=max(1, run_seconds))

    vcd = _vcd_for_testbench(project, chosen)
    if vcd is None:
        vcd = project.build_path() / "dump.vcd"
    vcd_path = str(vcd) if pathlib.Path(vcd).exists() else None

    ok = res["rc"] == 0
    return {
        "ok": ok,
        "top": top,
        "testbench": str(chosen),
        "vvp_binary": str(output),
        "command": " ".join(argv),
        "stdout": res["stdout"].strip(),
        "stderr": res["stderr"].strip(),
        "vcd": vcd_path,
        **({} if ok else {"error": res["stderr"].strip() or f"vvp exited {res['rc']}"}),
    }
