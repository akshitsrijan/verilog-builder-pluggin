---
description: Change a module by describing the change - pausing a running Icarus build first if one is in flight
argument-hint: "[project-path-or-name] [optional: what to change]"
---

Arguments: `$ARGUMENTS` (project path/name, optionally followed by what to change)

This is how the user edits their design without opening an editor: they say what they want
different and you make the change. It's also the on-demand counterpart to `/iverilog-fix`,
which only does something once a module has *errored*.

1. Resolve the project the same way `/iverilog-build` does.
2. Call `get_build_status` with `wait_seconds=0` and branch on `status`:
   - `"running"` - call `pause_build`, then poll `get_build_status` (short `wait_seconds`,
     e.g. 2) until `status` becomes `"paused"`. The build stops once the module currently
     being checked finishes; it won't kill anything mid-flight. If it instead lands on
     `"completed"`, `"blocked"`, or `"cancelled"` first, just carry on from that state.
   - `"blocked"` - this is really a `/iverilog-fix` situation; say so, but if the user still
     wants an unrelated change, proceed.
   - anything else (`"completed"`, `"not_started"`, `"paused"`) - nothing to pause, go
     straight on.
3. If `$ARGUMENTS` said what to change, use that; otherwise ask what they want different.
4. Find the right file. `list_projects` and the project manifest give you the source list;
   read the file before editing so you change what's actually there.
5. Make the edit and call `apply_fix` with the full new file content and a short `note`
   describing the change. The original is backed up to `<file>.bak`.
6. **Show the user what changed and why**, briefly - a diff in prose, not a wall of code.
7. Get it verified:
   - If a build was paused, call `resume_build` and keep watching as `/iverilog-build` does.
   - Otherwise call `start_build` and follow the same live-progress flow - a change nobody
     recompiled is a change nobody knows works.

To add a *new* module rather than change an existing one, use the `write_module` tool
directly (same flow as `/iverilog-new` step 4) instead of `apply_fix`.
