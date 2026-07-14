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
def start_build(project_path: str, mode: str = "synth") -> dict:
    """Start a module-by-module Vivado build for the given .xpr project.

    mode: 'synth' runs out-of-context synthesis per module plus the project's
    synth_1 run for timing. 'full' additionally runs implementation/routing.
    Returns immediately with a build_id; poll get_build_status for progress.
    """
    return vr.start_build(project_path, mode)


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
    """Resume a blocked build. If retry_module is true (default) the module
    that caused the block is retried; otherwise it stays failed and the
    build continues to the next module."""
    return vr.resume_build(project_path, retry_module)


@mcp.tool()
def cancel_build(project_path: str) -> dict:
    """Cancel the currently running build for a project."""
    return vr.cancel_build(project_path)


@mcp.tool()
def get_timing_report(project_path: str) -> dict:
    """Get the parsed timing summary (WNS/TNS/WHS/THS in ns) for the most
    recently completed build of this project, plus the raw report path."""
    state = vr.get_status(project_path)
    return state.get("timing") or {"error": "timing not available yet; build may still be running"}


if __name__ == "__main__":
    mcp.run()
