---
description: Build and simulate an Icarus Verilog project module-by-module with live progress and pause-to-fix on errors
argument-hint: "[project-path-or-name]"
---

Drive a full build of an Icarus Verilog project using the iverilog-builder MCP tools.

Project argument: `$ARGUMENTS`

The build runs in three phases, and the status you poll reports which one it's in:
`modules` (each design file syntax-checked on its own) → `compile` (the whole design linked
into a `.vvp` binary) → `simulate` (the first testbench run under `vvp`).

1. **Resolve the project.**
   - If `$ARGUMENTS` is a path to a directory containing `.ivproj.json`, use it directly.
   - If it's a bare name, call `list_projects` and match by name.
   - If empty, call `list_projects` (default search root `~`) and ask which project to build.
   - If nothing turns up, the user probably hasn't made one yet - point them at
     `/iverilog-new` rather than trying to construct a project by hand.

2. **Start the build.** Call `start_build` with the resolved project path. There's nothing to
   ask about here - no synth/impl choice, no part number, no GUI. Just start it.

3. **Stream live progress.** Loop calling `get_build_status` (its built-in `wait_seconds`
   paces the polling for you - don't add your own delay). Each time, render a compact view:
   - A module checklist: `✅ done`, `⚙️ running`, `⏳ pending`, `❌ error` per module in
     `modules[]`, in order.
   - The current `phase`, so the user sees it move from checking modules to compiling to
     simulating.
   - Under whatever is currently running, the last few lines of `log_tail`.
   - Don't re-render the whole checklist every poll if nothing changed - only when `phase`,
     `current_module`, or a module's status changes - but do show fresh `log_tail` lines so
     it feels live.
   - If `status` becomes `"paused"` (from an `/iverilog-modify` pause elsewhere), report that
     and stop the loop - it's not an error.

4. **On `status == "blocked"`:** call `get_blocking_issue`. Then:
   - Show which module and file failed. The `errors` list gives you `{file, line, severity,
     message}` - quote the exact line number, and read that part of the source file so you
     can show the offending line.
   - **Explain what the error actually means in plain English.** `iverilog` messages are terse
     ("syntax error" often just means a missing semicolon on the *previous* line) and a
     beginner can't decode them. This is the most useful thing you do in this whole flow.
   - Propose a concrete fix, but **ask before applying it** - accept your fix, give their own
     instruction, or skip the module. Don't edit anything without a go-ahead.
   - Once they respond, call `apply_fix` with the full new file content and a short `note`
     (the original is backed up to `<file>.bak`), then `resume_build`. Return to step 3.

5. **On `status == "completed"`:** show the final checklist, then report the simulation:
   - `simulation.stdout` is everything the testbench printed - show it and say what it means.
   - `simulation.vcd` is the waveform file, if the testbench dumped one.
   - If the project had no testbench, say so and offer to write one - a design that compiled
     is not a design that works.

6. **On `status == "failed"` or `"cancelled"`:** report what happened and stop.

Keep the live view terse and scannable - this should feel like watching a build, not reading
a report. Save the explaining for when something breaks or the simulation finishes.
