# Verilog Builder for custom LLM providers

Generic edition for any OpenAI-compatible chat completion API that takes a
plain API key - OpenAI, OpenRouter, Groq, Together, Fireworks, a local
llama.cpp/vLLM server, etc. This does not need Claude Code, Codex, Hermes, or
OpenClaw installed: `agent.py` is a small standalone REPL that speaks the
OpenAI chat-completions + tool-calling format directly, and drives the same
Vivado MCP server (`create_project`, `start_build`, `get_build_status`,
`apply_fix`, `resume_build`, `generate_waveform`, `get_timing_report`, etc.)
used by the other frontends in this repo.

## Install

1. `pip install -r requirements.txt`
2. Set your provider's API key and (optionally) endpoint/model:
   ```
   export LLM_API_KEY=sk-...
   export LLM_BASE_URL=https://api.openai.com/v1   # or any OpenAI-compatible URL
   export LLM_MODEL=gpt-4o-mini
   ```
3. `export VIVADO_BIN=vivado` (or the full path) if Vivado isn't on `PATH`.
4. `python3 agent.py`

Type at the `you>` prompt; the agent calls MCP tools on your behalf and
prints what it did before answering. `exit` or Ctrl-D to quit.

## Notes

- `MCP_SERVER_PATH` can point `agent.py` at a different `server.py` if you
  want to reuse this client against a modified server.
- Any provider that implements the OpenAI `chat.completions` API with tool
  calling works; providers without tool-calling support won't be able to
  invoke the MCP tools.
