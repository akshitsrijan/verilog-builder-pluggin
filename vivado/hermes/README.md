# Verilog Builder for Hermes Agent

Hermes port of Verilog Builder: the Vivado MCP server plus seven skills
(`verilog-new`, `verilog-build`, `verilog-status`, `verilog-timing`,
`verilog-fix`, `verilog-modify`, `generate-waveform`).

## Install

1. `pip install mcp` (into the interpreter Hermes will launch).
2. Register the MCP server: merge [`config.snippet.yaml`](config.snippet.yaml)
   into `~/.hermes/config.yaml`, fixing the absolute path.
3. Install the skills: `cp -r skills/* ~/.hermes/skills/`
4. Restart Hermes (or `/reload-mcp`). Skills are invoked as `/verilog-build`, etc.

Requires Vivado on `PATH` or `VIVADO_BIN` set. Tools are exposed to the agent as
`mcp_verilog-builder_<tool>`; the skills refer to them by bare name.

Note: config keys/paths follow Hermes' documented layout but were not tested
against a live Hermes install.
