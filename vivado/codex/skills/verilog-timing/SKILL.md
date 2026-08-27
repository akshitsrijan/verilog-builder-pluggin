---
name: verilog-timing
description: Analyze the timing results of a completed Vivado build.
---

# Verilog Timing

Project argument: `the user's supplied request`

Resolve the project the same way `the `verilog-build` skill` does. Call `get_timing_report`.

- If timing data is present, present WNS/TNS/WHS/THS (all in ns) in a small table, then a
  one-line plain-English verdict: timing met (all non-negative) or violated (explain which
  slack went negative and what that means - e.g. negative WNS means the worst setup path
  is too slow for the target clock).
- If timing isn't available yet (build still running, or never run), say so and suggest
  running `the `verilog-build` skill`.
- Always mention `raw_report` so the user can open the full Vivado report if they want more
  than the summary numbers.

