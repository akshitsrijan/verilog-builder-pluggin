---
name: verilog-modify
description: Pause a running Vivado build safely, modify RTL, then resume.
---

# Verilog Modify

Arguments: `the user's supplied request` (project path/name, optionally followed by what to change)

This is the on-demand counterpart to `the `verilog-fix` skill`: `the `verilog-fix` skill` only does anything once
a module has *errored*, but the user may want to change a source file mid-build even though
nothing is broken. Use `pause_build` for that instead of waiting for a failure.

1. Resolve the project the same way `the `verilog-build` skill` does (direct `.xpr` path, name match
   via `list_projects`, or ask if ambiguous/empty).
2. Call `get_build_status` with `wait_seconds=0`. If `status != "running"`, tell the user
   there's no active build to pause right now (point them at `the `verilog-build` skill` to start one,
   or `the `verilog-fix` skill` if it's already `blocked`) and stop.
3. Call `pause_build`. Tell the user the build will pause once the module currently
   synthesizing finishes (it won't kill anything mid-flight) - this may take a few seconds.
4. Poll `get_build_status` (short `wait_seconds`, e.g. 2) until `status` becomes `"paused"`.
   If it instead lands on `"completed"`, `"blocked"`, or `"cancelled"` before pausing,
   report that outcome instead and stop.
5. Once paused, show the module checklist so the user sees exactly where the build stopped
   (which modules are done, which is next).
6. If `the user's supplied request` included what to change, use that; otherwise ask the user what
   modification they want to make.
7. Read the relevant source file, make the edit, call `apply_fix` with the full new file
   content and a short `note` describing the change, then call `resume_build`.
8. Confirm the build has resumed and point the user at `the `verilog-build` skill` or `the `verilog-status` skill`
   to keep watching. If a GUI window is open for this build, mention it'll keep showing
   whichever module/run it last displayed until the next module finishes.

