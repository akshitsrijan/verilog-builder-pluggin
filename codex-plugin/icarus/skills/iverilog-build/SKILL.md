---
name: iverilog-build
description: Build an Icarus Verilog project module-by-module with live progress and prompt-driven fixes.
---

# Iverilog Build

Drive a full build of an Icarus Verilog project using the iverilog-builder MCP tools.

Project argument: `the user's supplied request`

1. **Resolve the project.**
   - If `the user's supplied request` is a path to a directory containing `.ivproj.json` (or the
     manifest itself), use it directly.
   - If it's a bare name, call `list_projects` and match by name.
   - If empty, call `list_projects` (default search root `~`) and ask the user which project
     to build.

2. **Start the build.** Call `start_build` with the resolved project path. Each source file is
   checked on its own first - so an error points at one module rather than a wall of output -
   and then the whole design is elaborated into a single `.vvp`.

3. **Stream live progress.** Loop calling `get_build_status` (its built-in `wait_seconds` paces
   the polling for you - no need to add your own delay). Each time, render a compact view:
   - A module checklist: `✅ done`, `⚙️ running`, `⏳ pending`, `❌ error` per module in
     `modules[]`, in order.
   - Under the currently running module, show the last few lines of `log_tail`.
   - Don't repeat the full checklist every poll if nothing changed - re-render only when
     `phase`, `current_module`, or a module's status changes, but do show fresh `log_tail`
     lines so it feels live.
   - When `phase` becomes `elaborate`, say so: that's the whole design being linked together,
     the step that catches mismatched port connections between modules.
   - If the user wants to change something mid-build even though nothing has failed, point
     them at `the `iverilog-modify` skill` (or just call `pause_build` yourself) rather than editing
     a source file underneath a running build.
   - If `status` becomes `"paused"`, report it and stop the loop - that's not an error.

4. **On `status == "blocked"`:** call `get_blocking_issue`. Show the user:
   - which module/file failed, and the `diagnostics` entries (`file`, `line`, `severity`,
     `message`) rather than raw stderr where you can - the line number is the useful part.
   - Read the offending source file around that line.
   - Explain in plain terms what iverilog is complaining about. Beginners hit the same few
     things: a missing semicolon, `reg` vs `wire` (anything assigned in an `always` block must
     be `reg`), a port width mismatch, an undeclared identifier, or a module name typo.
   - Propose a concrete fix, then **ask the user how they'd like to proceed** (accept it, give
     their own instruction, or skip the module). Don't apply anything without a go-ahead.
   - Once they respond, call `apply_fix` with the full new file content and a short `note`,
     then `resume_build`. Go back to step 3.

5. **On `status == "completed"`:** show the final checklist and the `output` `.vvp` path, then
   offer to run the simulation with `run_simulation` - a design that compiles isn't yet a
   design that works, and the testbench's `$display` output is what actually proves it.

6. **On `status == "failed"` or `"cancelled"`:** report what happened and stop.

Keep the live view terse and scannable - this should feel like watching a build, not reading
a report.
