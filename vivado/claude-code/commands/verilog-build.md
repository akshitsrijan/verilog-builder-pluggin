---
description: Build a Vivado project module-by-module with live progress, timing analysis, and pause-to-fix on errors
argument-hint: "[project-path-or-name]"
---

Drive a full build of a Vivado project using the verilog-builder MCP tools.

Project argument: `$ARGUMENTS`

1. **Resolve the project.**
   - If `$ARGUMENTS` is a path to an existing `.xpr` file, use it directly.
   - If it's a bare name, call `list_projects` and match by name.
   - If empty, call `list_projects` (default search root `~`) and ask the user which project to build.

2. **Start the build.** Call `start_build` with the resolved project path. Ask the user
   whether they want `mode="synth"` (synthesis + timing only, faster) or `mode="full"`
   (adds implementation/routing) if not obvious from context — default to `synth`. Also
   default `gui=true` (opens a persistent Vivado GUI window that updates to show each
   module's schematic as it finishes, then the final run) unless the user says they're
   headless or don't want it, in which case pass `gui=false`.

3. **Stream live progress.** Loop calling `get_build_status` (its built-in `wait_seconds`
   paces the polling for you — no need to add your own delay). Each time, render a compact
   view to the user:
   - A module checklist: `✅ done`, `⚙️ running`, `⏳ pending`, `❌ error` per module in
     `modules[]`, in order.
   - Under the currently running module, show the last few lines of `log_tail` so the user
     sees Vivado's synthesis output scroll by line by line.
   - Don't repeat the full checklist every single poll if nothing changed — only re-render
     when phase, current_module, or a module's status changes, but do show fresh log_tail
     lines each time so it feels live.
   - If the user asks to change something mid-build even though nothing has failed, tell
     them to run `/verilog-modify` (or just say what they want changed and you can call
     `pause_build` yourself) rather than editing the source file while Vivado still has the
     project open for the current module.
   - If `status` becomes `"paused"` (from a `/verilog-modify` pause elsewhere), report that
     and stop this loop — don't treat it like an error.

4. **On `status == "blocked"`:** call `get_blocking_issue`. Show the user:
   - which module/file failed and the Vivado error text.
   - Read the offending source file (around the error, if a line number is inferable).
   - Propose a concrete fix, but **ask the user how they'd like to proceed** (accept your
     proposed fix, give their own instruction, or skip the module). This is the
     prompt-driven mid-synthesis fix flow — don't apply anything without the user's go-ahead.
   - Once they respond, edit the file's contents accordingly and call `apply_fix` with the
     full new file content and a short `note` describing the change, then call
     `resume_build`. Go back to step 3.

5. **On `status == "completed"`:** show the final module checklist, then call
   `get_timing_report` and present WNS/TNS/WHS/THS in plain English (negative WNS means a
   timing violation on the worst path; point at `raw_report` for full detail).

6. **On `status == "failed"` or `"cancelled"`:** report what happened and stop.

Keep the tone of the live view terse and scannable — this is meant to feel like watching a
build progress, not reading a report.
