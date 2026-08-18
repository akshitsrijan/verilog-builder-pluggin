"""MCP server for verilog-builder: exposes Vivado build orchestration as tools
usable from both Claude Code CLI and Claude Desktop."""

import time

from mcp.server.fastmcp import FastMCP

import vivado_runner as vr

mcp = FastMCP("verilog-builder")


@mcp.tool()
def list_projects(search_root: str = "~") -> list:
    """List Vivado projects (.xpr files) found directly under search_root or one level deep."""
    return vr.list_projects(search_root)


@mcp.tool()
def create_project(project_name: str, source_files: list[str], project_dir: str = "",
                    part: str = "xc7a35tcpg236-1", constraints_file: str = "",
                    top: str = "") -> dict:
    """Create a brand-new Vivado project purely by prompting - no manual
    File > New Project in the Vivado GUI.

    source_files: list of Verilog/SystemVerilog file paths to add - either
    files that already exist on disk, or ones just written for this design.
    project_dir: defaults to ~/<project_name>/, matching the layout of every
    other project on this machine. part: target Xilinx part (defaults to
    the Basys3 part xc7a35tcpg236-1 used by the existing projects here).
    constraints_file: optional single .xdc file. top: optional top module
    name; Vivado infers it from the sources if omitted.

    Returns project_path (the new .xpr) on success, which can be passed
    straight to start_build to synthesize it.
    """
    pdir = project_dir or f"~/{project_name}"
    return vr.create_project(project_name, pdir, source_files, part,
                              constraints_file or None, top or None)


@mcp.tool()
def start_build(project_path: str, mode: str = "synth", gui: bool = True) -> dict:
    """Start a module-by-module Vivado build for the given .xpr project.

    mode: 'synth' runs out-of-context synthesis per module plus the project's
    synth_1 run for timing. 'full' additionally runs implementation/routing.

    gui: if true (default), opens a persistent Vivado GUI window that
    updates in place to show each module's synthesized schematic as it
    finishes, then the final synth_1/impl_1 run once the build completes.
    Requires a usable display; harmless best-effort if one isn't available
    (the build still proceeds headless either way). Pass gui=False to skip
    it entirely.

    Returns immediately with a build_id; poll get_build_status for progress.
    """
    return vr.start_build(project_path, mode, gui)


@mcp.tool()
def get_build_status(project_path: str, wait_seconds: int = 3) -> dict:
    """Get current build status: phase, per-module status list, current module,
    and a tail of the live Vivado log for whatever is building right now.

    Waits wait_seconds (default 3, max 15) before reading status, so callers
    can poll this in a loop to render live progress without spinning tightly.
    Pass wait_seconds=0 for an immediate read.
    """
    time.sleep(max(0, min(wait_seconds, 15)))
    return vr.get_status(project_path)


@mcp.tool()
def get_module_log(project_path: str, module: str, tail_lines: int = 100) -> dict:
    """Get the tail of the Vivado synthesis log for one specific module."""
    return vr.get_module_log(project_path, module, tail_lines)


@mcp.tool()
def get_blocking_issue(project_path: str) -> dict:
    """If the build is paused on an error, return the offending module, its
    source file, and the Vivado error text, so a fix can be proposed."""
    return vr.get_blocking_issue(project_path)


@mcp.tool()
def apply_fix(project_path: str, file_path: str, new_content: str, note: str = "") -> dict:
    """Write new_content to file_path to fix a build-blocking issue.

    The original file is backed up to file_path.bak first. This does not
    resume the build by itself; call resume_build afterward.
    """
    return vr.apply_fix(project_path, file_path, new_content, note)


@mcp.tool()
def resume_build(project_path: str, retry_module: bool = True) -> dict:
    """Resume a blocked or paused build.

    If the build was 'blocked' (an error paused it) and retry_module is true
    (default), the module that caused the block is retried; otherwise it
    stays failed and the build continues to the next module. If the build
    was 'paused' (via pause_build, a user-requested pause rather than an
    error), it simply continues from the next pending module."""
    return vr.resume_build(project_path, retry_module)


@mcp.tool()
def pause_build(project_path: str) -> dict:
    """Request that a running build pause at the next safe point (once the
    current module finishes synthesizing - this does not kill an in-flight
    Vivado process) so a source file can be modified via apply_fix before
    resuming with resume_build.

    This is the proactive, on-demand counterpart to the automatic pause
    that already happens when a module errors out: use this when the user
    wants to change something mid-build even though nothing has failed."""
    return vr.request_pause(project_path)


@mcp.tool()
def cancel_build(project_path: str) -> dict:
    """Cancel the currently running build for a project."""
    return vr.cancel_build(project_path)


@mcp.tool()
def close_gui_view(project_path: str) -> dict:
    """Close the persistent Vivado GUI window opened for this project's
    build, if one is running. Safe to call even if no GUI is open."""
    return vr.close_gui_view(project_path)


@mcp.tool()
def generate_waveform(project_path: str, testbench_file: str = "", top_module: str = "",
                       sim_time: str = "1000ns", gui: bool = True) -> dict:
    """Run a behavioral (functional) simulation and show the resulting
    waveform in Vivado - works the same way whether the design under test is
    combinational or sequential, since only the testbench's stimulus differs.

    testbench_file: path to a testbench .v/.sv file to add to the project's
    simulation fileset (write it with the Write tool first - either from a
    user-described stimulus sequence, or auto-generated based on the
    target module's ports). Pass "" to reuse whatever is already the sim
    fileset's top instead of adding a new file.
    top_module: the testbench's own module name (the sim fileset top, not
    the DUT) - required whenever testbench_file is given.
    sim_time: how long to run the simulation, Vivado time-unit syntax (e.g.
    '1000ns', '20us') - should cover every vector/cycle the testbench drives.
    gui: if true (default), reuses or launches the same persistent Vivado
    GUI window used during builds and loads the resulting waveform into it.
    Requires a usable display; harmless best-effort if one isn't available -
    the waveform database is still written to disk either way.

    Returns waveform_db/wave_config paths and gui_status; on failure returns
    an error plus log_tail from the simulation log.
    """
    return vr.generate_waveform(project_path, testbench_file, top_module, sim_time, gui)


@mcp.tool()
def get_timing_report(project_path: str) -> dict:
    """Get the parsed timing summary (WNS/TNS/WHS/THS in ns) for the most
    recently completed build of this project, plus the raw report path."""
    state = vr.get_status(project_path)
    return state.get("timing") or {"error": "timing not available yet; build may still be running"}


if __name__ == "__main__":
    mcp.run()

