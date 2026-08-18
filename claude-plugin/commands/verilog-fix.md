---
description: Inspect a blocked build's error and fix it by prompt, then resume
argument-hint: "[project-path-or-name] [optional: instructions for the fix]"
---

Arguments: `$ARGUMENTS` (project path/name, optionally followed by fix instructions)

1. Resolve the project the same way `/verilog-build` does.
2. Call `get_build_status` with `wait_seconds=0`. If `status != "blocked"`, tell the user
   there's nothing to fix right now and stop.
3. Call `get_blocking_issue` and show the user the failing module, file, and Vivado error
   text.
4. Read the offending source file. If the user supplied fix instructions in `$ARGUMENTS`,
   apply them directly. Otherwise propose a fix based on the error and ask for confirmation
   or alternate instructions before touching the file.
5. Once confirmed, edit the file content, call `apply_fix` with the new content and a short
   `note`, then call `resume_build`.
6. Briefly confirm the build has resumed and point the user at `/verilog-build` or
   `/verilog-status` to watch it continue.
