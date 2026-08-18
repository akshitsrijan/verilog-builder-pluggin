"""MCP server for verilog-builder-icarus: the open-source Verilog flow
(iverilog + vvp) exposed as tools for Claude Code.

Same UX as the Vivado plugin - create a project by prompting, build it
module-by-module with live status, pause/fix/resume on errors - but with no
proprietary toolchain, no GUI, and no project wizard: a project is just a
directory with a `.ivproj.json` manifest.
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # mcp >= 2.0 renamed FastMCP to MCPServer
    from mcp.server import MCPServer as FastMCP

import iverilog_runner as ir
import project as pj

mcp = FastMCP("iverilog-builder")


def _load(project_path: str):
    """Load a project, returning (project, None) or (None, error_dict)."""
    try:
        return pj.load_project(project_path), None
    except pj.ProjectError as exc:
        return None, {"ok": False, "error": str(exc)}


@mcp.tool()
def list_projects(search_root: str = "~") -> dict:
    """List Icarus Verilog projects found under search_root (up to two levels
    deep). A project is any directory containing a `.ivproj.json` manifest.

    Returns name, path, top module, and source count for each.
    """
    return {"ok": True, "projects": pj.list_projects(search_root)}


@mcp.tool()
def create_project(project_name: str, project_dir: str = "", source_files: list[str] = [],
                   top: str = "", std: str = "2012") -> dict:
    """Create a brand-new Icarus Verilog project - just a directory plus a
    `.ivproj.json` manifest, no GUI wizard and no vendor tooling.

    project_dir: defaults to `~/<project_name>/`, matching the layout of the
    other projects on this machine.
    source_files: optional list of existing `.v`/`.sv` paths to register.
    Leave it empty and use `write_module` to create the RTL by prompting -
    that is the normal path for a new design.
    top: optional top module name; inferred from the last source otherwise.
    std: Verilog standard passed to iverilog as -g<std> (default 2012).

    Returns the project summary, whose `path` can be passed straight to
    `write_module`, `compile_design`, or `start_build`.
    """
    try:
        p = pj.create_project(project_name, project_dir, source_files, top, std)
    except pj.ProjectError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "status": "created", "project": p.summary()}


@mcp.tool()
def write_module(project_path: str, filename: str, content: str,
                 is_testbench: bool = False) -> dict:
    """Write a Verilog source file into a project and register it in the
    manifest, in one step.

    This is the headline tool: the user describes a module in English ("a
    4-bit ripple carry adder"), you write the Verilog, and this persists it -
    no manual file creation, no GUI. Call it once per module, and again for
    the testbench.

    filename: a bare name like `adder.v` lands under `<project>/sources/`;
    a relative path is taken relative to the project root. A missing or
    unrecognised extension becomes `.v`.
    content: the complete Verilog source text.
    is_testbench: force classification as a testbench. Files named `tb_*` or
    containing `$dumpfile`/`$finish` are detected automatically, so you
    rarely need this.

    Overwriting an existing registered file is allowed and does not duplicate
    the manifest entry.
    """
    project, err = _load(project_path)
    if err:
        return err
    try:
        written = pj.write_module(project, filename, content,
                                  True if is_testbench else None)
    except (OSError, pj.ProjectError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "file": str(written),
            "module": pj.module_name_for_file(written),
            "project": project.summary()}


@mcp.tool()
def add_sources(project_path: str, files: list[str]) -> dict:
    """Register existing `.v`/`.sv` files with a project. Testbenches are
    sorted out of the design sources automatically; duplicates are ignored."""
    project, err = _load(project_path)
    if err:
        return err
    try:
        pj.add_sources(project, files)
    except pj.ProjectError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "project": project.summary()}


@mcp.tool()
def compile_design(project_path: str, top: str = "") -> dict:
    """Compile the whole project with iverilog into a `.vvp` binary under the
    build directory.

    Returns structured `errors` as [{file, line, severity, message}] on
    failure, which is what you want to quote back to the user and act on -
    the raw `stderr` is also included. `top` overrides the manifest's top
    module for this compile only.
    """
    project, err = _load(project_path)
    if err:
        return err
    return ir.compile_design(project, top)


@mcp.tool()
def lint_design(project_path: str, file_path: str = "") -> dict:
    """Syntax-check the project with `iverilog -t null` without producing a
    binary - fast feedback on freshly written RTL.

    Pass `file_path` to check a single file instead of the whole project.
    Note that checking one file in isolation reports its instantiated
    submodules as unresolved; that is expected and not a syntax problem.
    """
    project, err = _load(project_path)
    if err:
        return err
    if file_path:
        return ir.lint_file(file_path, project.std, project.include_dirs)
    return ir.lint_design(project)


@mcp.tool()
def start_build(project_path: str, gui: bool = False) -> dict:
    """Start a module-by-module build in the background.

    The build checks each design module on its own, then compiles the whole
    design, then runs the first testbench if the project has one. It pauses
    itself ("blocked") at the first module that fails so the error can be
    fixed by prompt and the build resumed.

    Returns immediately with a build_id; poll `get_build_status` for
    progress.
    """
    return ir.start_build(project_path, gui)


@mcp.tool()
def get_build_status(project_path: str, wait_seconds: int = 3) -> dict:
    """Get current build status: phase, per-module status list, current
    module, and a tail of the live log for whatever is building right now.

    Waits wait_seconds (default 3, max 15) before reading, so this can be
    polled in a loop to render live progress without spinning tightly. Pass
    wait_seconds=0 for an immediate one-shot read.
    """
    time.sleep(max(0, min(wait_seconds, 15)))
    return ir.get_status(project_path)


@mcp.tool()
def get_module_log(project_path: str, module: str, tail_lines: int = 100) -> dict:
    """Get the tail of the build log for one specific module."""
    return ir.get_module_log(project_path, module, tail_lines)


@mcp.tool()
def get_blocking_issue(project_path: str) -> dict:
    """If the build is blocked on an error, return the offending module, its
    source file, the raw compiler output, and the parsed `errors` list, so a
    fix can be proposed against exact line numbers."""
    return ir.get_blocking_issue(project_path)


@mcp.tool()
def apply_fix(project_path: str, file_path: str, new_content: str, note: str = "") -> dict:
    """Write new_content to file_path to fix a build-blocking issue.

    The original is backed up to `<file>.bak` first. This does not resume the
    build by itself; call `resume_build` afterward.
    """
    return ir.apply_fix(project_path, file_path, new_content, note)


@mcp.tool()
def resume_build(project_path: str, retry_module: bool = True) -> dict:
    """Resume a blocked or paused build.

    If the build was 'blocked' (an error stopped it) and retry_module is true
    (default), the failing module is retried; otherwise it stays failed and
    the build continues past it. If the build was 'paused' (a user-requested
    pause rather than an error), it simply continues from the next module.
    """
    return ir.resume_build(project_path, retry_module)


@mcp.tool()
def pause_build(project_path: str) -> dict:
    """Request that a running build pause at the next safe point, once the
    module currently being checked finishes, so a source file can be changed
    via `apply_fix` before resuming.

    This is the on-demand counterpart to the automatic pause that happens
    when a module errors out: use it when the user wants to change something
    mid-build even though nothing has failed.
    """
    return ir.request_pause(project_path)


@mcp.tool()
def cancel_build(project_path: str) -> dict:
    """Cancel the currently running build for a project."""
    return ir.cancel_build(project_path)


@mcp.tool()
def run_simulation(project_path: str, testbench: str = "", run_seconds: int = 60) -> dict:
    """Compile and run a testbench under vvp, returning everything it printed
    plus the path of any VCD waveform it dumped.

    testbench: selects one of the project's testbenches by path or module
    name; omitted, the first registered testbench runs.
    run_seconds: wall-clock timeout for the simulation (default 60), not
    simulated time - a testbench that never calls `$finish` will hit this.

    The returned `vcd` path is what a waveform viewer consumes. If it is
    null, the testbench never called `$dumpfile`/`$dumpvars`.
    """
    project, err = _load(project_path)
    if err:
        return err
    return ir.run_simulation(project, testbench, run_seconds)


# --- Optional tool modules contributed by other subsystems. Each module
# exposes register(mcp) and is skipped cleanly if not yet present. ---
for _mod in ("yosys_runner", "gtkwave_runner"):
    try:
        __import__(_mod).register(mcp)
    except Exception as _e:  # pragma: no cover
        print(f"[iverilog-builder] optional module {_mod} unavailable: {_e}", file=sys.stderr)

if __name__ == "__main__":
    mcp.run()
