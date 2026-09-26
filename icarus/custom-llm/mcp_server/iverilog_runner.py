"""Core orchestration for the iverilog-builder plugin.

Drives Icarus Verilog module-by-module: each source file is checked on its
own (`iverilog -t null`) so progress and errors are attributable to one file
at a time, then the whole design is elaborated into a single `.vvp` for
simulation. State is persisted to `<build_dir>/.build_state.json` so status
can be polled from any process, mirroring the Vivado port's design.
"""

import json
import pathlib
import re
import threading
import time
from datetime import datetime, timezone

import project as pj

_active_builds = {}
_lock = threading.Lock()

#: iverilog's `-g` generation flag per manifest `std` value.
_STD_FLAG = {"1995": "-g1995", "2001": "-g2001", "2005": "-g2005",
             "2009": "-g2009", "2012": "-g2012", "2005-sv": "-g2005-sv"}

# iverilog diagnostics look like: path/file.v:12: error: text
_DIAG_RE = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:\s*(?P<sev>error|warning|sorry))?:?\s*(?P<msg>.*)$")


# --------------------------------------------------------------------------
# diagnostics
# --------------------------------------------------------------------------

def parse_diagnostics(text: str) -> list:
    """Parse iverilog/vvp output into [{file, line, severity, message}].

    Lines that don't carry a file:line prefix are kept as severity "note"
    with file/line None, so nothing an error message said is silently lost.
    """
    out = []
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _DIAG_RE.match(line)
        if m:
            sev = m.group("sev") or ("error" if "error" in line.lower() else "warning")
            out.append({"file": m.group("file"), "line": int(m.group("line")),
                        "severity": sev, "message": m.group("msg").strip()})
        else:
            low = line.lower()
            sev = "error" if low.startswith("error") or ": error" in low else "note"
            out.append({"file": None, "line": None, "severity": sev, "message": line.strip()})
    return out


def _std_flag(p: pj.Project) -> str:
    return _STD_FLAG.get(str(p.std), "-g2012")


def _incl_flags(p: pj.Project) -> list:
    return [f"-I{d}" for d in p.include_dirs]


def _has_errors(diags: list) -> bool:
    return any(d["severity"] in ("error", "sorry") for d in diags)


# --------------------------------------------------------------------------
# compile / lint
# --------------------------------------------------------------------------

def compile_design(p: pj.Project, top: str = None) -> dict:
    """Elaborate every source (plus testbenches, if the top lives in one)
    into a single runnable `.vvp` under the build directory.

    Returns {"ok", "output", "diagnostics", "command", "stderr"}.
    """
    top = top or p.top or (pj.module_name_for_file(p.sources[-1]) if p.sources else "")
    if not p.sources and not p.testbenches:
        return {"ok": False, "error": "project has no sources", "diagnostics": []}

    files = list(p.sources)
    # If the requested top is defined in a testbench, that file has to be
    # part of the elaboration too.
    for tb in p.testbenches:
        if top and pj.module_name_for_file(tb) == top:
            files.append(tb)

    out_path = p.build_path() / f"{top or p.name}.vvp"
    argv = [pj.tool_path("iverilog"), _std_flag(p), *_incl_flags(p), "-o", str(out_path)]
    if top:
        argv += ["-s", top]
    argv += [str(f) for f in files]

    res = pj.run_cmd(argv, cwd=p.root, timeout=300)
    diags = parse_diagnostics(res["stderr"])
    ok = res["rc"] == 0 and out_path.exists()
    result = {"ok": ok, "top": top, "output": str(out_path) if ok else None,
              "diagnostics": diags, "command": " ".join(argv), "stderr": res["stderr"]}
    if not ok:
        result["error"] = res["stderr"].strip() or f"iverilog exited with rc={res['rc']}"
    return result


def lint_file(p: pj.Project, file_path, extra_files=None) -> dict:
    """Syntax/elaboration check for a single file with `iverilog -t null`.

    `extra_files` supplies the rest of the design when the file instantiates
    submodules; missing modules are otherwise reported as errors.
    """
    fp = pathlib.Path(file_path).expanduser().resolve()
    if not fp.exists():
        return {"ok": False, "error": f"file not found: {fp}", "diagnostics": []}
    argv = [pj.tool_path("iverilog"), _std_flag(p), *_incl_flags(p), "-t", "null", str(fp)]
    argv += [str(f) for f in (extra_files or []) if pathlib.Path(f).resolve() != fp]
    res = pj.run_cmd(argv, cwd=p.root, timeout=120)
    diags = parse_diagnostics(res["stderr"])
    return {"ok": res["rc"] == 0 and not _has_errors(diags), "file": str(fp),
            "diagnostics": diags, "command": " ".join(argv), "stderr": res["stderr"]}


def lint_design(p: pj.Project) -> dict:
    """Lint the design as a whole, plus each source file individually."""
    argv = [pj.tool_path("iverilog"), _std_flag(p), *_incl_flags(p), "-t", "null",
            *[str(f) for f in p.sources]]
    res = pj.run_cmd(argv, cwd=p.root, timeout=300)
    diags = parse_diagnostics(res["stderr"])
    per_file = []
    for f in p.sources:
        r = lint_file(p, f, extra_files=p.sources)
        per_file.append({"file": str(f), "ok": r["ok"], "diagnostics": r["diagnostics"]})
    return {"ok": res["rc"] == 0 and not _has_errors(diags), "diagnostics": diags,
            "per_file": per_file, "command": " ".join(argv)}


# --------------------------------------------------------------------------
# build state
# --------------------------------------------------------------------------

def _state_path(p: pj.Project) -> pathlib.Path:
    return p.build_path() / ".build_state.json"


def _log_dir(p: pj.Project) -> pathlib.Path:
    d = p.build_path() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_state(p: pj.Project):
    sp = _state_path(p)
    if not sp.exists():
        return None
    try:
        with open(sp) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_state(p: pj.Project, state: dict):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    sp = _state_path(p)
    tmp = sp.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(sp)


def _key(p: pj.Project) -> str:
    return str(p.root)


def _orchestrate(project_path: str, stop_event: threading.Event, resume: bool = False):
    """Thread body. A crash here must never strand state at 'running'."""
    p = pj.load_project(project_path)
    try:
        _orchestrate_inner(p, stop_event, resume)
    except Exception as exc:  # noqa: BLE001 - deliberately broad
        state = _read_state(p) or {}
        state["status"] = "failed"
        state["blocking_issue"] = {"module": state.get("current_module"),
                                   "file": str(p.manifest_path()),
                                   "error": f"orchestrator crashed: {exc!r}"}
        _write_state(p, state)


def _orchestrate_inner(p: pj.Project, stop_event: threading.Event, resume: bool):
    state = _read_state(p)

    if not resume:
        modules = []
        for f in p.sources:
            modules.append({"name": pj.module_name_for_file(f), "file": str(f),
                            "status": "pending", "error": None})
        state["modules"] = modules
        state["phase"] = "modules"
        _write_state(p, state)

    for mod in state["modules"]:
        if stop_event.is_set():
            state["status"] = "cancelled"
            state["current_module"] = None
            _write_state(p, state)
            return
        if state.get("pause_requested"):
            state["status"] = "paused"
            state["pause_requested"] = False
            state["current_module"] = None
            _write_state(p, state)
            return
        if mod["status"] == "done":
            continue

        mod["status"] = "running"
        state["current_module"] = mod["name"]
        log_path = _log_dir(p) / f"{mod['name']}.log"
        state["current_log"] = str(log_path)
        _write_state(p, state)

        # Re-read the manifest each module so a mid-build apply_fix or
        # write_module (which may add sources) is picked up.
        fresh = pj.load_project(p.root)
        r = lint_file(fresh, mod["file"], extra_files=fresh.sources)
        log_path.write_text((r.get("command", "") + "\n\n" + (r.get("stderr") or "")).strip() + "\n")

        if not r["ok"]:
            mod["status"] = "error"
            mod["error"] = (r.get("stderr") or r.get("error") or "").strip()
            state["status"] = "blocked"
            state["blocking_issue"] = {"module": mod["name"], "file": mod["file"],
                                       "error": mod["error"], "log_file": str(log_path),
                                       "diagnostics": r["diagnostics"]}
            _write_state(p, state)
            return

        mod["status"] = "done"
        mod["error"] = None
        mod["warnings"] = [d for d in r["diagnostics"] if d["severity"] == "warning"]
        _write_state(p, state)

    if state.get("pause_requested"):
        state["status"] = "paused"
        state["pause_requested"] = False
        state["current_module"] = None
        _write_state(p, state)
        return

    # Every module checked out individually - now elaborate the whole design.
    state["phase"] = "elaborate"
    state["current_module"] = None
    flog = _log_dir(p) / "elaborate.log"
    state["current_log"] = str(flog)
    _write_state(p, state)

    fresh = pj.load_project(p.root)
    res = compile_design(fresh, state.get("top") or fresh.top or None)
    flog.write_text((res.get("command", "") + "\n\n" + (res.get("stderr") or "")).strip() + "\n")

    if not res["ok"]:
        state["status"] = "blocked"
        state["blocking_issue"] = {"module": "(top-level)", "file": str(p.manifest_path()),
                                   "error": res.get("error", "elaboration failed"),
                                   "log_file": str(flog),
                                   "diagnostics": res.get("diagnostics", [])}
        _write_state(p, state)
        return

    state["phase"] = "done"
    state["status"] = "completed"
    state["output"] = res["output"]
    state["blocking_issue"] = None
    _write_state(p, state)


def start_build(project_path: str, top: str = None) -> dict:
    """Kick off a background module-by-module build. Returns immediately."""
    p = pj.load_project(project_path)
    if not p.sources:
        return {"ok": False, "error": "project has no sources; add or write a module first"}

    with _lock:
        existing = _active_builds.get(_key(p))
        if existing and existing["thread"].is_alive():
            return {"ok": False, "error": "a build is already running for this project",
                    "build_id": existing["build_id"]}

    build_id = f"{p.name}-{int(time.time())}"
    state = {
        "build_id": build_id, "project_path": str(p.root), "top": top or p.top,
        "status": "running", "phase": "modules", "modules": [],
        "current_module": None, "current_log": None, "blocking_issue": None,
        "output": None, "fix_log": [], "pause_requested": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_state(p, state)

    stop_event = threading.Event()
    t = threading.Thread(target=_orchestrate, args=(str(p.root), stop_event, False), daemon=True)
    with _lock:
        _active_builds[_key(p)] = {"thread": t, "stop_event": stop_event, "build_id": build_id}
    t.start()
    return {"ok": True, "build_id": build_id, "status": "started",
            "state_file": str(_state_path(p))}


def get_status(project_path: str) -> dict:
    """Full build state plus a tail of whatever log is live right now."""
    p = pj.load_project(project_path)
    state = _read_state(p)
    if state is None:
        return {"ok": True, "status": "not_started", "project_path": str(p.root)}
    out = dict(state)
    out["ok"] = True
    tail = []
    lp = state.get("current_log")
    if lp and pathlib.Path(lp).exists():
        tail = pathlib.Path(lp).read_text(errors="ignore").splitlines()[-20:]
    out["log_tail"] = tail
    return out


def get_module_log(project_path: str, module: str, tail_lines: int = 100) -> dict:
    p = pj.load_project(project_path)
    log_path = _log_dir(p) / f"{module}.log"
    if not log_path.exists():
        return {"ok": False, "error": f"no log found for module '{module}'"}
    lines = log_path.read_text(errors="ignore").splitlines()
    return {"ok": True, "module": module, "lines": lines[-tail_lines:]}


def get_blocking_issue(project_path: str) -> dict:
    p = pj.load_project(project_path)
    state = _read_state(p)
    if not state:
        return {"ok": False, "error": "no build found for this project"}
    issue = state.get("blocking_issue")
    if not issue:
        return {"ok": True, "blocked": False, "note": "build is not currently blocked"}
    return {"ok": True, "blocked": True, **issue}


def apply_fix(project_path: str, file_path: str, new_content: str, note: str = "") -> dict:
    """Overwrite a source file, backing the original up to `<file>.bak`."""
    target = pathlib.Path(file_path).expanduser().resolve()
    if not target.exists():
        return {"ok": False, "error": f"file not found: {target}"}
    backup = target.with_suffix(target.suffix + ".bak")
    backup.write_text(target.read_text(errors="ignore"))
    target.write_text(new_content)

    try:
        p = pj.load_project(project_path)
    except FileNotFoundError as exc:
        return {"ok": True, "backup": str(backup), "note": str(exc)}
    state = _read_state(p)
    if state is not None:
        state.setdefault("fix_log", []).append(
            {"at": datetime.now(timezone.utc).isoformat(), "file": str(target), "note": note})
        _write_state(p, state)
    return {"ok": True, "status": "applied", "file": str(target), "backup": str(backup)}


def resume_build(project_path: str, retry_module: bool = True) -> dict:
    p = pj.load_project(project_path)
    state = _read_state(p)
    if state is None:
        return {"ok": False, "error": "no build found for this project"}
    if state["status"] not in ("blocked", "paused"):
        return {"ok": False, "error": f"build is not blocked or paused (status={state['status']})"}

    if state["status"] == "blocked" and retry_module and state.get("current_module"):
        for mod in state["modules"]:
            if mod["name"] == state["current_module"]:
                mod["status"] = "pending"
                mod["error"] = None

    state["status"] = "running"
    state["blocking_issue"] = None
    _write_state(p, state)

    stop_event = threading.Event()
    t = threading.Thread(target=_orchestrate, args=(str(p.root), stop_event, True), daemon=True)
    with _lock:
        _active_builds[_key(p)] = {"thread": t, "stop_event": stop_event,
                                   "build_id": state["build_id"]}
    t.start()
    return {"ok": True, "status": "resumed"}


def request_pause(project_path: str) -> dict:
    """Ask a running build to stop after the current module finishes."""
    p = pj.load_project(project_path)
    state = _read_state(p)
    if state is None:
        return {"ok": False, "error": "no build found for this project"}
    if state["status"] != "running":
        return {"ok": False, "error": f"build is not running (status={state['status']}); nothing to pause"}
    state["pause_requested"] = True
    _write_state(p, state)
    return {"ok": True, "status": "pause_requested",
            "note": "build will pause once the current module finishes checking"}


def cancel_build(project_path: str) -> dict:
    p = pj.load_project(project_path)
    with _lock:
        b = _active_builds.get(_key(p))
    if not b or not b["thread"].is_alive():
        return {"ok": False, "error": "no active build for this project"}
    b["stop_event"].set()
    return {"ok": True, "status": "cancel_requested"}


# --------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------

_DUMPFILE_RE = re.compile(r'\$dumpfile\s*\(\s*"([^"]+)"\s*\)')


def _vcd_from_testbench(p: pj.Project, tb: pathlib.Path):
    """The path the testbench's own `$dumpfile` names, resolved from build_dir."""
    try:
        m = _DUMPFILE_RE.search(tb.read_text(errors="ignore"))
    except OSError:
        return None
    if not m:
        return None
    named = pathlib.Path(m.group(1))
    return named if named.is_absolute() else (p.build_path() / named)


def run_simulation(project_path: str, testbench: str = None, timeout: int = 120) -> dict:
    """Compile the chosen testbench together with the design and run it under vvp.

    `testbench` may be a file path or a bare module name; if omitted, the
    project's single registered testbench is used (an error if ambiguous).
    Returns stdout from the simulation plus the VCD path, if one was written.
    """
    p = pj.load_project(project_path)

    tb = None
    if testbench:
        cand = pathlib.Path(testbench).expanduser()
        if not cand.is_absolute():
            cand = (p.root / cand)
        if cand.exists():
            tb = cand.resolve()
        else:
            for t in p.testbenches:
                if pj.module_name_for_file(t) == testbench or t.stem == testbench:
                    tb = t
                    break
        if tb is None:
            return {"ok": False, "error": f"testbench not found: {testbench}"}
    else:
        if not p.testbenches:
            return {"ok": False, "error": "project has no testbenches; write one first"}
        if len(p.testbenches) > 1:
            return {"ok": False,
                    "error": "project has multiple testbenches; name which one to run",
                    "testbenches": [str(t) for t in p.testbenches]}
        tb = p.testbenches[0]

    tb_top = pj.module_name_for_file(tb)
    vvp_out = p.build_path() / f"{tb_top}.vvp"
    argv = [pj.tool_path("iverilog"), _std_flag(p), *_incl_flags(p), "-o", str(vvp_out),
            "-s", tb_top, str(tb), *[str(s) for s in p.sources]]
    cres = pj.run_cmd(argv, cwd=p.root, timeout=300)
    if cres["rc"] != 0 or not vvp_out.exists():
        return {"ok": False, "error": "compilation of the testbench failed",
                "diagnostics": parse_diagnostics(cres["stderr"]),
                "stderr": cres["stderr"], "command": " ".join(argv)}

    # vvp runs with cwd=build_dir so a relative $dumpfile lands there.
    sres = pj.run_cmd([pj.tool_path("vvp"), str(vvp_out)], cwd=p.build_path(), timeout=timeout)

    vcd = _vcd_from_testbench(p, tb)
    if vcd is None or not vcd.exists():
        fallback = p.build_path() / "dump.vcd"
        vcd = fallback if fallback.exists() else vcd

    sim_log = _log_dir(p) / f"{tb_top}_sim.log"
    sim_log.write_text((sres["stdout"] or "") + (sres["stderr"] or ""))

    return {"ok": sres["rc"] == 0, "testbench": str(tb), "top": tb_top,
            "vvp": str(vvp_out), "stdout": sres["stdout"], "stderr": sres["stderr"],
            "vcd": str(vcd) if vcd and vcd.exists() else None,
            "log_file": str(sim_log),
            **({} if sres["rc"] == 0 else {"error": f"vvp exited with rc={sres['rc']}"})}
