"""Core orchestration logic for the verilog-builder plugin.

Drives Vivado in batch mode module-by-module: extracts the design hierarchy,
synthesizes each module out-of-context so progress is visible per module,
then runs the real project-level synth (and optional implementation) run for
authoritative timing. State is persisted to disk under
<project_dir>/.verilog_builder/ so status can be polled independently of
which process is asking (Claude Code CLI or Claude Desktop).
"""

import json
import os
import pathlib
import re
import subprocess
import threading
import time
from datetime import datetime, timezone

VIVADO_BIN = os.environ.get("VIVADO_BIN", "vivado")
PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
TCL_DIR = PLUGIN_ROOT / "tcl"

_active_builds = {}
_lock = threading.Lock()


def _state_dir(project_xpr: str) -> pathlib.Path:
    d = pathlib.Path(project_xpr).resolve().parent / ".verilog_builder"
    d.mkdir(exist_ok=True)
    (d / "logs").mkdir(exist_ok=True)
    return d


def _state_path(project_xpr: str) -> pathlib.Path:
    return _state_dir(project_xpr) / "state.json"


def _read_state(project_xpr: str):
    p = _state_path(project_xpr)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def _write_state(project_xpr: str, state: dict):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    p = _state_path(project_xpr)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(p)


def _run_vivado(tcl_script: pathlib.Path, tclargs: list, log_path: pathlib.Path, stop_event=None):
    cmd = [VIVADO_BIN, "-mode", "batch", "-nojournal", "-nolog",
           "-source", str(tcl_script), "-tclargs", *[str(a) for a in tclargs]]
    lines = []
    with open(log_path, "w") as logf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1)
        for line in proc.stdout:
            logf.write(line)
            logf.flush()
            lines.append(line.rstrip("\n"))
            if stop_event is not None and stop_event.is_set():
                proc.terminate()
                break
        proc.wait()
    return proc.returncode, lines


def _looks_like_testbench(filename: str) -> bool:
    lower = filename.lower()
    return bool(re.search(r"(^|_)tb(_|\.)", lower)) or "testbench" in lower


def _module_name_for_file(filepath: pathlib.Path) -> str:
    text = filepath.read_text(errors="ignore")
    m = re.search(r"\bmodule\s+(\w+)", text)
    return m.group(1) if m else filepath.stem


def _parse_compile_order(report_path: pathlib.Path, search_root: pathlib.Path):
    if not report_path.exists():
        return []
    text = report_path.read_text(errors="ignore")
    candidates = re.findall(r"(\S+\.(?:v|sv|vh|svh))\b", text)
    seen, resolved = [], []
    for c in candidates:
        if c in seen:
            continue
        seen.append(c)
        p = pathlib.Path(c)
        if not p.is_absolute():
            p = search_root / c
        if p.exists():
            resolved.append(p.resolve())
    return resolved


def parse_timing_summary(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"raw_report": str(path), "wns": None, "tns": None, "whs": None,
                "ths": None, "note": "report not found"}
    text = path.read_text(errors="ignore")
    m = re.search(
        r"WNS\(ns\)\s+TNS\(ns\).*?\n-+.*?\n\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+"
        r"(-?\d+\.\d+)\s+(-?\d+\.\d+)",
        text, re.S)
    result = {"raw_report": str(path)}
    if m:
        result.update({"wns": float(m.group(1)), "tns": float(m.group(2)),
                        "whs": float(m.group(3)), "ths": float(m.group(4))})
    else:
        result.update({"wns": None, "tns": None, "whs": None, "ths": None,
                        "note": "could not parse summary table automatically; read raw_report"})
    return result


def list_projects(search_root: str = "~") -> list:
    root = pathlib.Path(search_root).expanduser()
    xprs = list(root.glob("*.xpr")) + list(root.glob("*/*.xpr"))
    seen, out = set(), []
    for x in xprs:
        rx = x.resolve()
        if rx in seen:
            continue
        seen.add(rx)
        out.append({"name": x.stem, "path": str(rx)})
    return out


def _orchestrate(project_xpr: str, mode: str, stop_event: threading.Event, resume: bool = False):
    try:
        _orchestrate_inner(project_xpr, mode, stop_event, resume)
    except Exception as exc:
        # A crash here (bad env, missing binary, bug) must never leave
        # state.json stuck at "running" forever with no explanation.
        state = _read_state(project_xpr) or {}
        state["status"] = "failed"
        state["blocking_issue"] = {
            "module": state.get("current_module"), "file": project_xpr,
            "error": f"orchestrator crashed: {exc!r}",
        }
        _write_state(project_xpr, state)


def _orchestrate_inner(project_xpr: str, mode: str, stop_event: threading.Event, resume: bool = False):
    sdir = _state_dir(project_xpr)
    state = _read_state(project_xpr)

    if not resume:
        hlog = sdir / "logs" / "hierarchy.log"
        state["current_log"] = str(hlog)
        _write_state(project_xpr, state)
        rc, lines = _run_vivado(TCL_DIR / "get_hierarchy.tcl", [project_xpr, sdir], hlog, stop_event)
        if rc != 0:
            state["status"] = "failed"
            state["phase"] = "hierarchy"
            state["blocking_issue"] = {"module": None, "file": project_xpr,
                                        "error": "\n".join(lines[-40:]), "log_file": str(hlog)}
            _write_state(project_xpr, state)
            return

        files = _parse_compile_order(sdir / "compile_order.rpt", pathlib.Path(project_xpr).parent)
        modules = []
        for f in files:
            if _looks_like_testbench(f.name):
                continue
            modules.append({"name": _module_name_for_file(f), "file": str(f),
                             "status": "pending", "error": None})
        state["modules"] = modules
        state["phase"] = "modules"
        _write_state(project_xpr, state)

    for mod in state["modules"]:
        if stop_event.is_set():
            state["status"] = "cancelled"
            _write_state(project_xpr, state)
            return
        if mod["status"] == "done":
            continue

        mod["status"] = "running"
        state["current_module"] = mod["name"]
        mlog = sdir / "logs" / f"{mod['name']}.log"
        state["current_log"] = str(mlog)
        _write_state(project_xpr, state)

        rc, lines = _run_vivado(TCL_DIR / "synth_module.tcl",
                                 [project_xpr, mod["name"], sdir], mlog, stop_event)
        if rc != 0:
            mod["status"] = "error"
            mod["error"] = "\n".join(lines[-40:])
            state["status"] = "blocked"
            state["blocking_issue"] = {"module": mod["name"], "file": mod["file"],
                                        "error": mod["error"], "log_file": str(mlog)}
            _write_state(project_xpr, state)
            return

        mod["status"] = "done"
        mod["error"] = None
        _write_state(project_xpr, state)

    state["phase"] = "full_synth"
    state["current_module"] = None
    do_impl = "impl" if mode == "full" else "synth_only"
    flog = sdir / "logs" / "full_synth.log"
    state["current_log"] = str(flog)
    _write_state(project_xpr, state)

    rc, lines = _run_vivado(TCL_DIR / "synth_full.tcl", [project_xpr, sdir, do_impl], flog, stop_event)
    if rc != 0:
        state["status"] = "blocked"
        state["blocking_issue"] = {"module": "(top-level)", "file": project_xpr,
                                    "error": "\n".join(lines[-40:]), "log_file": str(flog)}
        _write_state(project_xpr, state)
        return

    state["phase"] = "done"
    state["status"] = "completed"
    timing_file = sdir / ("full_impl_timing.rpt" if do_impl == "impl" else "full_synth_timing.rpt")
    state["timing"] = parse_timing_summary(timing_file)
    _write_state(project_xpr, state)


def start_build(project_path: str, mode: str = "synth") -> dict:
    project_xpr = str(pathlib.Path(project_path).expanduser().resolve())
    if not pathlib.Path(project_xpr).exists():
        return {"error": f"project not found: {project_xpr}"}

    with _lock:
        existing = _active_builds.get(project_xpr)
        if existing and existing["thread"].is_alive():
            return {"error": "a build is already running for this project", "build_id": existing["build_id"]}

    build_id = f"{pathlib.Path(project_xpr).stem}-{int(time.time())}"
    state = {
        "build_id": build_id, "project_path": project_xpr, "mode": mode,
        "status": "running", "phase": "hierarchy", "modules": [],
        "current_module": None, "current_log": None, "blocking_issue": None, "timing": None,
        "fix_log": [], "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_state(project_xpr, state)

    stop_event = threading.Event()
    t = threading.Thread(target=_orchestrate, args=(project_xpr, mode, stop_event), daemon=True)
    with _lock:
        _active_builds[project_xpr] = {"thread": t, "stop_event": stop_event, "build_id": build_id}
    t.start()
    return {"build_id": build_id, "status": "started", "state_file": str(_state_path(project_xpr))}


def get_status(project_path: str) -> dict:
    project_xpr = str(pathlib.Path(project_path).expanduser().resolve())
    state = _read_state(project_xpr)
    if state is None:
        return {"status": "not_started"}

    log_path = pathlib.Path(state["current_log"]) if state.get("current_log") else None

    tail = []
    if log_path is not None and log_path.exists():
        with open(log_path) as f:
            tail = [l.rstrip("\n") for l in f.readlines()[-20:]]

    out = dict(state)
    out["log_tail"] = tail
    return out


def get_module_log(project_path: str, module: str, tail_lines: int = 100) -> dict:
    project_xpr = str(pathlib.Path(project_path).expanduser().resolve())
    sdir = _state_dir(project_xpr)
    log_path = sdir / "logs" / f"{module}.log"
    if not log_path.exists():
        return {"error": f"no log found for module '{module}'"}
    with open(log_path) as f:
        lines = f.readlines()
    return {"module": module, "lines": [l.rstrip("\n") for l in lines[-tail_lines:]]}


def get_blocking_issue(project_path: str) -> dict:
    project_xpr = str(pathlib.Path(project_path).expanduser().resolve())
    state = _read_state(project_xpr)
    if not state:
        return {"error": "no build found for this project"}
    return state.get("blocking_issue") or {"note": "build is not currently blocked"}


def apply_fix(project_path: str, file_path: str, new_content: str, note: str = "") -> dict:
    target = pathlib.Path(file_path).expanduser().resolve()
    if not target.exists():
        return {"error": f"file not found: {target}"}

    backup = target.with_suffix(target.suffix + ".bak")
    backup.write_text(target.read_text())
    target.write_text(new_content)

    project_xpr = str(pathlib.Path(project_path).expanduser().resolve())
    state = _read_state(project_xpr)
    if state is not None:
        state.setdefault("fix_log", []).append({
            "at": datetime.now(timezone.utc).isoformat(), "file": str(target), "note": note,
        })
        _write_state(project_xpr, state)

    return {"status": "applied", "backup": str(backup)}


def resume_build(project_path: str, retry_module: bool = True) -> dict:
    project_xpr = str(pathlib.Path(project_path).expanduser().resolve())
    state = _read_state(project_xpr)
    if state is None:
        return {"error": "no build found for this project"}
    if state["status"] != "blocked":
        return {"error": f"build is not blocked (status={state['status']})"}

    if retry_module and state.get("current_module"):
        for mod in state["modules"]:
            if mod["name"] == state["current_module"]:
                mod["status"] = "pending"
                mod["error"] = None

    state["status"] = "running"
    state["blocking_issue"] = None
    _write_state(project_xpr, state)

    stop_event = threading.Event()
    t = threading.Thread(target=_orchestrate,
                          args=(project_xpr, state.get("mode", "synth"), stop_event, True), daemon=True)
    with _lock:
        _active_builds[project_xpr] = {"thread": t, "stop_event": stop_event, "build_id": state["build_id"]}
    t.start()
    return {"status": "resumed"}


def cancel_build(project_path: str) -> dict:
    project_xpr = str(pathlib.Path(project_path).expanduser().resolve())
    with _lock:
        b = _active_builds.get(project_xpr)
    if not b or not b["thread"].is_alive():
        return {"error": "no active build for this project"}
    b["stop_event"].set()
    return {"status": "cancel_requested"}
