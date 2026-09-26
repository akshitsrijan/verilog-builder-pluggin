# Verilog Builder for OpenClaw

OpenClaw port of Verilog Builder: the Vivado MCP server plus seven AgentSkills
(`verilog-new`, `verilog-build`, `verilog-status`, `verilog-timing`,
`verilog-fix`, `verilog-modify`, `generate-waveform`).

## Install

1. `pip install mcp` (into the interpreter OpenClaw will launch).
2. Register the MCP server, either by merging
   [`openclaw.mcp.json`](openclaw.mcp.json) into `~/.openclaw/openclaw.json`
   (fix the absolute path) or with
   `openclaw mcp set verilog-builder '{"command":"python3","args":["/ABS/PATH/mcp_server/server.py"],"env":{"VIVADO_BIN":"vivado"}}'`.
3. Install the skills: `cp -r skills/* ~/.openclaw/workspace/skills/`
4. Start a new session so skills and tools are picked up.

Requires Vivado on `PATH` or `VIVADO_BIN` set.

Note: config keys/paths follow OpenClaw's documented layout but were not tested
against a live OpenClaw install.
