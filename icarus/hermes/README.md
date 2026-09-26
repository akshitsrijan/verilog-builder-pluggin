# Icarus Verilog Builder for Hermes Agent

Hermes port of the Icarus Verilog edition: the iverilog/Yosys/GTKWave MCP
server plus seven skills (`iverilog-new`, `iverilog-build`, `iverilog-status`, `iverilog-fix`,
`iverilog-modify`, `iverilog-waveform`, `iverilog-schematic`).

## Install

1. `pip install -r mcp_server/requirements.txt`
2. Install `iverilog`, `yosys` and `gtkwave` and put them on `PATH`.
3. Merge [`config.snippet.yaml`](config.snippet.yaml) into
   `~/.hermes/config.yaml`, fixing the absolute path.
4. `cp -r skills/* ~/.hermes/skills/`
5. Restart Hermes (or `/reload-mcp`).

Note: config keys/paths follow Hermes' documented layout but were not tested
against a live Hermes install.
