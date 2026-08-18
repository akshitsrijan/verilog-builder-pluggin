# verilog-builder

A Claude Code plugin (and standalone MCP server) that drives Xilinx Vivado
synthesis module-by-module, streams live progress and timing analysis, shows
you each module's synthesized schematic in a live Vivado GUI window as it
completes, and lets you fix synthesis errors — or make your own prompted
changes mid-build, even without an error — instead of re-running the whole
flow blind.

## How it works

- `tcl/` — mechanical Vivado batch scripts: extract compile order, synthesize
  one module out-of-context, run the real project-level synth/impl run. Plus
  `gui_listener.tcl`, which runs inside a persistent Vivado *GUI* process and
  listens on a local socket for "show this module" / "show this run"
  commands, so one window updates in place instead of opening per module.
- `mcp_server/vivado_runner.py` — background orchestrator. Runs modules one
  at a time, writes live state to `<project_dir>/.verilog_builder/state.json`
  and per-module logs to `.verilog_builder/logs/`. Pauses on the first error
  instead of plowing through the rest of the hierarchy, and can also pause on
  request (not just on error) at the next module boundary so you can make a
  change mid-build. Also starts/drives the GUI listener process, best-effort
  — a GUI hiccup never blocks or fails the underlying build.
- `mcp_server/server.py` — exposes the orchestrator as MCP tools
  (`create_project`, `start_build`, `get_build_status`, `get_blocking_issue`,
  `apply_fix`, `resume_build`, `pause_build`, `cancel_build`,
  `close_gui_view`, `get_timing_report`, `generate_waveform`, ...).
- `commands/` — Claude Code slash commands (`/verilog-new`, `/verilog-build`,
  `/verilog-status`, `/verilog-timing`, `/verilog-fix`, `/verilog-modify`,
  `/generate_waveform`) that drive those tools and render the live,
  per-module progress view (or, for `/generate_waveform`, the simulated
  waveform).

`/verilog-new` creates the Vivado project itself — by prompt, no manual
`File > New Project` — from RTL Claude writes for you or from existing
source files you point it at, using `tcl/create_project.tcl` under the
hood. `/verilog-build` then takes over for an existing `.xpr`, whether it
came from `/verilog-new` or was created by hand.

Because the logic lives entirely in the MCP server, the same tools work from
Claude Desktop too — you just lose the slash commands and drive it by asking
in plain language (Claude will call the tools directly).

## Install: Claude Code (CLI)

From this directory (or after pushing it to a git remote):

```
/plugin marketplace add /home/vboxuser/verilog-builder-pluggin/claude-plugin
/plugin install verilog-builder@verilog-builder-marketplace
```

If you push this repo to GitHub, `.claude-plugin/marketplace.json` needs to
be discoverable at the root of whatever you point `/plugin marketplace add`
at — since it now lives under `claude-plugin/`, check the current Claude
Code docs for how your version resolves a subdirectory of a GitHub repo
(some versions need the subdirectory pushed/mirrored as its own repo, or
support a path suffix).

Then in any session:

```
/verilog-build two_one_mux
/verilog-status two_one_mux
/verilog-timing two_one_mux
/verilog-fix two_one_mux
/verilog-modify two_one_mux
/generate_waveform two_one_mux
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
      "command": "/home/vboxuser/verilog-builder-pluggin/claude-plugin/mcp_server/venv/bin/python",
      "args": ["/home/vboxuser/verilog-builder-pluggin/claude-plugin/mcp_server/server.py"],
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

## Quick start (first-time walkthrough)

New to this plugin? Here's the shortest path from zero to a finished build.

1. **Install it** (see [Install: Claude Code (CLI)](#install-claude-code-cli) above) and
   restart/reopen your Claude Code session so the slash commands show up.

2. **No project yet?** Run `/verilog-new` instead — describe the design (or point at RTL
   files you already have) and it creates the `.xpr` for you, no manual Vivado GUI steps.
   Skip to step 3 below once it's created, or let it kick straight into a build.

   **Already have a project?** You don't need to know the exact project path — just ask, or
   run a command with no argument:
   ```
   /verilog-build
   ```
   With no project given, it lists Vivado projects it can find under your home directory
   and asks which one you want. You can also pass a name or path directly, e.g.
   `/verilog-build two_one_mux`.

3. **Pick a mode when asked.** The command will ask whether you want:
   - `synth` (default, faster) — synthesis + timing only, good for early feedback.
   - `full` — also runs implementation/routing, slower but closer to a real bitstream.

4. **Watch it build.** Once started, you'll see a live per-module checklist
   (✅ done / ⚙️ running / ⏳ pending / ❌ error) with Vivado's log output scrolling
   underneath the module currently synthesizing. You don't need to do anything here —
   just watch.

5. **If a module errors out**, the build pauses instead of continuing blind. Claude will
   show you the failing module, file, and the Vivado error text, and propose a fix — but
   it will always ask before touching your source. You can accept the suggested fix, give
   your own instructions, or skip the module. Once you respond, the fix is applied and the
   build resumes automatically. If you ever want to revisit a stuck build later instead of
   fixing it immediately, run:
   ```
   /verilog-fix two_one_mux
   ```

6. **Check progress anytime without starting or resuming anything** (handy if you closed
   the session mid-build or just want a snapshot):
   ```
   /verilog-status two_one_mux
   ```

7. **When it finishes**, you'll get a final module checklist plus a timing summary. To
   pull that timing report up again later — WNS/TNS/WHS/THS in plain English, plus a
   verdict on whether timing was met — run:
   ```
   /verilog-timing two_one_mux
   ```

That's the whole loop: `/verilog-build` to start and drive a build, `/verilog-status` for
a read-only snapshot, `/verilog-fix` to unstick a blocked build on your own schedule, and
`/verilog-timing` to revisit the results. Using Claude Desktop instead? Skip the slash
commands and just ask in plain language, e.g. *"Build the two_one_mux Vivado project and
show me progress"* — see [Install: Claude Desktop](#install-claude-desktop) below.

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
  
  
##Simple Manual: Building a new module and getting it's gate architecture and waveform analysis from scratch

0. Restart your Claude Code session first. /verilog-new and the create_project tool were just added to the plugin files — your current session loaded the plugin before that, so it won't see them until you reopen/restart.

1. Create the project:
/verilog-new full_adder
When prompted:
- Choose "describe a design, write the RTL" (not "existing files").
- Describe it: "a 1-bit full adder — inputs a, b, cin; outputs sum, cout".
- Claude will show you the Verilog before creating anything — review it, ask for changes if you want a different style (structural gates vs. behavioral assign statements, different port names, etc.).
- Accept the defaults it proposes: project dir ~/full_adder/, part xc7a35tcpg236-1 (Basys3, matches your other projects), no constraints file needed for a plain combinational adder.
- It'll then ask if you want to build right away — say yes, or hold off and run step 2 later.

2. Build it (synthesis + gate-level schematic):
/verilog-build full_adder
- Pick mode synth (fast — synthesis + timing only; skip full unless you want place-and-route too).
- Keep gui=true (default) — this is what gets you the gate-level design view: a persistent Vivado GUI window pops up and shows the synthesized schematic for full_adder as soon as it finishes synthesizing.
- Watch the live checklist/log Claude streams as it runs.

3. Check timing anytime after it finishes:
/verilog-timing full_adder
Gives you WNS/TNS/WHS/THS in plain English.

4. Check status anytime without restarting anything:
/verilog-status full_adder

5. Simulate it and view the waveform:
/generate_waveform full_adder
- It'll ask whether you want to describe the input stimulus yourself or have Claude write
  default stimulus based on the module's ports (exhaustive toggling for small
  combinational designs, a generated clock/reset sequence for sequential ones).
- Claude writes the testbench under full_adder/sim/ and shows it to you before
  simulating anything.
- Once the simulation runs, the same persistent Vivado GUI window (or a fresh one, if
  none is open yet) loads the resulting waveform database so you can see every signal
  transition.
