"""Waveform generation for the Icarus flow: testbench -> VCD -> GTKWave.

The point of this module is that a beginner never has to write a testbench or
drag signals into a viewer. `generate_waveform` takes a module name, writes a
testbench for it if none exists, simulates it with `iverilog_runner`, reads the
VCD header to find out what was actually dumped, writes a GTKWave save file
with the interesting signals pre-added, and opens GTKWave already populated.

Everything is stdlib-only; the binaries are resolved through
`project.tool_path` so `GTKWAVE_BIN` and friends keep working.
"""

import os
import pathlib
import re
import subprocess

import iverilog_runner as ir
import project as pj

# --------------------------------------------------------------------------
# Verilog port extraction
# --------------------------------------------------------------------------

_CLOCK_RE = re.compile(r"^(i_)?(clk|clock|clk_i|clkin|sysclk)\w*$", re.I)
_RESET_RE = re.compile(r"^(i_)?(rst|reset|rstn|resetn|nrst|rst_n|reset_n)\w*$", re.I)

_COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub(" ", text)


def is_clock(name: str) -> bool:
    return bool(_CLOCK_RE.match(name or ""))


def is_reset(name: str) -> bool:
    return bool(_RESET_RE.match(name or ""))


def active_low_reset(name: str) -> bool:
    return bool(re.search(r"(_n|n)$", name or "", re.I)) and is_reset(name)


def _match_paren(text: str, start: int):
    """Index just past the ')' matching the '(' at `start`, or -1."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _eval_bound(expr: str, params: dict):
    """Evaluate a simple width bound: an integer, a parameter, or `X-1`."""
    e = (expr or "").strip()
    if not e:
        return None
    for name, val in params.items():
        e = re.sub(rf"\b{re.escape(name)}\b", str(val), e)
    if not re.fullmatch(r"[\d\s+\-*/()]+", e):
        return None
    try:
        return int(eval(e, {"__builtins__": {}}, {}))  # digits/operators only
    except Exception:
        return None


def _width_from_range(rng: str, params: dict) -> int:
    """`[3:0]` -> 4. Unknown/unparseable ranges fall back to 1 bit."""
    if not rng:
        return 1
    m = re.match(r"\s*\[\s*([^:]+):([^\]]+)\]", rng)
    if not m:
        return 1
    hi = _eval_bound(m.group(1), params)
    lo = _eval_bound(m.group(2), params)
    if hi is None or lo is None:
        return 1
    return abs(hi - lo) + 1


_DECL_RE = re.compile(
    r"\b(?P<dir>input|output|inout)\b\s*"
    r"(?:wire|reg|logic|signed|unsigned|\s)*"
    r"(?P<range>\[[^\]]*\])?\s*"
    r"(?P<names>[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)")


def parse_module_ports(path, module: str = "") -> dict:
    """Extract {"name", "ports": [{"name","dir","width"}], "params"} from a file.

    Handles both ANSI headers (`module m(input wire [3:0] a, output y);`) and
    the old style (`module m(a, y); input [3:0] a; output y;`).
    """
    p = pathlib.Path(path)
    text = _strip_comments(p.read_text(errors="ignore"))

    if module:
        m = re.search(rf"\bmodule\s+({re.escape(module)})\b", text)
    else:
        m = re.search(r"\bmodule\s+(\w+)", text)
    if not m:
        return {"name": module or p.stem, "ports": [], "params": {}}
    name = m.group(1)

    end = text.find("endmodule", m.end())
    body_all = text[m.end(): end if end != -1 else len(text)]

    params = {}
    for pm in re.finditer(r"\bparameter\b[^;=]*?(\w+)\s*=\s*([^,;)\n]+)", body_all):
        val = _eval_bound(pm.group(2), params)
        if val is not None:
            params[pm.group(1)] = val

    # header: the first '(' that is not the parameter list's
    idx = body_all.find("(")
    if body_all.lstrip().startswith("#"):
        hash_open = body_all.find("(", body_all.find("#"))
        close = _match_paren(body_all, hash_open)
        idx = body_all.find("(", close + 1)
    if idx == -1:
        return {"name": name, "ports": [], "params": params}
    close = _match_paren(body_all, idx)
    header = body_all[idx + 1: close if close != -1 else len(body_all)]
    body = body_all[(close + 1) if close != -1 else len(body_all):]

    ports = []
    seen = set()

    def add(pname, direction, width):
        if pname in seen:
            return
        seen.add(pname)
        ports.append({"name": pname, "dir": direction, "width": width})

    if re.search(r"\b(input|output|inout)\b", header):
        # ANSI header. Directions/ranges persist across comma-separated names.
        cur_dir, cur_rng = None, ""
        for chunk in header.split(","):
            c = chunk.strip()
            if not c:
                continue
            d = re.match(r"\s*(input|output|inout)\b", c)
            if d:
                cur_dir = d.group(1)
                c = c[d.end():]
                r = re.search(r"(\[[^\]]*\])", c)
                cur_rng = r.group(1) if r else ""
            nm = re.findall(r"([A-Za-z_]\w*)\s*(?:=[^,]*)?$", c.strip())
            if nm and cur_dir:
                add(nm[-1], cur_dir, _width_from_range(cur_rng, params))
    else:
        order = [n.strip() for n in header.split(",") if n.strip()]
        found = {}
        for d in _DECL_RE.finditer(body):
            w = _width_from_range(d.group("range"), params)
            for nm in d.group("names").split(","):
                found[nm.strip()] = (d.group("dir"), w)
        for nm in order:
            nm = re.sub(r"\W", "", nm)
            direction, w = found.get(nm, ("input", 1))
            add(nm, direction, w)

    return {"name": name, "ports": ports, "params": params}


# --------------------------------------------------------------------------
# testbench generation
# --------------------------------------------------------------------------

def _find_module_file(project: pj.Project, module: str):
    for entry in project.modules():
        if entry["name"] == module:
            return pathlib.Path(entry["file"])
    for f in project.sources:
        if f.stem == module:
            return f
    return None


def _existing_testbench(project: pj.Project, module: str):
    """A registered testbench that instantiates `module`, if there is one."""
    for tb in project.testbenches:
        try:
            text = _strip_comments(tb.read_text(errors="ignore"))
        except OSError:
            continue
        if re.search(rf"\b{re.escape(module)}\s+\w+\s*\(", text):
            return tb
    return None


def build_testbench_source(info: dict, tb_name: str, vcd_name: str,
                           cycles: int = 20) -> str:
    """Render a self-checking-free but fully dumping testbench for a module."""
    mod = info["name"]
    ports = info["ports"]
    inputs = [p for p in ports if p["dir"] == "input"]
    outputs = [p for p in ports if p["dir"] in ("output", "inout")]
    clocks = [p for p in inputs if is_clock(p["name"])]
    resets = [p for p in inputs if is_reset(p["name"]) and p not in clocks]
    stim = [p for p in inputs if p not in clocks and p not in resets]

    def decl(kind, p):
        rng = f" [{p['width'] - 1}:0]" if p["width"] > 1 else ""
        return f"    {kind}{rng} {p['name']};"

    L = ["`timescale 1ns / 1ps", "",
         f"// Auto-generated by verilog-builder-icarus for module `{mod}`.",
         "// Regenerate freely - edit it if you want different stimulus.",
         f"module {tb_name};", ""]
    L += [decl("reg", p) for p in inputs]
    L += [decl("wire", p) for p in outputs]
    L.append("")
    L.append(f"    {mod} dut (")
    conns = [f"        .{p['name']}({p['name']})" for p in ports]
    L.append(",\n".join(conns))
    L.append("    );")
    L.append("")

    if clocks:
        clk = clocks[0]["name"]
        L += [f"    initial {clk} = 1'b0;",
              f"    always #5 {clk} = ~{clk};   // 100 MHz", ""]

    L += ["    initial begin",
          f'        $dumpfile("{vcd_name}");',
          f"        $dumpvars(0, {tb_name});", ""]

    for p in resets:
        val = 0 if active_low_reset(p["name"]) else 1
        L.append(f"        {p['name']} = 1'b{val};")
    for p in stim:
        L.append(f"        {p['name']} = {p['width']}'d0;")
    L.append("")

    total_bits = sum(p["width"] for p in stim)
    if clocks:
        clk = clocks[0]["name"]
        if resets:
            r = resets[0]["name"]
            rel = 1 if active_low_reset(r) else 0
            L += [f"        repeat (4) @(posedge {clk});",
                  f"        {r} = 1'b{rel};",
                  f"        @(posedge {clk});", ""]
        if stim:
            L.append(f"        repeat ({cycles}) begin")
            L.append(f"            @(posedge {clk});")
            for p in stim:
                L.append(f"            {p['name']} <= $random;")
            L.append("        end")
        else:
            L.append(f"        repeat ({cycles}) @(posedge {clk});")
        L.append(f"        repeat (2) @(posedge {clk});")
    elif stim and total_bits <= 8:
        # Small combinational design: sweep every input combination.
        L.append(f"        for (idx = 0; idx < {1 << total_bits}; idx = idx + 1) begin")
        bit = 0
        for p in reversed(stim):
            hi = bit + p["width"] - 1
            L.append(f"            {p['name']} = idx[{hi}:{bit}];" if p["width"] > 1
                     else f"            {p['name']} = idx[{bit}];")
            bit += p["width"]
        L.append("            #10;")
        L.append("        end")
    elif stim:
        # Too wide to enumerate: sweep each input while the others sit at 0.
        for p in stim:
            L += [f"        {p['name']} = {p['width']}'d0; #10;",
                  f"        {p['name']} = {{{p['width']}{{1'b1}}}}; #10;",
                  f"        {p['name']} = $random; #10;",
                  f"        {p['name']} = {p['width']}'d0;"]
        L.append("        #20;")
    else:
        L.append("        #100;")

    L += ["", "        $finish;", "    end", "", "endmodule", ""]

    if not clocks and stim and total_bits <= 8:
        # `idx` must be declared before the initial block that uses it.
        head = L.index("    initial begin")
        L.insert(head, "    integer idx;")
        L.insert(head + 1, "")
    return "\n".join(L)


def ensure_testbench(project: pj.Project, module: str = "", cycles: int = 20,
                     force: bool = False) -> dict:
    """Return a testbench for `module`, generating one if none exists."""
    module = module or project.top or (project.modules()[0]["name"]
                                       if project.modules() else "")
    if not module:
        return {"ok": False, "error": "project has no design sources to simulate"}

    src = _find_module_file(project, module)
    if src is None:
        return {"ok": False, "error": f"module {module!r} not found in project sources",
                "available": [m["name"] for m in project.modules()]}

    if not force:
        existing = _existing_testbench(project, module)
        if existing is not None:
            return {"ok": True, "module": module, "testbench": str(existing),
                    "generated": False, "source": str(src)}

    try:
        info = parse_module_ports(src, module)
    except OSError as exc:
        return {"ok": False, "error": f"could not read {src}: {exc}"}
    if not info["ports"]:
        return {"ok": False, "error": f"could not parse any ports from {src}; "
                                      "write a testbench by hand with write_module"}

    tb_name = f"tb_{module}"
    content = build_testbench_source(info, tb_name, f"{module}.vcd", cycles=cycles)
    path = pj.write_module(project, f"{tb_name}.v", content, is_testbench=True)
    return {"ok": True, "module": module, "testbench": str(path), "generated": True,
            "source": str(src), "ports": info["ports"]}


# --------------------------------------------------------------------------
# VCD parsing
# --------------------------------------------------------------------------

def list_vcd_signals(vcd_path) -> dict:
    """Parse a VCD header into [{scope, name, width, identifier}]."""
    p = pathlib.Path(vcd_path).expanduser()
    if not p.exists():
        return {"ok": False, "error": f"VCD not found: {p}"}

    signals, scopes = [], []
    try:
        with open(p, errors="ignore") as fh:
            for line in fh:
                s = line.strip()
                if s.startswith("$scope"):
                    parts = s.split()
                    if len(parts) >= 3:
                        scopes.append(parts[2])
                elif s.startswith("$upscope"):
                    if scopes:
                        scopes.pop()
                elif s.startswith("$var"):
                    parts = s.split()
                    # $var wire 4 ! count [3:0] $end
                    if len(parts) >= 5:
                        width = int(parts[2]) if parts[2].isdigit() else 1
                        ident = parts[3]
                        name = parts[4]
                        bits = parts[5] if len(parts) > 6 and parts[5].startswith("[") else ""
                        signals.append({
                            "scope": ".".join(scopes),
                            "name": name,
                            "full_name": ".".join(scopes + [name]),
                            "width": width,
                            "identifier": ident,
                            "bit_range": bits,
                            "type": parts[1],
                        })
                elif s.startswith("$enddefinitions"):
                    break
    except OSError as exc:
        return {"ok": False, "error": f"could not read {p}: {exc}"}

    return {"ok": True, "vcd": str(p), "count": len(signals), "signals": signals}


# Loop counters and other testbench bookkeeping only clutter the viewer.
_HELPER_RE = re.compile(r"^(idx|i|j|k|n|count_i|errors|vectors?)$", re.I)


def _is_helper(sig: dict) -> bool:
    return (sig.get("type") in ("integer", "parameter", "real", "realtime", "time")
            or bool(_HELPER_RE.match(sig["name"])))


def _rank(sig: dict, top_scope: str) -> tuple:
    """Sort key: clock, reset, then top-level signals, then deeper scopes."""
    depth = sig["scope"].count(".")
    if is_clock(sig["name"]):
        group = 0
    elif is_reset(sig["name"]):
        group = 1
    elif sig["scope"] == top_scope:
        # In a generated testbench the DUT inputs are the regs the stimulus
        # drives and the outputs are wires, so this orders inputs before
        # outputs without needing the RTL.
        group = 2 if sig.get("type") == "reg" else 3
    else:
        group = 4
    return (group, depth, sig["full_name"])


def write_gtkw(vcd_path, gtkw_path=None, signals=None, max_signals: int = 40) -> dict:
    """Write a GTKWave save file with the interesting signals pre-added.

    Single-bit signals get GTKWave's default flags (`@28`); multi-bit buses are
    flagged `@22` so they render in hex. Opening `gtkwave <vcd> <gtkw>` then
    shows a populated window with no dragging.
    """
    if signals is None:
        listing = list_vcd_signals(vcd_path)
        if not listing["ok"]:
            return listing
        signals = listing["signals"]
    if not signals:
        return {"ok": False, "error": "VCD contains no signals to display"}

    vcd = pathlib.Path(vcd_path).expanduser().resolve()
    out = pathlib.Path(gtkw_path) if gtkw_path else vcd.with_suffix(".gtkw")

    top_scope = min((s["scope"] for s in signals), key=len, default="")
    top_names = {s["name"] for s in signals if s["scope"] == top_scope}
    interesting = [s for s in signals
                   if not (s["scope"] != top_scope and s["name"] in top_names)
                   and not _is_helper(s)]
    chosen = sorted(interesting or signals,
                    key=lambda s: _rank(s, top_scope))[:max_signals]

    lines = ["[*] GTKWave save file",
             "[*] written by verilog-builder-icarus",
             f'[dumpfile] "{vcd}"',
             "[timestart] 0",
             "[sst_width] 220",
             "[signals_width] 220",
             "[sst_expanded] 1",
             "[pane_width] 1000"]
    for scope in sorted({s["scope"] for s in chosen if s["scope"]}):
        lines.append(f"[treeopen] {scope}.")

    last_flags = None
    for s in chosen:
        flags = "@22" if s["width"] > 1 else "@28"
        if flags != last_flags:
            lines.append(flags)
            last_flags = flags
        label = s["full_name"]
        if s["width"] > 1:
            label += f"[{s['width'] - 1}:0]"
        lines.append(label)
    lines.append("[pattern_trace] 1")
    lines.append("[pattern_trace] 0")

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n")
    except OSError as exc:
        return {"ok": False, "error": f"could not write {out}: {exc}"}

    return {"ok": True, "gtkw": str(out), "vcd": str(vcd),
            "displayed": [s["full_name"] for s in chosen]}


# --------------------------------------------------------------------------
# launching the viewer
# --------------------------------------------------------------------------

def has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def open_waveform(vcd_path, gtkw_path=None) -> dict:
    """Spawn GTKWave detached so it outlives (and never blocks) this call."""
    vcd = pathlib.Path(vcd_path).expanduser()
    if not vcd.exists():
        return {"ok": False, "error": f"VCD not found: {vcd}"}

    argv = [pj.tool_path("gtkwave"), str(vcd)]
    if gtkw_path and pathlib.Path(gtkw_path).exists():
        argv.append(str(gtkw_path))

    if not has_display():
        return {"ok": False, "launched": False, "vcd": str(vcd),
                "gtkw": str(gtkw_path) if gtkw_path else None,
                "command": " ".join(argv),
                "error": "no graphical display is available (DISPLAY unset), so the "
                         "GTKWave window cannot open here. The VCD and its save file "
                         "are on disk - run the command above on a machine with a "
                         "display, or ask for the signal list in text instead."}
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)  # detached: no zombie, never blocks
    except OSError as exc:
        return {"ok": False, "launched": False, "command": " ".join(argv),
                "error": f"could not launch gtkwave: {exc}"}

    return {"ok": True, "launched": True, "pid": proc.pid,
            "command": " ".join(argv), "vcd": str(vcd),
            "gtkw": str(gtkw_path) if gtkw_path else None}


# --------------------------------------------------------------------------
# the headline flow
# --------------------------------------------------------------------------

def generate_waveform(project: pj.Project, module: str = "", testbench: str = "",
                      open_viewer: bool = True, run_seconds: int = 60,
                      cycles: int = 20) -> dict:
    """Testbench (written if needed) -> simulate -> .gtkw -> GTKWave window."""
    if testbench:
        tb_info = {"ok": True, "testbench": testbench, "generated": False,
                   "module": module or project.top}
    else:
        tb_info = ensure_testbench(project, module, cycles=cycles)
        if not tb_info["ok"]:
            return tb_info

    sim = ir.run_simulation(project, tb_info["testbench"], run_seconds=run_seconds)
    if not sim.get("ok"):
        return {"ok": False, "phase": sim.get("phase", "simulate"),
                "error": sim.get("error", "simulation failed"),
                "errors": sim.get("errors", []),
                "testbench": tb_info["testbench"],
                "testbench_generated": tb_info.get("generated", False),
                "sim_stdout": sim.get("stdout", ""), "stderr": sim.get("stderr", ""),
                "command": sim.get("command", "")}

    vcd = sim.get("vcd")
    if not vcd:
        return {"ok": False, "error": "the simulation ran but produced no VCD - the "
                                      "testbench never called $dumpfile/$dumpvars",
                "testbench": tb_info["testbench"], "sim_stdout": sim.get("stdout", "")}

    listing = list_vcd_signals(vcd)
    save = write_gtkw(vcd, signals=listing.get("signals")) if listing["ok"] else listing

    result = {
        "ok": True,
        "module": tb_info.get("module") or sim.get("top"),
        "testbench": tb_info["testbench"],
        "testbench_generated": tb_info.get("generated", False),
        "vcd": vcd,
        "gtkw": save.get("gtkw"),
        "signals": listing.get("signals", []),
        "displayed": save.get("displayed", []),
        "sim_stdout": sim.get("stdout", ""),
        "sim_command": sim.get("command", ""),
    }
    if not save.get("ok"):
        result["gtkw_error"] = save.get("error")

    if open_viewer:
        view = open_waveform(vcd, save.get("gtkw"))
        result["viewer"] = view
        result["viewer_launched"] = view.get("launched", False)
        if not view.get("ok"):
            result["viewer_error"] = view.get("error")
    else:
        result["viewer_launched"] = False
    return result


# --------------------------------------------------------------------------
# MCP registration
# --------------------------------------------------------------------------

def register(mcp) -> None:
    @mcp.tool()
    def generate_waveform(project_path: str, module: str = "", testbench: str = "",
                          open_viewer: bool = True, run_seconds: int = 60,
                          cycles: int = 20) -> dict:
        """Show the waveform for a module - the one call that does everything.

        Writes a testbench for `module` if the project has none for it (clock
        generated, reset pulsed, inputs swept), runs the simulation, then opens
        GTKWave with the signals already added, so the user does no setup.

        module: which design module to look at; defaults to the project top.
        testbench: use this existing testbench instead of generating one.
        open_viewer: set false for a headless run - the VCD and `.gtkw` are
        still written and `signals` still comes back so you can describe the
        waveform in text.
        cycles: how many clock cycles a generated sequential testbench runs.

        Returns `vcd`, `gtkw`, `testbench`, `signals` and the simulator's
        stdout. If the viewer could not open, everything else is still valid.
        """
        try:
            project = pj.load_project(project_path)
        except pj.ProjectError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            return generate_waveform_impl(project, module, testbench,
                                          open_viewer, run_seconds, cycles)
        except Exception as exc:  # never raise out of a tool
            return {"ok": False, "error": f"waveform generation failed: {exc}"}

    @mcp.tool()
    def ensure_testbench(project_path: str, module: str = "", cycles: int = 20,
                         force: bool = False) -> dict:
        """Make sure a testbench exists for a module, writing one if it doesn't.

        Parses the module's ports and generates a testbench that instantiates
        it by name, drives any clock, pulses any reset, applies stimulus
        (exhaustive for small combinational designs, a clocked run otherwise)
        and always dumps a VCD.

        force: regenerate even if a matching testbench already exists.
        Returns the testbench path and whether it was newly `generated`.
        """
        try:
            project = pj.load_project(project_path)
        except pj.ProjectError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            return ensure_testbench_impl(project, module, cycles, force)
        except Exception as exc:
            return {"ok": False, "error": f"could not build a testbench: {exc}"}

    @mcp.tool()
    def list_vcd_signals(vcd_path: str) -> dict:
        """List every signal recorded in a VCD file: scope, name and bit width.

        Use this to describe a waveform in words when no display is available,
        or to check what the simulation actually captured.
        """
        try:
            return list_vcd_signals_impl(vcd_path)
        except Exception as exc:
            return {"ok": False, "error": f"could not parse VCD: {exc}"}

    @mcp.tool()
    def open_waveform(vcd_path: str, gtkw_path: str = "") -> dict:
        """Open an existing VCD in GTKWave, pre-populated from a `.gtkw` file.

        The viewer is launched detached, so this returns immediately. With no
        display available it returns the paths and the command to run instead
        of failing silently.
        """
        try:
            return open_waveform_impl(vcd_path, gtkw_path or None)
        except Exception as exc:
            return {"ok": False, "error": f"could not open the waveform: {exc}"}


# Module-level aliases so `register`'s tool functions can shadow the names
# without losing access to the implementations.
generate_waveform_impl = generate_waveform
ensure_testbench_impl = ensure_testbench
list_vcd_signals_impl = list_vcd_signals
open_waveform_impl = open_waveform
