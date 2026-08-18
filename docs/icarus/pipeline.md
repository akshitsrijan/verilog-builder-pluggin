# The Icarus pipeline

How a sentence becomes a waveform and a schematic. Everything below is what the
plugin actually runs — no vendor tools, no GUI wizards.

## The whole picture

```mermaid
flowchart TD
    U["User prompt<br/>'make me a 4-bit counter'"] --> A[Assistant]
    A -->|create_project| P[".ivproj.json manifest"]
    A -->|write_module| S["sources/counter.v"]

    S --> L["lint_design<br/>iverilog -t null, one file at a time"]
    L --> C["compile_design<br/>iverilog -g2012 -o build/counter.vvp"]

    C --> TB{"testbench<br/>for this module?"}
    TB -->|no| GEN["ensure_testbench<br/>ports parsed, clock + reset + stimulus written"]
    TB -->|yes| SIM
    GEN --> SIM["run_simulation<br/>vvp build/tb_counter.vvp"]
    SIM --> VCD["build/counter.vcd<br/>from the testbench's $dumpfile"]
    VCD --> GTKW["build/counter.gtkw<br/>signals ranked, buses set to hex"]
    GTKW --> GW["GTKWave window,<br/>signals already populated"]

    S --> Y["yosys<br/>read_verilog + hierarchy / synth"]
    Y --> J["build/schematic/&lt;top&gt;_&lt;level&gt;.json"]
    J --> NS["netlistsvg"]
    J -.->|netlistsvg missing| DOT["graphviz dot (fallback)"]
    NS --> SVG["build/schematic/&lt;top&gt;_&lt;level&gt;.svg"]
    DOT --> SVG
    SVG --> V["desktop image viewer"]
```

The two halves are independent. A schematic never needs a testbench, and a
waveform never needs yosys.

## The simulation path, step by step

1. **`write_module`** persists the Verilog and registers it in `.ivproj.json`.
   Nothing is written by hand, and no build script exists to edit.
2. **Lint** runs `iverilog` over each design file on its own, so a syntax error
   is attributed to the module that owns it rather than to the whole design.
3. **Compile** runs `iverilog -g<std>` across every registered source into a
   single `.vvp` binary under `build/`.
4. **Testbench.** If the module has no testbench, the plugin parses its port list
   — resolving parameterised widths — and writes one that instantiates the module
   by name, generates a clock if there is a clock-shaped port, pulses reset (with
   the right polarity for an `*_n` name), sweeps the inputs (exhaustively for a
   small combinational design, a clocked run otherwise), calls `$dumpfile` /
   `$dumpvars`, and **always calls `$finish`**.
5. **Simulate** runs `vvp` with its working directory set to `build/`, so a
   relative `$dumpfile` path lands there. The VCD path is read back out of the
   testbench's `$dumpfile(...)`, falling back to `build/dump.vcd`.
6. **`.gtkw`.** The VCD is parsed for every signal (scope, name, width), helper
   signals from the testbench are demoted, clocks and resets and top-level ports
   are ranked first, and multi-bit buses are flagged `@22` so GTKWave shows them
   in hex. Up to 40 signals go into the save file.
7. **View.** GTKWave is launched detached with both files, so the tool returns
   immediately and the window survives. With no `DISPLAY` it says so and hands
   back the paths instead of hanging.

## The schematic path

```mermaid
flowchart LR
    V["design sources<br/>(testbenches excluded)"] --> R["read_verilog -sv"]
    R --> H{"level"}
    H -->|rtl| E["hierarchy -top T -check<br/>proc; opt_clean"]
    H -->|gate| G["synth -top T -flatten"]
    E --> W["write_json"]
    G --> W
    E --> WD["write dot backend"]
    G --> WD
    W --> N["netlistsvg → .svg"]
    WD --> D["dot → .svg/.png"]
```

- **`level="rtl"`** stops after elaboration and light optimisation, so adders,
  multiplexers and registers survive as recognisable blocks. This is the view
  that corresponds to Vivado's *Open Elaborated Design*, and it is the one to
  look at first.
- **`level="gate"`** runs a full `synth`, **with `-flatten`**. The flatten is not
  cosmetic: without it, netlistsvg draws only the top module, so a hierarchical
  design (a 4-bit adder built from full adders, say) renders as a single opaque
  box with no gates in it at all. With it you see the actual gate netlist.
- Testbenches are deliberately excluded from the source list — a schematic of a
  stimulus generator is noise.
- Everything is kept: the generated `schematic.ys` script, the yosys JSON
  netlist, and the rendered image all sit in `build/schematic/`, so a render can
  be reproduced or re-styled without re-running the plugin.

## The build state machine

`start_build` returns immediately with a `build_id` and runs the work on a
background thread. State is persisted to `<build_dir>/.build_state.json` and
rewritten atomically after every transition, so any process can read it —
`get_build_status` is just a read of that file plus a 20-line tail of the log
that is being written right now.

```mermaid
stateDiagram-v2
    [*] --> not_started
    not_started --> running: start_build
    running --> blocked: a module or the compile fails
    running --> paused: pause_build honoured at a module boundary
    running --> completed: all phases clean
    running --> failed: unexpected error
    running --> cancelled: cancel_build
    blocked --> running: apply_fix then resume_build
    paused --> running: resume_build
    completed --> [*]
```

Phases inside `running`:

- **Claude port:** `modules` → `compile` → `simulate` → `done`.
- **Codex port:** `modules` → `elaborate` → `done`.

Per-module status is `pending` → `running` → `done`, or `error`.

### The pause-to-fix loop

This is the point of the whole design: a failing build stops and waits for you
instead of dumping a wall of red.

```mermaid
sequenceDiagram
    participant U as User
    participant A as Assistant
    participant S as iverilog-builder
    U->>A: /iverilog-build my_cpu
    A->>S: start_build
    loop while running
        A->>S: get_build_status
        S-->>A: phase, module list, log tail
    end
    S-->>A: status = blocked
    A->>S: get_blocking_issue
    S-->>A: module, file, error, parsed diagnostics, log path
    A->>U: here is the failing line and why it fails
    U->>A: yes, fix it that way
    A->>S: apply_fix (backs the file up first)
    A->>S: resume_build (retry_module = true)
    S-->>A: running again from the failing module
```

`apply_fix` backs the original file up and appends to the state's `fix_log`, so
every prompt-driven edit is recoverable. `resume_build` with `retry_module=True`
resets the failing module to `pending` and restarts the orchestrator; with
`False` it leaves that module failed and moves on.

`pause_build` is cooperative — it sets `pause_requested`, which the orchestrator
honours *between* modules. It never kills an in-flight `iverilog` process, which
is why `/iverilog-modify` can safely change RTL mid-build.

## Files a project accumulates

```text
counter_demo/
  .ivproj.json                  name, top, sources, testbenches, build_dir, std,
                                include_dirs, created, resolved toolchain paths
  sources/counter.v             design RTL
  sources/tb_counter.v          generated testbench   (Claude port)
  tb/tb_counter.v               generated testbench   (Codex port)
  build/
    counter.vvp                 compiled design
    tb_counter.vvp              compiled testbench
    counter.vcd                 waveform dump
    counter.gtkw                GTKWave save file
    .build_state.json           the state machine above
    logs/
      counter.log               per-module lint output
      compile.log / elaborate.log
      simulate.log / tb_counter_sim.log
    schematic/
      schematic.ys              the generated yosys script
      counter_rtl.json          yosys netlist
      counter_rtl.svg           rendered schematic
      counter_gate.svg          gate-level render, if asked for
```

Paths in the manifest are stored relative to the project root where possible, so
a project directory can be moved or committed to git. `build/` is entirely
regenerable and is a reasonable thing to `.gitignore`.

## Where to go next

- [Beginner tutorial](beginner-tutorial.md) — zero to waveform in one sitting.
- [Claude Code port README](../../claude-plugin/icarus/README.md)
- [Codex port README](../../codex-plugin/icarus/README.md)
