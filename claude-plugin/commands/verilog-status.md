---
description: Show the current status of a Vivado build without starting or resuming anything
argument-hint: "[project-path-or-name]"
---

Project argument: `$ARGUMENTS`

Resolve the project the same way `/verilog-build` does (direct `.xpr` path, name match via
`list_projects`, or ask if ambiguous/empty). Call `get_build_status` with `wait_seconds=0`
(a single immediate read, not a poll loop) and render:

- overall `status` and `phase`
- the module checklist (✅/⚙️/⏳/❌)
- if `status == "blocked"`, surface the `blocking_issue` summary and mention `/verilog-fix`
- if `status == "completed"`, show the `timing` summary if present

Do not start a new build and do not loop — this is a one-shot snapshot.
