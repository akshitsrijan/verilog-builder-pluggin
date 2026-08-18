"""MCP server for iverilog-builder: exposes Icarus Verilog project creation,
module-by-module building, prompt-driven fixes, and simulation as tools.

Every tool returns a dict with an "ok" boolean; failures carry "error".
Optional companion modules (yosys_runner for schematics, gtkwave_runner for
waveforms) register their own tools at the bottom of this file - see
CONTRACT.md.
"""

import pathlib
import sys
import time

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # mcp >= 2.0 renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import iverilog_runner as ir  # noqa: E402
import project as pj  # noqa: E402

mcp = FastMCP("iverilog-builder")


def _fail(exc) -> dict:
    return {"ok": False, "error": str(exc)}


@mcp.tool()
def list_projects(search_root: str = "~") -> dict:
    """List Icarus Verilog projects (directories holding a .ivproj.json
    manifest) found at, or up to two levels under, search_root."""
    try:
        return {"ok": True, "projects": pj.list_projects(search_root)}
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def create_project(project_name: str, project_dir: str = "", source_files: list[str] = None,
                   top: str = "") -> dict:
    """Create a brand-new Icarus Verilog project - no build files to hand-write.

    project_dir: defaults to ~/<project_name>/. source_files: optional list of
    existing .v/.sv paths to adopt; leave empty when the user is going to
    describe their modules in English instead (then call write_module for
    each one). top: optional top module name, inferred from the sources
    otherwise.

    Returns the project path, which every other tool here accepts.
    """
    pdir = project_dir or f"~/{project_name}"
    try:
        p = pj.create_project(project_name, pdir, source_files or [], top)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)
    return {"ok": True, "status": "created", **p.summary()}


@mcp.tool()
def write_module(project_path: str, module_name: str, verilog_code: str,
                 is_testbench: bool = False, subdir: str = "") -> dict:
    """Write a Verilog module into a project and register it in the manifest.

    This is the main way modules get created: the user describes what they
    want in plain English, you write the Verilog, and this persists it and
    wires it into the project in one step - the user never creates a file or
    edits a build script by hand.

    module_name: the module's name; the file is written as <module_name>.v.
    verilog_code: the complete file contents. is_testbench: true registers it
    under testbenches (also auto-detected from a tb_/_tb name) so it is used
    by run_simulation rather than treated as design RTL. subdir: optional
    folder under the project root, defaults to 'sources' for design modules
    and 'tb' for testbenches.

    Overwrites an existing file of the same name after backing it up to
    <file>.bak, so calling this again is the way to revise a module.
    """
    try:
        p = pj.load_project(project_path)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)

    tb = is_testbench or pj.looks_like_testbench(module_name + ".v")
    folder = p.root / (subdir or ("tb" if tb else "sources"))
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{module_name}.v"

    backup = None
    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        backup.write_text(target.read_text(errors="ignore"))
    target.write_text(verilog_code if verilog_code.endswith("\n") else verilog_code + "\n")

    try:
        if tb and target not in p.testbenches:
            p.testbenches.append(target)
        elif not tb and target not in p.sources:
            p.sources.append(target)
        if not tb and not p.top:
            p.top = pj.module_name_for_file(target)
        pj.save_project(p)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)

    return {"ok": True, "file": str(target), "module": pj.module_name_for_file(target),
            "is_testbench": tb, "backup": str(backup) if backup else None,
            "project": p.summary()}


@mcp.tool()
def add_sources(project_path: str, files: list[str]) -> dict:
    """Register existing .v/.sv files with a project. Files whose names look
    like testbenches (tb_*, *_tb, *testbench*) go to the testbench list."""
    try:
        p = pj.load_project(project_path)
        pj.add_sources(p, files)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)
    return {"ok": True, **p.summary()}


@mcp.tool()
def compile_design(project_path: str, top: str = "") -> dict:
    """Elaborate the whole design with iverilog into a runnable .vvp.

    Returns the output path plus parsed diagnostics
    ({file, line, severity, message}) whether it succeeded or not."""
    try:
        p = pj.load_project(project_path)
        return ir.compile_design(p, top or None)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def lint_design(project_path: str, file_path: str = "") -> dict:
    """Syntax/elaboration check via `iverilog -t null` without producing any
    output binary. Pass file_path to check just one file, otherwise the whole
    design is checked plus each source individually."""
    try:
        p = pj.load_project(project_path)
        if file_path:
            return ir.lint_file(p, file_path, extra_files=p.sources)
        return ir.lint_design(p)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def start_build(project_path: str, top: str = "") -> dict:
    """Start a background module-by-module build: each source file is checked
    on its own so errors are attributable to one module, then the full design
    is elaborated into a .vvp.

    Returns immediately with a build_id; poll get_build_status for progress.
    """
    try:
        return ir.start_build(project_path, top or None)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def get_build_status(project_path: str, wait_seconds: int = 2) -> dict:
    """Current build status: phase, per-module status list, current module,
    and a tail of the live log.

    Waits wait_seconds (default 2, max 15) before reading, so this can be
    polled in a loop to render live progress. Pass 0 for an immediate read.
    """
    time.sleep(max(0, min(wait_seconds, 15)))
    try:
        return ir.get_status(project_path)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def get_module_log(project_path: str, module: str, tail_lines: int = 100) -> dict:
    """Tail of the compile log for one specific module."""
    try:
        return ir.get_module_log(project_path, module, tail_lines)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def get_blocking_issue(project_path: str) -> dict:
    """If the build is blocked on an error, return the offending module, its
    source file, the iverilog error text and parsed diagnostics."""
    try:
        return ir.get_blocking_issue(project_path)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def apply_fix(project_path: str, file_path: str, new_content: str, note: str = "") -> dict:
    """Write new_content to file_path to fix a build-blocking issue.

    The original is backed up to <file>.bak first. This does not resume the
    build by itself; call resume_build afterward."""
    try:
        return ir.apply_fix(project_path, file_path, new_content, note)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def resume_build(project_path: str, retry_module: bool = True) -> dict:
    """Resume a blocked or paused build.

    If it was 'blocked' and retry_module is true (default), the module that
    caused the block is retried; otherwise it stays failed and the build
    moves on. If it was 'paused', it simply continues."""
    try:
        return ir.resume_build(project_path, retry_module)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def pause_build(project_path: str) -> dict:
    """Ask a running build to pause once the current module finishes checking,
    so a source file can be changed via apply_fix or write_module before
    resuming. The on-demand counterpart to the automatic pause on error."""
    try:
        return ir.request_pause(project_path)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def cancel_build(project_path: str) -> dict:
    """Cancel the currently running build for a project."""
    try:
        return ir.cancel_build(project_path)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
def run_simulation(project_path: str, testbench: str = "", timeout: int = 120) -> dict:
    """Compile a testbench together with the design and run it under vvp.

    testbench: file path or module name; omit it when the project has exactly
    one registered testbench. Returns the simulation's stdout ($display
    output) and the path to any VCD the testbench dumped - pass that VCD to
    the waveform tooling to view it.
    """
    try:
        return ir.run_simulation(project_path, testbench or None, timeout)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


for _mod in ("yosys_runner", "gtkwave_runner"):
    try:
        __import__(_mod).register(mcp)
    except Exception as _e:
        print(f"[iverilog-builder] optional module {_mod} unavailable: {_e}", file=sys.stderr)

if __name__ == "__main__":
    mcp.run()
