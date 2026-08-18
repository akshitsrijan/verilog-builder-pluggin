---
name: verilog-status
description: Show the current Vivado build status without starting or changing it.
---

# Verilog Status

Project argument: `the user's supplied request`

Resolve the project the same way `the `verilog-build` skill` does (direct `.xpr` path, name match via
`list_projects`, or ask if ambiguous/empty). Call `get_build_status` with `wait_seconds=0`
(a single immediate read, not a poll loop) and render:

- overall `status` and `phase`
- the module checklist (✅/⚙️/⏳/❌)
- if `status == "blocked"`, surface the `blocking_issue` summary and mention `the `verilog-fix` skill`
- if `status == "completed"`, show the `timing` summary if present

Do not start a new build and do not loop — this is a one-shot snapshot.

