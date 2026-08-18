---
description: Show the current status of an Icarus Verilog build without starting or resuming anything
argument-hint: "[project-path-or-name]"
---

Project argument: `$ARGUMENTS`

Resolve the project the same way `/iverilog-build` does (directory containing
`.ivproj.json`, name match via `list_projects`, or ask if ambiguous/empty). Call
`get_build_status` with `wait_seconds=0` - a single immediate read, not a poll loop - and
render:

- overall `status` and which `phase` it's in (`modules` → `compile` → `simulate` → `done`)
- the module checklist (✅ done / ⚙️ running / ⏳ pending / ❌ error)
- if `status == "blocked"`, the `blocking_issue` summary, and mention `/iverilog-fix`
- if `status == "completed"`, the `simulation.stdout` output and the `simulation.vcd` path
- if `status == "not_started"`, say so and point at `/iverilog-build` to start one

Do not start a build, do not resume one, and do not loop - this is a one-shot snapshot.
