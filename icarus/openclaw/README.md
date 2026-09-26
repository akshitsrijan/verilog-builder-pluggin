# Icarus Verilog Builder for OpenClaw

OpenClaw port of the Icarus Verilog edition: the iverilog/Yosys/GTKWave MCP
server plus seven AgentSkills (`iverilog-new`, `iverilog-build`, `iverilog-status`, `iverilog-fix`,
`iverilog-modify`, `iverilog-waveform`, `iverilog-schematic`).

## Install

1. `pip install -r mcp_server/requirements.txt`
2. Install `iverilog`, `yosys` and `gtkwave` and put them on `PATH`.
3. Merge [`openclaw.mcp.json`](openclaw.mcp.json) into
   `~/.openclaw/openclaw.json` (fix the absolute path), or use
   `openclaw mcp set iverilog-builder '{"command":"python3","args":["/ABS/PATH/mcp_server/server.py"]}'`.
4. `cp -r skills/* ~/.openclaw/workspace/skills/`
5. Start a new session.

Note: config keys/paths follow OpenClaw's documented layout but were not tested
against a live OpenClaw install.
