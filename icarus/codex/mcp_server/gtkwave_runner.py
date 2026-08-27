"""Waveform generation for the iverilog-builder plugin.

The point of this module is that a beginner never has to write a testbench,
never has to remember `$dumpvars`, and never has to click signals into a
waveform viewer. They say "show me the waveform for my counter" and a
populated GTKWave window opens.

To get there we:

1. `ensure_testbench` - if the project has no testbench for the target
   module, parse that module's port list straight out of its Verilog source
   and *write* one: clock generation, reset pulse, stimulus sized to the
   design, and always a `$dumpfile`/`$dumpvars`/`$finish`.
2. `generate_waveform` - run that testbench through `iverilog_runner`'s
   existing compile+simulate path, find the VCD it produced, build a GTKWave
   save file (`.gtkw`) that pre-adds the interesting signals in a sensible
   order, and launch `gtkwave <vcd> <gtkw>` detached.

Stdlib only, like `project.py`. Nothing expensive happens at import time -
gtkwave is probed inside the tool call, so the server still starts on a
machine that has no viewer installed.
"""

import os
import pathlib
import re
import subprocess

import project as pj
import iverilog_runner as ir

# --------------------------------------------------------------------------
# Verilog port parsing
# --------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_CLOCK_NAMES = ("clk", "clock", "i_clk", "clk_i", "sysclk", "clk_in")
_RESET_NAMES = ("rst", "reset", "rst_n", "resetn", "reset_n", "i_rst", "rst_i",
                "nreset", "arst", "rstn")


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub(" ", text)


def _is_clock(name: str) -> bool:
    low = name.lower()
    return low in _CLOCK_NAMES or low.startswith("clk") or low.startswith("clock")


def _is_reset(name: str) -> bool:
    low = name.lower()
    return low in _RESET_NAMES or "reset" in low or re.match(r"^i?_?rst", low) is not None


def _active_low(name: str) -> bool:
    low = name.lower()
    return low.endswith("_n") or low.endswith("n") and low.startswith("rst") or low.startswith("n")


def _width_of(msb: str, lsb: str) -> int:
    """Width from a `[msb:lsb]` range, best-effort for constant expressions."""
    try:
        return abs(int(_eval_const(msb)) - int(_eval_const(lsb))) + 1
    except Exception:  # noqa: BLE001 - parameterised widths, fall back to 1
        return 1


def _eval_const(expr: str):
    expr = expr.strip()
    if re.fullmatch(r"[-+*/() \t0-9]+", expr):
        return eval(expr, {"__builtins__": {}}, {})  # noqa: S307 - digits/ops only
    raise ValueError(expr)


_MODULE_RE_TMPL = r"\bmodule\s+{name}\b\s*(#\s*\((?P<params>.*?)\))?\s*\((?P<ports>.*?)\)\s*;(?P<body>.*?)\bendmodule\b"
_ANY_MODULE_RE = re.compile(
    r"\bmodule\s+(?P<name>\w+)\b\s*(#\s*\(.*?\))?\s*\((?P<ports>.*?)\)\s*;(?P<body>.*?)\bendmodule\b",
    re.S)
_DIR_RE = re.compile(r"\b(?P<dir>input|output|inout)\b")
_RANGE_RE = re.compile(r"\[\s*(?P<msb>[^\]:]+?)\s*:\s*(?P<lsb>[^\]]+?)\s*\]")
_TYPE_WORDS = {"wire", "reg", "logic", "bit", "signed", "unsigned", "var", "integer"}


def _parse_decls(text: str):
    """Yield (direction, width, [names]) for every port declaration in `text`.

    A declaration runs from its `input`/`output`/`inout` keyword up to the
    next such keyword or the next `;`, whichever comes first - that is what
    keeps `input a, input b` from being read as one four-name declaration.
    """
    marks = list(_DIR_RE.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        semi = text.find(";", m.end())
        if semi != -1 and semi < end:
            end = semi
        chunk = text[m.end():end]
        rng = _RANGE_RE.search(chunk)
        width = _width_of(rng.group("msb"), rng.group("lsb")) if rng else 1
        chunk = _RANGE_RE.sub(" ", chunk)
        names = []
        for tok in chunk.split(","):
            tok = tok.split("=")[0]
            words = [w for w in re.findall(r"\w+", tok) if w not in _TYPE_WORDS]
            if words:
                names.append(words[-1])
        yield m.group("dir"), width, names


def parse_module_ports(source: str, module: str = "") -> dict:
    """Extract `{name, ports:[{name,dir,width}]}` from Verilog source text.

    Handles both ANSI headers (`module m(input wire [3:0] a, output b);`) and
    the old style where the header lists bare names and the directions are
    declared in the body. Unknown/parameterised widths degrade to 1 rather
    than failing the whole parse.
    """
    text = _strip_comments(source)
    match = None
    if module:
        match = re.search(_MODULE_RE_TMPL.format(name=re.escape(module)), text, re.S)
    if match is None:
        match = _ANY_MODULE_RE.search(text)
        if match is None:
            raise ValueError("no module declaration found in source")
        module = match.group("name")

    header = match.group("ports") or ""
    body = match.group("body") or ""

    ports = []
    seen = {}

    def _add(name, direction, width):
        name = name.strip()
        if not name or name in ("wire", "reg", "logic", "signed", "unsigned"):
            return
        if name in seen:
            entry = seen[name]
            if direction:
                entry["dir"] = direction
            if width > entry["width"]:
                entry["width"] = width
            return
        entry = {"name": name, "dir": direction or "input", "width": width or 1}
        seen[name] = entry
        ports.append(entry)

    # ANSI-style: directions live in the header itself.
    header_flat = re.sub(r"\s+", " ", header)
    if _DIR_RE.search(header_flat):
        for direction, width, names in _parse_decls(header_flat):
            for nm in names:
                _add(nm, direction, width)
    else:
        # Old style: header is just an ordered name list; keep that order.
        order = [n.strip() for n in header_flat.split(",") if n.strip()]
        for nm in order:
            _add(nm, None, 1)
        for direction, width, names in _parse_decls(re.sub(r"\s+", " ", body)):
            for nm in names:
                if nm in seen:
                    seen[nm]["dir"] = direction
                    seen[nm]["width"] = width
                else:
                    _add(nm, direction, width)

    return {"name": module, "ports": ports}


def _find_module_file(p: pj.Project, module: str):
    """The source file declaring `module`, or None."""
    for f in list(p.sources) + list(p.testbenches):
        try:
            if re.search(r"\bmodule\s+%s\b" % re.escape(module),
                         _strip_comments(f.read_text(errors="ignore"))):
                return f
        except OSError:
            continue
    return None


def _existing_testbench_for(p: pj.Project, module: str):
    """A registered testbench that instantiates `module`, or None."""
    for tb in p.testbenches:
        try:
            text = _strip_comments(tb.read_text(errors="ignore"))
        except OSError:
            continue
        if re.search(r"\b%s\s+\w+\s*\(" % re.escape(module), text):
            return tb
    return None


# --------------------------------------------------------------------------
# Testbench generation
# --------------------------------------------------------------------------

def _bus(width: int) -> str:
    return "" if width <= 1 else "[%d:0] " % (width - 1)


def build_testbench_source(info: dict, tb_name: str, vcd_name: str,
                           cycles: int = 32) -> str:
    """Render a self-checking-ish stimulus testbench for a parsed module.

    Combinational designs with a small total input width get an exhaustive
    sweep; everything else gets a clocked run with a reset pulse and
    pseudo-random-but-deterministic input stepping.
    """
    module = info["name"]
    ports = info["ports"]
    inputs = [q for q in ports if q["dir"] == "input"]
    outputs = [q for q in ports if q["dir"] in ("output", "inout")]

    clk = next((q for q in inputs if _is_clock(q["name"])), None)
    rst = next((q for q in inputs if q is not clk and _is_reset(q["name"])), None)
    data_in = [q for q in inputs if q is not clk and q is not rst]
    total_w = sum(q["width"] for q in data_in)

    L = []
    L.append("// Auto-generated by iverilog-builder (gtkwave_runner).")
    L.append("// Stimulus for module `%s` - edit freely, it is a normal testbench." % module)
    L.append("`timescale 1ns / 1ps")
    L.append("")
    L.append("module %s;" % tb_name)
    L.append("")
    for q in inputs:
        L.append("    reg  %s%s;" % (_bus(q["width"]), q["name"]))
    for q in outputs:
        L.append("    wire %s%s;" % (_bus(q["width"]), q["name"]))
    L.append("")
    L.append("    %s dut (" % module)
    L.append(",\n".join("        .%s(%s)" % (q["name"], q["name"]) for q in ports))
    L.append("    );")
    L.append("")

    if clk:
        L.append("    // 100 MHz clock")
        L.append("    initial %s = 1'b0;" % clk["name"])
        L.append("    always #5 %s = ~%s;" % (clk["name"], clk["name"]))
        L.append("")

    L.append("    initial begin")
    L.append('        $dumpfile("%s");' % vcd_name)
    L.append("        $dumpvars(0, %s);" % tb_name)
    L.append("")

    if clk:
        for q in data_in:
            L.append("        %s = %d'd0;" % (q["name"], q["width"]))
        if rst:
            asserted, released = ("1'b0", "1'b1") if _active_low(rst["name"]) else ("1'b1", "1'b0")
            L.append("        %s = %s;   // hold reset" % (rst["name"], asserted))
            L.append("        repeat (4) @(posedge %s);" % clk["name"])
            L.append("        %s = %s;   // release reset" % (rst["name"], released))
        L.append("")
        if data_in:
            L.append("        repeat (%d) begin" % cycles)
            L.append("            @(posedge %s);" % clk["name"])
            for q in data_in:
                if q["width"] == 1:
                    L.append("            %s <= ~%s;" % (q["name"], q["name"]))
                else:
                    L.append("            %s <= %s + 1'b1;" % (q["name"], q["name"]))
            L.append("        end")
        else:
            L.append("        repeat (%d) @(posedge %s);" % (cycles, clk["name"]))
        L.append("        repeat (2) @(posedge %s);" % clk["name"])
    elif data_in and total_w <= 8:
        L.append("        // exhaustive sweep of all %d input combinations" % (1 << total_w))
        L.append("        begin : sweep")
        L.append("            integer i;")
        L.append("            for (i = 0; i < %d; i = i + 1) begin" % (1 << total_w))
        bit = 0
        for q in reversed(data_in):
            if q["width"] == 1:
                L.append("                %s = i[%d];" % (q["name"], bit))
            else:
                L.append("                %s = i[%d:%d];" % (q["name"], bit + q["width"] - 1, bit))
            bit += q["width"]
        L.append("                #10;")
        L.append("            end")
        L.append("        end")
    elif data_in:
        L.append("        // input space too large to enumerate - sweep each input in turn")
        for q in data_in:
            L.append("        %s = %d'd0;" % (q["name"], q["width"]))
        L.append("        #10;")
        for q in data_in:
            L.append("        %s = {%d{1'b1}}; #10;" % (q["name"], q["width"]))
            L.append("        %s = %d'd0;     #10;" % (q["name"], q["width"]))
        L.append("        #20;")
    else:
        L.append("        #100;")

    L.append("")
    L.append("        $finish;")
    L.append("    end")
    L.append("")
    L.append("endmodule")
    L.append("")
    return "\n".join(L)


def ensure_testbench(project_path: str, module: str = None, force: bool = False,
                     cycles: int = 32) -> dict:
    """Return a testbench for `module`, generating one if none exists."""
    p = pj.load_project(project_path)
    module = module or p.top or (pj.module_name_for_file(p.sources[-1]) if p.sources else "")
    if not module:
        return {"ok": False, "error": "project has no sources and no top module set"}

    if not force:
        existing = _existing_testbench_for(p, module)
        if existing is not None:
            return {"ok": True, "testbench": str(existing), "module": module,
                    "generated": False,
                    "note": "using the project's existing testbench for %s" % module}

    src = _find_module_file(p, module)
    if src is None:
        return {"ok": False,
                "error": "no source file in the project declares module '%s'" % module,
                "sources": [str(s) for s in p.sources]}

    try:
        info = parse_module_ports(src.read_text(errors="ignore"), module)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": "could not parse ports of %s: %s" % (module, exc)}
    if not info["ports"]:
        return {"ok": False, "error": "module %s declares no ports; nothing to drive" % module}

    tb_dir = p.root / "tb"
    tb_dir.mkdir(parents=True, exist_ok=True)
    tb_name = "tb_%s" % module
    tb_file = tb_dir / ("%s%s" % (tb_name, src.suffix if src.suffix in (".v", ".sv") else ".v"))
    tb_file.write_text(build_testbench_source(info, tb_name, "%s.vcd" % module, cycles))

    pj.add_sources(p, [tb_file])

    return {"ok": True, "testbench": str(tb_file), "module": module, "tb_top": tb_name,
            "generated": True, "ports": info["ports"],
            "note": "generated a testbench at %s and registered it with the project" % tb_file}


# --------------------------------------------------------------------------
# VCD parsing
# --------------------------------------------------------------------------

def list_vcd_signals(vcd_path: str) -> dict:
    """Parse a VCD header into [{scope, name, width, msb, lsb, id}]."""
    path = pathlib.Path(vcd_path).expanduser()
    if not path.exists():
        return {"ok": False, "error": "VCD file not found: %s" % path}

    signals = []
    scope = []
    try:
        with open(path, errors="ignore") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("$scope"):
                    parts = line.split()
                    if len(parts) >= 3:
                        scope.append(parts[2])
                elif line.startswith("$upscope"):
                    if scope:
                        scope.pop()
                elif line.startswith("$var"):
                    parts = line.split()
                    # $var wire 4 ! count [3:0] $end
                    if len(parts) < 5:
                        continue
                    width = int(parts[2]) if parts[2].isdigit() else 1
                    ident = parts[3]
                    name = parts[4]
                    msb, lsb = (width - 1, 0)
                    rng = parts[5] if len(parts) > 5 and parts[5].startswith("[") else ""
                    m = re.match(r"\[(\d+)(?::(\d+))?\]", rng)
                    if m:
                        msb = int(m.group(1))
                        lsb = int(m.group(2)) if m.group(2) is not None else msb
                    signals.append({"scope": ".".join(scope), "name": name,
                                    "full_name": ".".join(scope + [name]),
                                    "width": width, "msb": max(msb, lsb),
                                    "lsb": min(msb, lsb), "id": ident,
                                    "type": parts[1]})
                elif line.startswith("$enddefinitions"):
                    break
    except OSError as exc:
        return {"ok": False, "error": "could not read VCD: %s" % exc}

    return {"ok": True, "vcd": str(path), "count": len(signals), "signals": signals}


def _signal_rank(sig: dict, dut_scope: str) -> tuple:
    """Sort key: clock, reset, then top-scope signals, then depth/name."""
    name = sig["name"]
    depth = sig["scope"].count(".")
    if _is_clock(name):
        cls = 0
    elif _is_reset(name):
        cls = 1
    elif depth == 0:
        cls = 2
    else:
        cls = 3
    return (cls, depth, name.lower())


_NOISE_TYPES = {"integer", "real", "realtime", "parameter", "time"}


def select_gtkw_signals(signals):
    """Trim a VCD's signal list down to what is worth pre-adding to a window.

    Drops simulator bookkeeping (loop counters and the like) and the deeper
    copies of a signal that the testbench already exposes at its top level,
    so the viewer opens with one trace per interesting wire.
    """
    top_names = {s["name"] for s in signals if not s["scope"].count(".")}
    picked = []
    for sig in signals:
        if sig.get("type") in _NOISE_TYPES:
            continue
        depth = sig["scope"].count(".")
        if depth and sig["name"] in top_names:
            continue
        picked.append(sig)
    return picked or list(signals)


def write_gtkw(vcd_path, signals, gtkw_path, max_signals: int = 40) -> pathlib.Path:
    """Write a GTKWave save file that pre-adds `signals`.

    Format is GTKWave's own: a `[dumpfile]` header followed by trace lines,
    each preceded by an `@<flags>` line. 0x22 selects hex data format for
    buses, 0x28 the plain binary/logic display used for single bits.
    """
    gtkw_path = pathlib.Path(gtkw_path)
    lines = ["[*]", "[*] GTKWave save file generated by iverilog-builder", "[*]",
             '[dumpfile] "%s"' % pathlib.Path(vcd_path).resolve(),
             "[timestart] 0",
             "[sst_width] 250", "[signals_width] 220", "[sst_expanded] 1",
             "[pattern_trace] 1", "[pattern_trace] 0"]
    for sig in signals[:max_signals]:
        flags = "@22" if sig["width"] > 1 else "@28"
        name = sig["full_name"]
        if sig["width"] > 1:
            name = "%s[%d:%d]" % (name, sig["msb"], sig["lsb"])
        lines.append(flags)
        lines.append(name)
    gtkw_path.write_text("\n".join(lines) + "\n")
    return gtkw_path


# --------------------------------------------------------------------------
# Viewer
# --------------------------------------------------------------------------

def open_waveform(vcd_path: str, gtkw_path: str = None) -> dict:
    """Spawn GTKWave detached so it never blocks or zombifies the server."""
    vcd = pathlib.Path(vcd_path).expanduser()
    if not vcd.exists():
        return {"ok": False, "error": "VCD file not found: %s" % vcd, "vcd": str(vcd)}

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"ok": False, "launched": False, "vcd": str(vcd),
                "gtkw": str(gtkw_path) if gtkw_path else None,
                "error": "no graphical display available (DISPLAY unset), so the viewer "
                         "was not launched. The waveform is saved - open it later with: "
                         "gtkwave %s%s" % (vcd, (" " + str(gtkw_path)) if gtkw_path else "")}

    binary = pj.tool_path("gtkwave")
    # Without this GTKWave opens at its default zoom, showing the first couple
    # of picoseconds of the dump - the traces are loaded but the window looks
    # blank. Zoom-fit makes the whole simulation visible on open.
    argv = [binary, "--rcvar", "do_initial_zoom_fit on", str(vcd)]
    argv += [str(gtkw_path)] if gtkw_path else []
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        return {"ok": False, "launched": False, "vcd": str(vcd),
                "error": "could not launch gtkwave (%s): %s" % (binary, exc)}
    return {"ok": True, "launched": True, "pid": proc.pid, "vcd": str(vcd),
            "gtkw": str(gtkw_path) if gtkw_path else None,
            "command": " ".join(argv)}


# --------------------------------------------------------------------------
# The headline one-call tool
# --------------------------------------------------------------------------

def generate_waveform(project_path: str, module: str = None, testbench: str = None,
                      open_viewer: bool = True, cycles: int = 32,
                      timeout: int = 120) -> dict:
    """Testbench -> simulate -> VCD -> save file -> viewer, in one call."""
    p = pj.load_project(project_path)
    module = module or p.top or (pj.module_name_for_file(p.sources[-1]) if p.sources else "")

    generated = False
    if testbench:
        tb = testbench
    else:
        ens = ensure_testbench(project_path, module, cycles=cycles)
        if not ens.get("ok"):
            return ens
        tb = ens["testbench"]
        generated = ens.get("generated", False)

    sim = ir.run_simulation(project_path, tb, timeout)
    if not sim.get("ok"):
        return {"ok": False, "error": sim.get("error", "simulation failed"),
                "testbench": tb, "generated_testbench": generated,
                "diagnostics": sim.get("diagnostics", ir.parse_diagnostics(sim.get("stderr", ""))),
                "sim_stdout": sim.get("stdout", ""), "stderr": sim.get("stderr", "")}

    vcd = sim.get("vcd")
    if not vcd:
        return {"ok": False, "testbench": tb, "generated_testbench": generated,
                "sim_stdout": sim.get("stdout", ""),
                "error": "the simulation ran but wrote no VCD - the testbench needs "
                         '$dumpfile("name.vcd"); $dumpvars(0, <tb_module>);'}

    listing = list_vcd_signals(vcd)
    if not listing.get("ok"):
        return {"ok": False, "testbench": tb, "vcd": vcd, "error": listing["error"]}

    signals = sorted(listing["signals"], key=lambda s: _signal_rank(s, module))
    gtkw = write_gtkw(vcd, select_gtkw_signals(signals), p.build_path() / ("%s.gtkw" % (module or "waveform")))

    result = {"ok": True, "module": module, "testbench": tb,
              "generated_testbench": generated, "vcd": vcd, "gtkw": str(gtkw),
              "signals": signals, "signal_count": len(signals),
              "sim_stdout": sim.get("stdout", ""), "log_file": sim.get("log_file")}

    if open_viewer:
        result["viewer"] = open_waveform(vcd, str(gtkw))
    else:
        result["viewer"] = {"ok": True, "launched": False,
                            "note": "open_viewer=false; run `gtkwave %s %s` to view it"
                                    % (vcd, gtkw)}
    return result


# --------------------------------------------------------------------------
# MCP registration
# --------------------------------------------------------------------------

def _fail(exc: Exception) -> dict:
    return {"ok": False, "error": str(exc)}


def register(mcp):
    """Attach the waveform tools to the server's FastMCP instance."""

    @mcp.tool()
    def generate_waveform_for_module(project_path: str, module: str = "",
                                     testbench: str = "", open_viewer: bool = True,
                                     cycles: int = 32) -> dict:
        """Simulate a module and open its waveform - the one-call waveform tool.

        Writes a testbench for you if the project doesn't already have one for
        this module (clock, reset pulse, and stimulus chosen to suit a
        combinational or sequential design), runs it under vvp, and opens
        GTKWave with the interesting signals already added to the window.

        module: which module to look at; defaults to the project's top.
        testbench: use this testbench instead of generating one.
        open_viewer: set false on a headless machine to just produce the VCD.
        """
        try:
            return generate_waveform(project_path, module or None, testbench or None,
                                     open_viewer, cycles)
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @mcp.tool()
    def ensure_waveform_testbench(project_path: str, module: str = "",
                                  force: bool = False, cycles: int = 32) -> dict:
        """Make sure a module has a testbench, writing one if it doesn't.

        Parses the module's ports out of its Verilog source and generates a
        testbench that instantiates it by name, drives any clock and reset,
        applies stimulus, and dumps a VCD. The file is written under
        `<project>/tb/` and registered with the project, so you can read and
        edit it like any other testbench. Returns whether it was generated or
        already existed.
        """
        try:
            return ensure_testbench(project_path, module or None, force, cycles)
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @mcp.tool()
    def list_waveform_signals(vcd_path: str) -> dict:
        """List every signal in a VCD file: scope, name and bit width.

        Useful for describing a waveform in words when there's no display, or
        for deciding which signals matter before opening the viewer.
        """
        try:
            return list_vcd_signals(vcd_path)
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @mcp.tool()
    def open_waveform_viewer(vcd_path: str, gtkw_path: str = "") -> dict:
        """Open an existing VCD in GTKWave without re-running the simulation.

        Launches detached, so it returns immediately and the viewer keeps
        running. If there's no graphical display it says so and still hands
        back the VCD path.
        """
        try:
            return open_waveform(vcd_path, gtkw_path or None)
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)
