"""RTL schematic generation for the iverilog-builder plugin, via yosys.

This is the open-source counterpart to Vivado's "Open Elaborated Design"
schematic view: point it at a project, and it elaborates the design with
yosys and renders a diagram - no GUI steps, no hand-written scripts.

Two levels are offered:

* ``rtl``  (default) - ``hierarchy; proc; opt_clean`` only. Keeps adders,
  muxes and registers as recognisable RTL blocks. This is what a beginner
  wants to look at.
* ``gate`` - a full ``synth -top``, i.e. the gate-level netlist. Accurate,
  but big and hard to read for anything non-trivial.

Rendering prefers ``netlistsvg`` (readable, schematic-style symbols) and
falls back to graphviz ``dot`` when netlistsvg is missing or fails.

Registered as an optional companion module - see CONTRACT.md §7.
"""

import os
import pathlib
import re
import shutil
import subprocess

import project as pj

#: yosys prints errors as "ERROR: ..." and warnings as "Warning: ...".
_YOSYS_ERR_RE = re.compile(
    r"^(?P<sev>ERROR|Warning)\s*:\s*(?P<msg>.*)$", re.IGNORECASE)

#: Yosys usually names the offending source as `file.v:12` inside the message.
_YOSYS_LOC_RE = re.compile(r"(?P<file>[\w./\\+-]+\.(?:sv|svh|vh|v)):(?P<line>\d+)")

_LEVELS = ("rtl", "gate")
_FORMATS = ("svg", "png", "dot", "json")


# --------------------------------------------------------------------------
# diagnostics
# --------------------------------------------------------------------------

def parse_yosys_diagnostics(text: str) -> list:
    """Parse yosys output into the plugin's shared diagnostic shape.

    Returns [{file, line, severity, message}] exactly like
    iverilog_runner.parse_diagnostics, so the assistant can explain a yosys
    failure the same way it explains an iverilog one. Only lines that carry
    an ERROR/Warning marker are kept - yosys is extremely chatty otherwise.
    """
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _YOSYS_ERR_RE.match(line)
        if not m:
            continue
        sev = "error" if m.group("sev").lower() == "error" else "warning"
        msg = m.group("msg").strip()
        loc = _YOSYS_LOC_RE.search(msg)
        f, ln = (loc.group("file"), int(loc.group("line"))) if loc else (None, None)
        out.append({"file": f, "line": ln, "severity": sev, "message": msg})
    return out


def _has_errors(diags: list) -> bool:
    return any(d["severity"] == "error" for d in diags)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _schematic_dir(p: pj.Project) -> pathlib.Path:
    d = p.build_path() / "schematic"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _all_sources(p: pj.Project) -> list:
    """Design sources only - testbenches are not part of a schematic."""
    return [s for s in p.sources if s.suffix.lower() in (".v", ".sv")]


def _resolve_top(p: pj.Project, top: str = None) -> str:
    if top:
        return top
    if p.top:
        return p.top
    srcs = _all_sources(p)
    if len(srcs) == 1:
        return pj.module_name_for_file(srcs[0])
    return ""


def _read_flags(p: pj.Project) -> str:
    flags = ["-sv"]
    for d in p.include_dirs:
        flags.append(f"-I{d}")
    return " ".join(flags)


def build_script(p: pj.Project, top: str, level: str = "rtl",
                 want_json: str = None, want_dot: str = None) -> str:
    """Assemble the .ys script text for one schematic run."""
    lines = []
    read = _read_flags(p)
    for s in _all_sources(p):
        lines.append(f'read_verilog {read} "{s}"')
    if level == "gate":
        # -flatten so the gate view of the top actually shows gates rather
        # than a box per sub-module (which is what the RTL view already is).
        lines.append(f"synth -top {top} -flatten")
    else:
        lines.append(f"hierarchy -top {top} -check")
        lines.append("proc")
        lines.append("opt_clean")
    if want_json:
        lines.append(f'write_json "{want_json}"')
    if want_dot:
        # `show -prefix` does not strip quotes, so it must stay unquoted; the
        # script runs with cwd = the schematic dir, so a bare stem is enough.
        prefix = want_dot[:-4] if want_dot.endswith(".dot") else want_dot
        prefix = pathlib.Path(prefix).name
        lines.append(f"show -format dot -prefix {prefix} -notitle {top}")
    lines.append("stat")
    return "\n".join(lines) + "\n"


def _run_yosys(p: pj.Project, script: str, timeout: int = 180) -> dict:
    """Write the script to the schematic dir and run yosys on it."""
    sdir = _schematic_dir(p)
    ys = sdir / "schematic.ys"
    ys.write_text(script)
    yosys = pj.tool_path("yosys")
    argv = [yosys, "-s", str(ys)]  # not -q: `stat`/`ls` output is on stdout
    res = pj.run_cmd(argv, cwd=str(sdir), timeout=timeout)
    res["command"] = " ".join(argv)
    res["script"] = str(ys)
    return res


def _list_modules(p: pj.Project) -> list:
    """Ask yosys which modules the sources actually define.

    Used to give a useful error when the requested top doesn't exist.
    """
    read = _read_flags(p)
    lines = [f'read_verilog {read} "{s}"' for s in _all_sources(p)]
    lines.append("ls")
    res = _run_yosys(p, "\n".join(lines) + "\n", timeout=60)
    mods = []
    grabbing = False
    for line in (res.get("stdout") or "").splitlines():
        s = line.strip()
        if s.endswith("modules:"):
            grabbing = True
            continue
        if grabbing:
            if not s:
                grabbing = False
                continue
            mods.append(s.lstrip("$\\"))
    return mods


def _no_top_error(p: pj.Project, top: str) -> dict:
    mods = _list_modules(p)
    if top:
        err = (f"yosys could not elaborate top module '{top}'. "
               f"Modules found in this project: {', '.join(mods) or '(none)'}")
    else:
        err = ("No top module given and the project manifest has none. "
               f"Modules found: {', '.join(mods) or '(none)'}. "
               "Pass top=<module name>.")
    return {"ok": False, "error": err, "modules": mods, "top": top or None}


# --------------------------------------------------------------------------
# stat parsing
# --------------------------------------------------------------------------

def parse_stats(text: str) -> dict:
    """Parse the output of yosys `stat` into structured counts.

    Returns {"modules": {name: {wires, wire_bits, public_wires, cells,
    memories, memory_bits, processes, cell_types: {...}}}, "top": name}.
    """
    modules = {}
    cur = None
    in_cells = False
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        s = line.strip()
        if s.startswith("=== ") and s.endswith(" ==="):
            name = s[4:-4].strip().lstrip("\\")
            if name.startswith("design hierarchy"):
                cur = None
                continue
            cur = {"wires": 0, "wire_bits": 0, "public_wires": 0,
                   "public_wire_bits": 0, "cells": 0, "memories": 0,
                   "memory_bits": 0, "processes": 0, "cell_types": {}}
            modules[name] = cur
            in_cells = False
            continue
        if cur is None:
            continue
        if s.startswith("Number of "):
            m = re.match(r"Number of ([\w ]+?)\s*:\s*(\d+)", s)
            if m:
                key = m.group(1).strip().replace(" ", "_")
                cur[key] = int(m.group(2))
            in_cells = s.startswith("Number of cells")
            continue
        if in_cells and s:
            m = re.match(r"(\S+)\s+(\d+)$", s)
            if m:
                cur["cell_types"][m.group(1).lstrip("$\\")] = int(m.group(2))
    return modules


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _render_netlistsvg(json_path: pathlib.Path, svg_path: pathlib.Path) -> dict:
    exe = shutil.which("netlistsvg") or "/usr/local/bin/netlistsvg"
    if not os.path.exists(exe):
        return {"rc": -2, "stderr": "netlistsvg not installed", "stdout": "",
                "command": "netlistsvg"}
    argv = [exe, str(json_path), "-o", str(svg_path)]
    res = pj.run_cmd(argv, cwd=str(json_path.parent), timeout=180)
    res["command"] = " ".join(argv)
    return res


def _render_dot(dot_path: pathlib.Path, out_path: pathlib.Path, fmt: str) -> dict:
    exe = shutil.which("dot") or "/usr/bin/dot"
    argv = [exe, f"-T{fmt}", str(dot_path), "-o", str(out_path)]
    res = pj.run_cmd(argv, cwd=str(dot_path.parent), timeout=180)
    res["command"] = " ".join(argv)
    return res


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def generate_schematic(project_path: str, top: str = None, level: str = "rtl",
                       fmt: str = "svg") -> dict:
    """Elaborate the design with yosys and render a schematic.

    level: "rtl" (default, readable) or "gate" (post-synth netlist).
    fmt:   "svg" (default), "png", "dot" or "json".
    """
    level = (level or "rtl").lower()
    fmt = (fmt or "svg").lower()
    if level not in _LEVELS:
        return {"ok": False, "error": f"level must be one of {_LEVELS}, got {level!r}"}
    if fmt not in _FORMATS:
        return {"ok": False, "error": f"fmt must be one of {_FORMATS}, got {fmt!r}"}

    p = pj.load_project(project_path)
    srcs = _all_sources(p)
    if not srcs:
        return {"ok": False, "error": f"project '{p.name}' has no Verilog sources registered"}

    top = _resolve_top(p, top)
    if not top:
        return _no_top_error(p, top)

    sdir = _schematic_dir(p)
    stem = f"{top}_{level}"
    json_path = sdir / f"{stem}.json"
    dot_path = sdir / f"{stem}.dot"

    # Always emit both intermediates: json feeds netlistsvg, dot feeds graphviz
    # (and is the fallback), and both are cheap next to the elaboration itself.
    script = build_script(p, top, level, want_json=str(json_path), want_dot=str(dot_path))
    res = _run_yosys(p, script)
    log = ((res.get("stdout") or "") + "\n" + (res.get("stderr") or "")).strip()
    log_file = sdir / f"{stem}.log"
    log_file.write_text(log)
    diags = parse_yosys_diagnostics(log)

    if res["rc"] != 0 or _has_errors(diags):
        joined = " ".join(d["message"] for d in diags if d["severity"] == "error")
        if "not found" in joined.lower() or "no top module" in joined.lower():
            out = _no_top_error(p, top)
            out.update({"diagnostics": diags, "log": log, "log_file": str(log_file),
                        "command": res["command"]})
            return out
        return {"ok": False,
                "error": (diags[0]["message"] if diags else
                          (res.get("stderr") or "yosys failed").strip()[:400]),
                "top": top, "level": level, "diagnostics": diags,
                "log": log, "log_file": str(log_file), "command": res["command"]}

    stats = parse_stats(res.get("stdout") or "")
    renderer = None
    render_log = ""

    if fmt == "json":
        path = json_path
    elif fmt == "dot":
        path = dot_path
        renderer = "yosys show"
    else:
        path = sdir / f"{stem}.{fmt}"
        if fmt == "svg" and json_path.exists():
            r = _render_netlistsvg(json_path, path)
            render_log = ((r.get("stdout") or "") + (r.get("stderr") or "")).strip()
            if r["rc"] == 0 and path.exists() and path.stat().st_size > 0:
                renderer = "netlistsvg"
        if renderer is None:
            if not dot_path.exists():
                return {"ok": False, "error": "yosys produced no .dot to render from",
                        "top": top, "level": level, "log": log,
                        "log_file": str(log_file), "command": res["command"]}
            r = _render_dot(dot_path, path, fmt)
            render_log = (render_log + "\n" +
                          ((r.get("stdout") or "") + (r.get("stderr") or ""))).strip()
            if r["rc"] != 0 or not path.exists():
                return {"ok": False,
                        "error": f"rendering failed: {render_log[:400] or 'graphviz dot failed'}",
                        "top": top, "level": level, "log": log,
                        "log_file": str(log_file), "command": r["command"]}
            renderer = "graphviz"

    if not path.exists() or path.stat().st_size == 0:
        return {"ok": False, "error": f"expected output {path} was not produced",
                "top": top, "level": level, "log": log, "log_file": str(log_file),
                "command": res["command"]}

    out = {"ok": True, "path": str(path), "format": fmt, "top": top, "level": level,
           "renderer": renderer, "stats": stats,
           "json": str(json_path) if json_path.exists() else None,
           "dot": str(dot_path) if dot_path.exists() else None,
           "warnings": [d for d in diags if d["severity"] == "warning"],
           "log_file": str(log_file), "log": log[-4000:],
           "command": res["command"]}
    if fmt == "svg":
        out["svg"] = str(path)
    if render_log:
        out["render_log"] = render_log[-2000:]
    return out


def get_netlist_stats(project_path: str, top: str = None) -> dict:
    """Elaborate with yosys and report cell/wire/memory counts - no rendering."""
    p = pj.load_project(project_path)
    if not _all_sources(p):
        return {"ok": False, "error": f"project '{p.name}' has no Verilog sources registered"}
    top = _resolve_top(p, top)
    if not top:
        return _no_top_error(p, top)

    script = build_script(p, top, "rtl")
    res = _run_yosys(p, script)
    log = ((res.get("stdout") or "") + "\n" + (res.get("stderr") or "")).strip()
    diags = parse_yosys_diagnostics(log)
    if res["rc"] != 0 or _has_errors(diags):
        out = _no_top_error(p, top)
        out["diagnostics"] = diags
        if diags and _has_errors(diags):
            out["error"] = diags[0]["message"]
        out["command"] = res["command"]
        return out

    stats = parse_stats(res.get("stdout") or "")
    top_stats = stats.get(top) or stats.get("\\" + top) or {}
    return {"ok": True, "top": top, "level": "rtl", "stats": stats,
            "top_stats": top_stats,
            "warnings": [d for d in diags if d["severity"] == "warning"],
            "command": res["command"]}


def open_schematic(path: str = None, project_path: str = None) -> dict:
    """Best-effort open a rendered schematic in the user's desktop viewer.

    Never blocks and never raises: on a headless machine it just reports that
    there's no display and hands back the file path.
    """
    target = None
    if path:
        target = pathlib.Path(path).expanduser()
    elif project_path:
        p = pj.load_project(project_path)
        sdir = p.build_path() / "schematic"
        cands = sorted(sdir.glob("*.svg"), key=lambda f: f.stat().st_mtime, reverse=True) \
            if sdir.is_dir() else []
        if not cands:
            cands = sorted(sdir.glob("*.png"), key=lambda f: f.stat().st_mtime,
                           reverse=True) if sdir.is_dir() else []
        if not cands:
            return {"ok": False, "error": "no rendered schematic found - "
                                          "run generate_schematic first"}
        target = cands[0]
    else:
        return {"ok": False, "error": "pass either path or project_path"}

    if not target.exists():
        return {"ok": False, "error": f"no such file: {target}"}

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"ok": False, "opened": False, "path": str(target),
                "error": "no graphical display available (DISPLAY unset) - "
                         "open the file yourself, or view the SVG inline"}

    if target.suffix == ".dot" and (shutil.which("xdot") or os.path.exists("/usr/bin/xdot")):
        argv = [shutil.which("xdot") or "/usr/bin/xdot", str(target)]
    else:
        opener = shutil.which("xdg-open") or "/usr/bin/xdg-open"
        argv = [opener, str(target)]

    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": str(target), "opened": False,
                "error": f"could not launch viewer: {exc}"}
    return {"ok": True, "opened": True, "path": str(target),
            "command": " ".join(argv)}


# --------------------------------------------------------------------------
# MCP registration
# --------------------------------------------------------------------------

def register(mcp):
    """Declare the schematic tools on the server (see CONTRACT.md §7)."""

    def _fail(exc) -> dict:
        return {"ok": False, "error": str(exc)}

    @mcp.tool()
    def generate_schematic(project_path: str, top: str = "", level: str = "rtl",
                           fmt: str = "svg") -> dict:
        """Draw the schematic of a design - the open-source equivalent of
        Vivado's "Open Elaborated Design" view.

        level="rtl" (default) keeps adders, muxes and registers as
        recognisable blocks and is what you want to look at; level="gate"
        runs a full synthesis and shows the gate-level netlist instead.
        fmt: "svg" (default, most readable), "png", "dot" or "json".

        top: omit to use the project's top module. Output lands in
        <build_dir>/schematic/. Returns the file path - call open_schematic
        to pop it up on screen.
        """
        try:
            return globals()["generate_schematic"](project_path, top or None, level, fmt)
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @mcp.tool()
    def get_netlist_stats(project_path: str, top: str = "") -> dict:
        """Report how much hardware a design elaborates to: counts of wires,
        cells (by type), memories and processes, per module. Cheap and
        text-only - no viewer needed, good for a quick 'how big is this?'."""
        try:
            return globals()["get_netlist_stats"](project_path, top or None)
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @mcp.tool()
    def open_schematic(path: str = "", project_path: str = "") -> dict:
        """Open a rendered schematic in the desktop image viewer.

        Pass the path returned by generate_schematic, or just project_path to
        open the most recent one. On a machine with no display this reports
        that cleanly instead of hanging."""
        try:
            return globals()["open_schematic"](path or None, project_path or None)
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @mcp.tool()
    def list_design_modules(project_path: str) -> dict:
        """List every module yosys can see in the project's sources - handy
        when you're not sure what to pass as `top`."""
        try:
            p = pj.load_project(project_path)
            return {"ok": True, "modules": _list_modules(p), "top": p.top or None}
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)
