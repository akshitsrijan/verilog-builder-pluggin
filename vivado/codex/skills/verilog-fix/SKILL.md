---
name: verilog-fix
description: Inspect a blocked Vivado build, apply a confirmed fix, and resume it.
---

# Verilog Fix

Arguments: `the user's supplied request` (project path/name, optionally followed by fix instructions)

1. Resolve the project the same way `the `verilog-build` skill` does.
2. Call `get_build_status` with `wait_seconds=0`. If `status != "blocked"`, tell the user
   there's nothing to fix right now and stop.
3. Call `get_blocking_issue` and show the user the failing module, file, and Vivado error
   text.
4. Read the offending source file. If the user supplied fix instructions in `the user's supplied request`,
   apply them directly. Otherwise propose a fix based on the error and ask for confirmation
   or alternate instructions before touching the file.
5. Once confirmed, edit the file content, call `apply_fix` with the new content and a short
   `note`, then call `resume_build`.
6. Briefly confirm the build has resumed and point the user at `the `verilog-build` skill` or
   `the `verilog-status` skill` to watch it continue.

