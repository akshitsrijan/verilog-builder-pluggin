---
name: iverilog-status
description: Show the current Icarus Verilog build status without starting or changing it.
---

# Iverilog Status

Project argument: `the user's supplied request`

Resolve the project the same way `the `iverilog-build` skill` does (direct project directory,
name match via `list_projects`, or ask if ambiguous/empty). Call `get_build_status` with
`wait_seconds=0` - a single immediate read, not a poll loop - and render:

- overall `status` and `phase`
- the module checklist (✅ done / ⚙️ running / ⏳ pending / ❌ error)
- if `status == "blocked"`, surface the `blocking_issue` summary and mention
  `the `iverilog-fix` skill`
- if `status == "completed"`, show the `output` `.vvp` path and offer `run_simulation`
- if `status == "not_started"`, say so and point at `the `iverilog-build` skill`

Do not start a build, do not loop - this is a one-shot snapshot.
