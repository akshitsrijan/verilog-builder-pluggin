# Zero to waveform: a beginner's tutorial

You know a little Verilog. You have never used Yosys, never heard of MCP, and
have never installed a plugin. In one sitting you will go from an empty machine
to a running 4-bit counter, a waveform on screen, and a schematic of the
circuit — and you will get there by **typing sentences**, not by writing files,
build scripts, or command lines.

Everything here runs on free, open-source tools. No Vivado, no licence, no login.

---

## 1. Install the toolchain

Four programs do the real work:

| Tool | What it is | Needed for |
|---|---|---|
| `iverilog` | Icarus Verilog — a Verilog compiler | compiling your design |
| `vvp` | Icarus's simulator (ships with `iverilog`) | running the simulation |
| `gtkwave` | a waveform viewer | *seeing* the simulation |
| `yosys` | an open-source synthesis tool | drawing schematics |

On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install iverilog gtkwave yosys graphviz
```

Then one extra, from npm, which draws far nicer schematics than graphviz does:

```bash
sudo npm install -g netlistsvg
```

If you don't have `npm`, install Node.js first (`sudo apt install nodejs npm`).
`netlistsvg` is optional — without it schematics still render, just via graphviz
and less prettily.

Check that everything landed:

```bash
iverilog -V | head -1     # Icarus Verilog version 12.0 (stable)
yosys -V                  # Yosys 0.33
gtkwave --version | head -1
which netlistsvg          # /usr/local/bin/netlistsvg
```

You also need Python 3.10+ with the `mcp` package, which is what lets the
assistant talk to these tools. Each port ships a ready virtualenv at
`mcp_server/venv/`; if you need to build your own:

```bash
python3 -m venv mcp_server/venv
mcp_server/venv/bin/pip install -r mcp_server/requirements.txt
```

## 2. Install the plugin

**Claude Code.** From inside Claude Code:

```text
/plugin marketplace add <repo>/claude-plugin/icarus
/plugin install verilog-builder-icarus
```

`<repo>` is wherever you cloned this repository.

**Codex.** Install `codex-plugin/icarus/` as a Codex plugin; its
`.codex-plugin/plugin.json` wires up the skills and the MCP server for you.

Either way the plugin brings its own **MCP server** — a small background program
named `iverilog-builder` that exposes "compile this", "simulate that", "draw a
schematic" as things the assistant can actually *do*, rather than just describe.
You never start it yourself; the plugin does.

Confirm it's live by asking:

> **You:** list my verilog projects

You should get an empty list rather than an error. An empty list means the server
is running and simply hasn't found any projects yet.

---

## 3. Make a 4-bit counter

This is the whole workflow. You describe; it builds.

> **You:** make me a new Icarus project called `counter_demo` with a 4-bit
> counter that counts up on the clock and resets to zero

**What happens.** The assistant calls `create_project`, then `write_module` with
Verilog it wrote for you. On disk you now have:

```text
~/counter_demo/
  .ivproj.json          the project manifest — this IS the project
  sources/counter.v     your design
```

`.ivproj.json` is a small JSON file listing the project name, the top module, the
sources, the testbenches, and the Verilog standard. There is no makefile, no
`.xpr`, and nothing to configure. `sources/counter.v` holds something like:

```verilog
module counter(input clk, input rst, output reg [3:0] q);
    always @(posedge clk)
        if (rst) q <= 4'd0;
        else     q <= q + 1'b1;
endmodule
```

Read it. Change it if you like — it's a normal file. But the intended way to
change it is to say so:

> **You:** actually make it count down instead

## 4. Build it

> **You:** build it

**What happens.** The assistant starts a background build and polls it, so you
see progress rather than a frozen prompt:

1. **lint** — each design file is syntax-checked *on its own* with
   `iverilog -t null`, so an error is blamed on the file that owns it.
2. **compile** — everything is compiled together into `build/counter.vvp`.
3. **simulate** — if a testbench exists, it runs.

A clean build reports `completed`. You can ask at any time:

> **You:** what's the build status?

If something is wrong, the build does not vomit a wall of red and quit. It stops
in the `blocked` state, holding the failing module and the exact error, and the
assistant explains it in English:

> **Assistant:** `counter.v:3: syntax error` — the `always` block is missing its
> `begin`. Want me to fix it?
>
> **You:** yes
>
> **Assistant:** *(backs up the file, applies the fix, resumes the build from the
> failing module)*

That backup is real: every prompt-driven edit copies the original aside and is
recorded in the build's fix log, so nothing you wrote is ever silently lost.

## 5. Show me the waveform

The single most useful sentence in this whole tutorial:

> **You:** show me its waveform

**What happens**, all in one call:

1. Your module has no testbench, so **one is written for you**. The plugin reads
   `counter`'s port list, sees a port named `clk` and one named `rst`, and
   generates:

```verilog
`timescale 1ns / 1ps

// Auto-generated by verilog-builder-icarus for module `counter`.
// Regenerate freely - edit it if you want different stimulus.
module tb_counter;

    reg clk;
    reg rst;
    wire [3:0] q;

    counter dut (
        .clk(clk),
        .rst(rst),
        .q(q)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;   // 100 MHz

    initial begin
        $dumpfile("counter.vcd");
        $dumpvars(0, tb_counter);

        rst = 1'b1;
        repeat (4) @(posedge clk);
        rst = 1'b0;
        @(posedge clk);

        repeat (20) @(posedge clk);
        $finish;
    end

endmodule
```

   Note the two things beginners most often forget: `$dumpfile`/`$dumpvars`
   (without them there is no waveform at all) and `$finish` (without it the
   simulation runs forever). The generator always emits both.

2. `iverilog` compiles design + testbench; `vvp` runs it.
3. `$dumpvars` writes **`build/counter.vcd`** — a VCD, "Value Change Dump", a
   text file recording every signal transition with its timestamp.
4. The plugin parses that VCD, ranks the signals (clock and reset first, then the
   top-level ports, testbench scratch signals last), marks the multi-bit ones to
   display in hex, and writes **`build/counter.gtkw`** — a GTKWave *save file*
   that says which signals to show and how.
5. GTKWave opens with both files, so the window comes up **already populated**.
   You do not go hunting through a signal tree.

You should see `clk` toggling, `rst` high for four cycles then dropping, and `q`
stepping `0 → 1 → 2 …` right after reset releases.

Want different stimulus? Say so:

> **You:** run it for 100 cycles instead

And if you are on a machine with no screen (SSH, a container), ask for the
signals in words instead:

> **You:** list the signals in that VCD

## 6. Show me the schematic

> **You:** show me the RTL schematic

**What happens.** `yosys` reads your design (testbenches excluded — a schematic
of a stimulus generator is noise), elaborates it with `hierarchy -top counter
-check; proc; opt_clean`, and writes a JSON netlist. `netlistsvg` turns that into
`build/schematic/counter_rtl.svg`, which opens in your image viewer.

For our counter you'll see an adder, a multiplexer (that's the `if (rst)`), and a
4-bit register — recognisable blocks, not gates. This is the open-source
equivalent of Vivado's *Open Elaborated Design* view.

To see actual gates:

> **You:** now show me the gate-level schematic

This runs a full `synth -top counter -flatten`. The `-flatten` matters a great
deal: without it, a design built out of sub-modules renders as one opaque box
with nothing inside, because the drawing tool only draws the top level. With it,
the hierarchy is dissolved and you see the real gate netlist.

Prefer numbers to pictures? Ask:

> **You:** how big is this design?

which returns cell counts by type — for our counter, one `$add`, one `$dff`, one
`$mux`, five wires.

## 7. Where everything ended up

```text
~/counter_demo/
  .ivproj.json
  sources/
    counter.v
    tb_counter.v                  the generated testbench (Codex port puts it in tb/)
  build/
    counter.vvp                   compiled design
    tb_counter.vvp                compiled testbench
    counter.vcd                   the waveform data
    counter.gtkw                  GTKWave save file
    .build_state.json             build progress, readable at any time
    logs/                         per-module and per-phase logs
    schematic/
      schematic.ys                the yosys script that was run
      counter_rtl.json            the netlist
      counter_rtl.svg             the picture
      counter_gate.svg
```

`build/` is entirely regenerable — a fine thing to put in `.gitignore`. The
manifest stores paths relative to the project root, so you can move or commit the
project directory freely.

---

## Troubleshooting

**"GTKWave didn't open" / `no display available`.**
You're on a headless machine, over SSH without X forwarding, or in a container.
The VCD and `.gtkw` were still written — the tool tells you where. Either copy
them to a desktop machine and run `gtkwave counter.vcd counter.gtkw`, or ask the
assistant to *describe* the waveform: it can list every signal in the VCD with
its scope and width without any display at all. (`ssh -X` also works if the
remote has X11 forwarding enabled.)

**"netlistsvg not found" / the schematic looks like an ugly box-and-line graph.**
`netlistsvg` isn't installed, so the plugin silently fell back to graphviz. That
fallback is functional but far less readable. Fix it with
`sudo npm install -g netlistsvg`, then check `which netlistsvg`. If it's
installed somewhere unusual, set `NETLISTSVG_BIN=/path/to/netlistsvg` in the
plugin's `.mcp.json` — the same trick works for `IVERILOG_BIN`, `VVP_BIN`,
`YOSYS_BIN`, `GTKWAVE_BIN` and `DOT_BIN`.

**The simulation hangs, then times out.**
Almost always a testbench with no `$finish`. `vvp` will happily simulate forever;
the plugin kills it at the timeout (60s in the Claude port, 120s in the Codex
port) and reports it. If you wrote the testbench yourself, add `$finish` at the
end of your stimulus. Generated testbenches always have one. A clock-only
`always #5 clk = ~clk;` with nothing to stop it is the classic culprit.

**"I got a VCD but the waveform window is empty."**
The testbench never called `$dumpfile`/`$dumpvars`, so nothing was recorded. Add:

```verilog
initial begin
    $dumpfile("mydesign.vcd");
    $dumpvars(0, tb_mydesign);
end
```

The `0` means "dump this scope and everything below it".

**`ERROR: Module ... is not part of the design` or "Unknown module type".**
Yosys or iverilog can see a module being *instantiated* but not *defined* — a
source file wasn't registered with the project. Ask:

> **You:** what modules does my project have?

and then add the missing file:

> **You:** add `~/counter_demo/sources/full_adder.v` to the project

This also happens when the top module is wrong. Say
"set the top module to `counter`" and rebuild.

**A syntax error in one file blames a completely different file.**
That is why the build lints each file alone first. Look at the per-module log:

> **You:** show me the log for the counter module

**"No project found."**
Every tool needs a directory containing a `.ivproj.json`. If you moved things
around, point at the directory explicitly ("use the project at
`~/counter_demo`"), or run `list projects` to see what the plugin can find — it
searches two levels below your home directory.

**Changes to a `.v` file don't seem to take effect.**
Nothing is cached, but the build only re-runs when you ask. Say "rebuild" after
editing a file by hand.

---

## What to try next

- Build something hierarchical — "make me a 4-bit ripple-carry adder out of full
  adders" — then compare the RTL schematic (four blocks) with the gate-level one
  (the flattened gates).
- Break something on purpose and use `/iverilog-fix` to watch the pause-to-fix
  loop work.
- Read [the pipeline document](pipeline.md) for the diagrams of exactly what runs
  when, and the build state machine.
- Full tool and command reference:
  [Claude Code port](../../claude-plugin/icarus/README.md) ·
  [Codex port](../../codex-plugin/icarus/README.md).

One thing this edition deliberately does **not** do: timing analysis. There is no
WNS/TNS/WHS/THS here, because nothing places or routes your design onto a real
FPGA. For that you still want the Vivado edition. Everything up to and including
"does my logic actually do what I meant?" is covered here.
