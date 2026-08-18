---
description: Inspect a blocked Icarus build's error, explain it, and fix it by prompt, then resume
argument-hint: "[project-path-or-name] [optional: instructions for the fix]"
---

Arguments: `$ARGUMENTS` (project path/name, optionally followed by fix instructions)

1. Resolve the project the same way `/iverilog-build` does (directory containing
   `.ivproj.json`, name match via `list_projects`, or ask if ambiguous/empty).
2. Call `get_build_status` with `wait_seconds=0`. If `status != "blocked"`, say there's
   nothing to fix right now and stop - if it's still `"running"`, tell them to watch it with
   `/iverilog-status` instead.
3. Call `get_blocking_issue` and show the failing module, file, and the compiler output.
   The `errors` list gives `{file, line, severity, message}` - use the line number.
4. Read the offending source file around that line. **Explain the error in plain English
   before proposing anything** - `iverilog`'s "syntax error" usually points at the line
   *after* the real mistake (a missing `;` or an unclosed `begin`), and that's not obvious to
   someone learning. Show the actual offending line.
5. If the user supplied fix instructions in `$ARGUMENTS`, apply those. Otherwise propose a
   fix and ask for confirmation or a different instruction before touching the file.
6. Once confirmed, call `apply_fix` with the full new file content and a short `note` (the
   original is backed up to `<file>.bak`), then `resume_build`.
7. Confirm the build resumed, and either keep watching it as `/iverilog-build` step 3 does or
   point the user at `/iverilog-status`.
