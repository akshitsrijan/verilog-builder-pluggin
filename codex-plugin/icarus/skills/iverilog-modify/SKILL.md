---
name: iverilog-modify
description: Pause a running Icarus Verilog build safely, modify RTL, then resume.
---

# Iverilog Modify

Arguments: `the user's supplied request` (project path/name, optionally followed by what to change)

This is the on-demand counterpart to `the `iverilog-fix` skill`: that one only does anything once a
module has *errored*, but the user may want to change a source file mid-build even though
nothing is broken. Use `pause_build` for that instead of waiting for a failure.

1. Resolve the project the same way `the `iverilog-build` skill` does.
2. Call `get_build_status` with `wait_seconds=0`. If `status != "running"`, tell the user
   there's no active build to pause (point them at `the `iverilog-build` skill` to start one, or
   `the `iverilog-fix` skill` if it's already `blocked`) and stop.
3. Call `pause_build`. Tell the user the build will pause once the module currently being
   checked finishes - it won't kill anything mid-flight.
4. Poll `get_build_status` (short `wait_seconds`, e.g. 2) until `status` becomes `"paused"`.
   If it instead lands on `"completed"`, `"blocked"`, or `"cancelled"` first, report that
   outcome and stop.
5. Once paused, show the module checklist so the user sees exactly where the build stopped.
6. If `the user's supplied request` said what to change, use that; otherwise ask.
7. Make the edit:
   - to change an existing file, call `apply_fix` with the full new content and a short `note`;
   - to add a whole new module, call `write_module` - it writes the file and registers it in
     the manifest, and the build picks it up because the manifest is re-read each module.
8. Call `resume_build` and confirm. Point the user at `the `iverilog-build` skill` or
   `the `iverilog-status` skill` to keep watching.
