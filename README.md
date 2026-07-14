# verilog-builder

A Claude Code plugin (and standalone MCP server) that drives Xilinx Vivado
synthesis module-by-module, streams live progress and timing analysis, and
lets you fix synthesis errors by prompting mid-build instead of re-running
the whole flow blind.

## How it works

- `tcl/` — mechanical Vivado batch scripts: extract compile order, synthesize
  one module out-of-context, run the real project-level synth/impl run.
- `mcp_server/vivado_runner.py` — background orchestrator. Runs modules one
  at a time, writes live state to `<project_dir>/.verilog_builder/state.json`
  and per-module logs to `.verilog_builder/logs/`. Pauses on the first error
  instead of plowing through the rest of the hierarchy.
- `mcp_server/server.py` — exposes the orchestrator as MCP tools
  (`start_build`, `get_build_status`, `get_blocking_issue`, `apply_fix`,
  `resume_build`, `get_timing_report`, ...).
- `commands/` — Claude Code slash commands (`/verilog-build`,
  `/verilog-status`, `/verilog-timing`, `/verilog-fix`) that drive those
  tools and render the live, per-module progress view.

Because the logic lives entirely in the MCP server, the same tools work from
Claude Desktop too — you just lose the slash commands and drive it by asking
in plain language (Claude will call the tools directly).

## Install: Claude Code (CLI)

From this directory (or after pushing it to a git remote):

```
/plugin marketplace add /home/vboxuser/verilog-builder-plugin
/plugin install verilog-builder@verilog-builder-marketplace
```

If you push this repo to GitHub, others install it with:

```
/plugin marketplace add <your-github-org>/verilog-builder-plugin
/plugin install verilog-builder@verilog-builder-marketplace
```

Then in any session:

```
/verilog-build two_one_mux
/verilog-status two_one_mux
/verilog-timing two_one_mux
/verilog-fix two_one_mux
```

## Install: Claude Desktop

Claude Desktop doesn't run Claude Code plugins (no slash commands/hooks),
but it speaks MCP, so the same server works — just add it directly to your
Desktop MCP config (Settings -> Developer -> Edit Config), merging into
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "verilog-builder": {
      "command": "/home/vboxuser/verilog-builder-plugin/mcp_server/venv/bin/python",
      "args": ["/home/vboxuser/verilog-builder-plugin/mcp_server/server.py"],
      "env": {
        "VIVADO_BIN": "/home/vboxuser/Downloads/Xilinx/Vivado/2023.2/bin/vivado"
      }
    }
  }
}
```

Restart Desktop, then just ask: *"Build the two_one_mux Vivado project and
show me progress"* — Claude will call `start_build` / `get_build_status` /
etc. itself. There are no slash commands on Desktop, so the polling loop and
formatting come from Claude's own reasoning rather than a scripted command,
but the underlying build behavior (pause-on-error, prompt-driven fixes,
timing report) is identical since it's the same server and same state files.

This is a locally-run MCP server, not a hosted Anthropic-reviewed connector,
so it won't show up in Desktop's public Connectors marketplace browse list —
it has to be added via the config above, since it needs to run Vivado on
this machine.

## Requirements

- Vivado 2023.2 installed locally (default expected at
  `/home/vboxuser/Downloads/Xilinx/Vivado/2023.2/bin/vivado`; override via
  the `VIVADO_BIN` env var in `.mcp.json` / `claude_desktop_config.json`).
- Python 3 with the `mcp` package (already set up in `mcp_server/venv/` by
  the scaffolding step; recreate with `python3 -m venv venv && ./venv/bin/pip
  install mcp` if needed).

## Design notes / current limitations (v0.1.0)

- One active build per project at a time.
- Module boundaries are inferred from `report_compile_order` plus a
  `module <name>` regex per file, so it assumes roughly one module per file
  (true for the projects this was built against). Multi-module files will
  still work but only the first `module` declaration per file is named.
- "Full" mode runs real implementation/routing (`impl_1`), which can take a
  while depending on the design; "synth" mode (default) only goes through
  `synth_1` and out-of-context per-module synthesis, which is much faster
  and enough for early timing feedback.
- Timing summary parsing (WNS/TNS/WHS/THS) is a best-effort regex over
  Vivado's `report_timing_summary` text table; the raw report path is always
  returned so you can open it directly if parsing misses.
- If the MCP server process restarts mid-build, the in-memory thread is
  gone, but `state.json` persists — the build will show as stuck at
  `"running"` with a stale module. Re-running `/verilog-build` on the same
  project is safe: it starts a fresh build and modules already marked "done"
  from a prior run aren't reused, since a new `build_id` is issued and the
  module list is re-derived. (Restarting an in-place stuck build without a
  fresh full run isn't supported yet.)
