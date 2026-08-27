"""RTL schematic generation for the Icarus Verilog plugin.

This is the open-source counterpart to Vivado's "Open Elaborated Design"
schematic view: yosys elaborates the design, and either netlistsvg or
graphviz renders it, so the user prompts once and a schematic appears.

The default level is `rtl` - `read_verilog; hierarchy; proc; opt_clean` and
nothing more. Running a full `synth` here would technology-map the design
into a few thousand gates, which is accurate and completely unreadable; the
gate-level view is available on request via level="gate".

Stdlib-only, and safe to import with yosys missing - every binary is resolved
at call time through `project.tool_path`.

See CONTRACT.md for the API this builds on.
"""

import os
import re
import shutil
import subprocess

import project as pj

LEVELS = ("rtl", "gate")
FORMATS = ("svg", "png", "dot", "json")

# yosys diagnostics: "ERROR: ..." / "Warning: ...", sometimes carrying a
# "file.v:12:" or "file.v:12.5-12.9:" location somewhere in the message.
_SEVERITY_RE = re.compile(
    r"^\s*(?:(?P<file>[\w./\\-]+\.(?:sv|v|vh|svh)):(?P<line>\d+):\s*)?"
    r"(?P<severity>ERROR|Warning|Note)\s*:\s*(?P<message>.*)$")
_LOCATION_RE = re.compile(r"(?P<file>[\w./\\-]+\.(?:sv|v|vh|svh)):(?P<line>\d+)")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def parse_diagnostics(text: str) -> list:
    """Parse yosys output into [{file, line, severity, message}].

    Matches the shape `iverilog_runner.parse_diagnostics` produces so the
    slash commands can render errors from either tool identically.
    """
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _SEVERITY_RE.match(line)
        if not m:
            continue
        message = m.group("message").strip()
        severity = {"ERROR": "error", "Warning": "warning", "Note": "info"}[m.group("severity")]
        loc = _LOCATION_RE.search(message)
        file_ = m.group("file") or (loc.group("file") if loc else None)
        line_no = m.group("line") or (loc.group("line") if loc else None)
        out.append({
            "file": file_,
            "line": int(line_no) if line_no else None,
            "severity": severity,
            "message": message,
        })
    return out


def _errors_only(diags: list) -> list:
    return [d for d in diags if d["severity"] == "error"]


def _schematic_dir(project) -> "os.PathLike":
    out = project.build_path() / "schematic"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _read_files(project) -> list:
    """Design sources only - a testbench has no place in a schematic."""
    return [str(p) for p in project.sources] or [str(p) for p in project.all_files()]


def _quote(path: str) -> str:
    return '"%s"' % str(path).replace('"', '\\"')


def _script(project, top: str, level: str, backend: str, out_base) -> str:
    """Build the .ys script text for one schematic run."""
    lines = []
    for inc in project.include_dirs:
        lines.append("verilog_defaults -add -I%s" % inc)
    lines.append("read_verilog -sv %s" % " ".join(_quote(f) for f in _read_files(project)))
    if level == "gate":
        # -flatten so the gate view of the top actually shows gates: without
        # it netlistsvg renders only the top module, which for a hierarchical
        # design is just the submodule instances - visually identical to the
        # rtl view even though the netlist underneath is technology-mapped.
        lines.append("synth -top %s -flatten" % top)
    else:
        lines.append("hierarchy -top %s -check" % top)
        lines.append("proc")
        lines.append("opt_clean")
    if backend == "json":
        lines.append("write_json %s" % _quote(str(out_base) + ".json"))
    else:
        # yosys `show` takes -prefix as a bare token (quotes end up in the
        # filename), so pass a basename and rely on cwd being the output dir.
        lines.append("show -format dot -prefix %s -notitle -stretch" % os.path.basename(str(out_base)))
    return "\n".join(lines) + "\n"


def _run_yosys(project, script_text: str, out_dir, timeout: int = 180) -> dict:
    ys_path = out_dir / "schematic.ys"
    ys_path.write_text(script_text)
    # No -q: the pass log on stdout is what `stat`/`ls` parsing reads.
    argv = [pj.tool_path("yosys"), "-s", str(ys_path)]
    res = pj.run_cmd(argv, cwd=str(out_dir), timeout=timeout)
    res["command"] = " ".join(argv)
    res["script"] = script_text
    res["script_path"] = str(ys_path)
    return res


def list_modules(project) -> dict:
    """Every module yosys can see in the design sources."""
    files = _read_files(project)
    if not files:
        return {"ok": False, "error": "This project has no design sources registered.",
                "modules": []}
    out_dir = _schematic_dir(project)
    script = "read_verilog -sv %s\nls\n" % " ".join(_quote(f) for f in files)
    res = _run_yosys(project, script, out_dir, timeout=60)
    names = []
    in_list = False
    for line in (res["stdout"] or "").splitlines():
        if re.match(r"^\d+ modules:$", line.strip()):
            in_list = True
            continue
        if in_list:
            m = re.match(r"^\s{2}(\S+)\s*$", line)
            if m and not m.group(1).startswith("$"):
                names.append(m.group(1).lstrip("\\"))
            else:
                in_list = False
    if not names:
        names = [m["name"] for m in project.modules() if m.get("name")]
    return {"ok": True, "modules": sorted(set(names)), "command": res["command"]}


def _resolve_top(project, top: str) -> tuple:
    """(top_name, error_dict_or_None)."""
    chosen = (top or project.top or "").strip()
    found = list_modules(project)
    known = found.get("modules") or []
    if not chosen:
        if len(known) == 1:
            return known[0], None
        if known:
            msg = ("No top module given and the project doesn't record one. "
                   "Pick one of: %s" % ", ".join(known))
        else:
            msg = "No modules were found in this project's design sources."
        return "", {"ok": False, "error": msg, "modules": known}
    if known and chosen not in known:
        return "", {
            "ok": False,
            "error": "No module named %r in this project. Available modules: %s"
                     % (chosen, ", ".join(known)),
            "modules": known,
        }
    return chosen, None


# --------------------------------------------------------------------------
# schematic generation
# --------------------------------------------------------------------------

def _render_netlistsvg(json_path, svg_path) -> dict:
    argv = [pj.tool_path("netlistsvg"), str(json_path), "-o", str(svg_path)]
    res = pj.run_cmd(argv, timeout=180)
    res["command"] = " ".join(argv)
    res["ok"] = res["rc"] == 0 and svg_path.exists() and svg_path.stat().st_size > 0
    return res


def _render_dot(dot_path, out_path, fmt: str) -> dict:
    # Not pj.run_cmd: graphviz can echo binary image data on stdout, which
    # blows up text-mode decoding, so capture bytes and decode leniently.
    argv = [pj.tool_path("dot"), "-T%s" % fmt, str(dot_path), "-o", str(out_path)]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=180)
        rc, err = proc.returncode, proc.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        rc, err = 124, "graphviz timed out after 180s"
    except OSError as exc:
        rc, err = 127, "could not run %s: %s" % (argv[0], exc)
    return {"rc": rc, "stdout": "", "stderr": err, "command": " ".join(argv),
            "ok": rc == 0 and out_path.exists() and out_path.stat().st_size > 0}


def generate_schematic(project, top: str = "", level: str = "rtl", fmt: str = "svg") -> dict:
    """Elaborate the design with yosys and render a schematic.

    Returns {"ok", "top", "level", "format", "schematic", "renderer",
    "command", "errors", "stderr"} - `schematic` is the absolute output path.
    """
    level = (level or "rtl").lower()
    fmt = (fmt or "svg").lower()
    if level not in LEVELS:
        return {"ok": False, "error": "level must be one of %s" % ", ".join(LEVELS)}
    if fmt not in FORMATS:
        return {"ok": False, "error": "format must be one of %s" % ", ".join(FORMATS)}
    if shutil.which(pj.tool_path("yosys")) is None and not os.path.exists(pj.tool_path("yosys")):
        return {"ok": False, "error": "yosys was not found. Install it (apt install yosys) "
                                      "or set YOSYS_BIN to its location."}

    top_name, err = _resolve_top(project, top)
    if err:
        return err

    out_dir = _schematic_dir(project)
    base = out_dir / ("%s_%s" % (top_name, level))
    # netlistsvg needs JSON; graphviz and .dot need the dot backend.
    want_json_first = fmt in ("svg", "json")
    backend = "json" if want_json_first else "dot"

    res = _run_yosys(project, _script(project, top_name, level, backend, base), out_dir)
    diags = parse_diagnostics((res["stdout"] or "") + "\n" + (res["stderr"] or ""))
    errors = _errors_only(diags)
    if res["rc"] != 0 or errors:
        return {
            "ok": False,
            "error": errors[0]["message"] if errors else
                     "yosys failed (rc=%s) while elaborating %s." % (res["rc"], top_name),
            "top": top_name, "level": level, "format": fmt,
            "command": res["command"], "errors": errors,
            "stderr": (res["stderr"] or "") + (res["stdout"] or ""),
        }

    result = {"ok": True, "top": top_name, "level": level, "format": fmt,
              "command": res["command"], "errors": [d for d in diags if d not in errors],
              "stderr": res["stderr"], "script": res["script_path"]}

    json_path = base.with_suffix(".json")
    if fmt == "json":
        if not json_path.exists():
            return {"ok": False, "error": "yosys produced no JSON netlist.",
                    "command": res["command"], "stderr": res["stderr"]}
        result["schematic"] = str(json_path)
        result["renderer"] = "yosys write_json"
        return result

    if fmt == "dot":
        dot_path = base.with_suffix(".dot")
        if not dot_path.exists():
            return {"ok": False, "error": "yosys produced no .dot file.",
                    "command": res["command"], "stderr": res["stderr"]}
        result["schematic"] = str(dot_path)
        result["renderer"] = "yosys show"
        return result

    out_path = base.with_suffix("." + fmt)
    fallback_note = None

    # Preferred path: netlistsvg, which draws real gate/box symbols.
    if fmt == "svg" and json_path.exists():
        r = _render_netlistsvg(json_path, out_path)
        if r["ok"]:
            result["schematic"] = str(out_path)
            result["renderer"] = "netlistsvg"
            result["netlist_json"] = str(json_path)
            return result
        fallback_note = "netlistsvg failed (%s); rendered with graphviz instead." % (
            (r["stderr"] or r["stdout"] or "rc=%s" % r["rc"]).strip().splitlines()[0]
            if (r["stderr"] or r["stdout"]) else "rc=%s" % r["rc"])

    # Fallback (and the only path for PNG): yosys `show` + graphviz.
    dres = _run_yosys(project, _script(project, top_name, level, "dot", base), out_dir)
    dot_path = base.with_suffix(".dot")
    if dres["rc"] != 0 or not dot_path.exists():
        return {"ok": False,
                "error": "Could not produce a schematic: yosys `show` failed.",
                "top": top_name, "command": dres["command"],
                "errors": _errors_only(parse_diagnostics(dres["stderr"] or dres["stdout"])),
                "stderr": dres["stderr"]}
    r = _render_dot(dot_path, out_path, fmt)
    if not r["ok"]:
        return {"ok": False,
                "error": "graphviz could not render the schematic. Is `dot` installed?",
                "top": top_name, "command": r["command"], "stderr": r["stderr"],
                "dot": str(dot_path)}
    result["schematic"] = str(out_path)
    result["renderer"] = "graphviz"
    result["dot"] = str(dot_path)
    if fallback_note:
        result["note"] = fallback_note
    return result


# --------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------

def _parse_stat(text: str) -> dict:
    """Parse the `stat` pass output into structured counts."""
    stats = {"wires": 0, "wire_bits": 0, "public_wires": 0, "public_wire_bits": 0,
             "memories": 0, "memory_bits": 0, "processes": 0, "cells": 0,
             "cell_types": {}}
    simple = {
        "Number of wires": "wires",
        "Number of wire bits": "wire_bits",
        "Number of public wires": "public_wires",
        "Number of public wire bits": "public_wire_bits",
        "Number of memories": "memories",
        "Number of memory bits": "memory_bits",
        "Number of processes": "processes",
        "Number of cells": "cells",
    }
    in_cells = False
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        m = re.match(r"^(Number of [a-z ]+):\s+(\d+)$", stripped)
        if m and m.group(1) in simple:
            stats[simple[m.group(1)]] = int(m.group(2))
            in_cells = m.group(1) == "Number of cells"
            continue
        if in_cells:
            c = re.match(r"^(\$?[\w.\\$]+)\s+(\d+)$", stripped)
            if c:
                stats["cell_types"][c.group(1).lstrip("\\")] = int(c.group(2))
            elif stripped and not stripped.startswith("Number of"):
                in_cells = False
    return stats


def get_netlist_stats(project, top: str = "", level: str = "rtl") -> dict:
    """Run yosys `stat` and return structured cell/wire/memory counts."""
    top_name, err = _resolve_top(project, top)
    if err:
        return err
    out_dir = _schematic_dir(project)
    lines = ["read_verilog -sv %s" % " ".join(_quote(f) for f in _read_files(project))]
    if level == "gate":
        lines.append("synth -top %s -flatten" % top_name)
    else:
        lines += ["hierarchy -top %s -check" % top_name, "proc", "opt_clean"]
    lines.append("stat -top %s" % top_name)
    res = _run_yosys(project, "\n".join(lines) + "\n", out_dir)
    diags = parse_diagnostics((res["stdout"] or "") + "\n" + (res["stderr"] or ""))
    errors = _errors_only(diags)
    if res["rc"] != 0 or errors:
        return {"ok": False,
                "error": errors[0]["message"] if errors else
                         "yosys `stat` failed (rc=%s)." % res["rc"],
                "top": top_name, "command": res["command"], "errors": errors,
                "stderr": (res["stderr"] or "") + (res["stdout"] or "")}
    return {"ok": True, "top": top_name, "level": level,
            "stats": _parse_stat(res["stdout"]),
            "command": res["command"], "raw": res["stdout"]}


# --------------------------------------------------------------------------
# viewer
# --------------------------------------------------------------------------

def open_schematic(path: str) -> dict:
    """Best-effort, detached launch of a viewer for a schematic file."""
    p = str(path)
    if not os.path.exists(p):
        return {"ok": False, "error": "No such schematic file: %s" % p}
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"ok": False, "path": p,
                "error": "No graphical display is available, so nothing can be opened here. "
                         "The schematic is saved at %s - open it from a desktop session or "
                         "a browser." % p}
    viewer = "xdot" if p.endswith(".dot") else "xdg-open"
    try:
        subprocess.Popen([viewer, p], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as exc:
        return {"ok": False, "path": p,
                "error": "Could not launch %s (%s). The schematic is saved at %s."
                         % (viewer, exc, p)}
    return {"ok": True, "path": p, "viewer": viewer,
            "note": "Launched %s in the background; it may take a moment to appear." % viewer}


# --------------------------------------------------------------------------
# MCP registration
# --------------------------------------------------------------------------

def register(mcp) -> None:
    """Attach the schematic tools to the iverilog-builder MCP server."""

    @mcp.tool()
    def generate_schematic(project_path: str, top: str = "", level: str = "rtl",
                           fmt: str = "svg") -> dict:
        """Draw a schematic of the design - the open-source equivalent of
        Vivado's elaborated-design view.

        top: module to draw; defaults to the project's top module.
        level: "rtl" (default) shows adders, muxes, and registers as
        recognisable blocks - this is what a beginner wants. "gate" runs a
        full synthesis first and shows the mapped gate-level netlist, which
        is far larger and only useful when the question is about gates.
        fmt: "svg" (default, best quality via netlistsvg), "png", "dot", or
        "json" for the raw yosys netlist.

        Returns the absolute path of the written file under `schematic`, plus
        which `renderer` drew it. Follow up with `open_schematic` to display
        it, or just tell the user the path.
        """
        try:
            proj = pj.load_project(project_path)
        except pj.ProjectError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            return _generate(proj, top, level, fmt)
        except Exception as exc:  # pragma: no cover - never raise out of a tool
            return {"ok": False, "error": "Schematic generation failed: %s" % exc}

    @mcp.tool()
    def get_netlist_stats(project_path: str, top: str = "", level: str = "rtl") -> dict:
        """Summarise the elaborated design as counts - how many cells of each
        kind, wires, memories, and processes yosys sees.

        Cheap text insight into the structure of a design with no viewer and
        no image involved; good for answering "how big is this?" or "did my
        adder actually infer an adder?". `level` works as in
        `generate_schematic`.
        """
        try:
            proj = pj.load_project(project_path)
        except pj.ProjectError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            return _stats(proj, top, level)
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": "Netlist stats failed: %s" % exc}

    @mcp.tool()
    def list_design_modules(project_path: str) -> dict:
        """List every module yosys finds in the project's design sources.

        Use this when the user asks for a schematic of "the design" and it
        isn't obvious which module is the top, or after a top-not-found
        error.
        """
        try:
            proj = pj.load_project(project_path)
        except pj.ProjectError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            return _list_modules(proj)
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": "Could not list modules: %s" % exc}

    @mcp.tool()
    def open_schematic(schematic_path: str) -> dict:
        """Open an already-generated schematic file in a desktop viewer.

        Non-blocking: the viewer is detached and this returns immediately. On
        a headless machine it returns ok=false with the file path so you can
        just tell the user where the schematic is.
        """
        try:
            return _open(schematic_path)
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": "Could not open the schematic: %s" % exc}


# Module-level aliases captured before `register` shadows the names inside its
# own scope, so the tool bodies always call the real implementations.
_generate = generate_schematic
_stats = get_netlist_stats
_list_modules = list_modules
_open = open_schematic
