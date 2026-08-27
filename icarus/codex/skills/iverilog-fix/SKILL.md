---
name: iverilog-fix
description: Inspect a blocked Icarus Verilog build, apply a confirmed fix, and resume it.
---

# Iverilog Fix

Arguments: `the user's supplied request` (project path/name, optionally followed by fix instructions)

1. Resolve the project the same way `the `iverilog-build` skill` does.
2. Call `get_build_status` with `wait_seconds=0`. If `status != "blocked"`, tell the user
   there's nothing to fix right now and stop.
3. Call `get_blocking_issue` and show the failing module, file, and the parsed `diagnostics`
   (`file:line: severity: message`) - lead with the line number, not the raw stderr blob.
4. Read the offending source file around that line. Explain what iverilog is actually
   objecting to in plain terms; note that a syntax error is often reported on the line *after*
   the real mistake (a missing semicolon shows up on the next statement).
5. If the user supplied fix instructions in `the user's supplied request`, apply them directly.
   Otherwise propose a fix and ask for confirmation or alternate instructions before touching
   the file.
6. Once confirmed, call `apply_fix` with the full new file content and a short `note` (the
   original is backed up to `<file>.bak` automatically), then call `resume_build`, which
   retries the failed module by default.
7. Confirm the build has resumed and point the user at `the `iverilog-build` skill` or
   `the `iverilog-status` skill` to watch it continue.
