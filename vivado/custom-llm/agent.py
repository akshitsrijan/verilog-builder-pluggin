#!/usr/bin/env python3
"""Minimal REPL agent that drives the verilog-builder MCP server (Vivado
edition) from any OpenAI-compatible chat completion API using a plain API
key - OpenAI, OpenRouter, Groq, Together, a local vLLM/llama.cpp server,
etc. No Claude Code / Codex / Hermes / OpenClaw install required.

Env vars:
  LLM_API_KEY   - required. API key for your provider.
  LLM_BASE_URL  - OpenAI-compatible base URL (default: https://api.openai.com/v1).
  LLM_MODEL     - model name (default: gpt-4o-mini).
  MCP_SERVER_PATH - path to mcp_server/server.py (default: sibling of this file).
  VIVADO_BIN    - passed through to the MCP server's environment.

Usage:
  pip install -r requirements.txt
  export LLM_API_KEY=sk-...
  python3 agent.py
"""

import asyncio
import json
import os
import pathlib
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_SERVER = HERE / "mcp_server" / "server.py"

SYSTEM_PROMPT = (
    "You are an assistant that builds and debugs Vivado FPGA projects for the "
    "user by calling the provided tools (verilog-builder MCP server). Prefer "
    "using the tools over guessing: create projects with create_project, "
    "start builds with start_build, poll get_build_status, and inspect "
    "get_blocking_issue/get_module_log when something fails. Explain what "
    "you did in plain language after each tool call."
)


def mcp_tool_to_openai_schema(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


async def run():
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("error: set LLM_API_KEY", file=sys.stderr)
        sys.exit(1)

    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    server_path = pathlib.Path(os.environ.get("MCP_SERVER_PATH", str(DEFAULT_SERVER)))

    llm = OpenAI(api_key=api_key, base_url=base_url)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
        env={**os.environ},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            openai_tools = [mcp_tool_to_openai_schema(t) for t in tools]
            print(f"Connected to MCP server with {len(tools)} tools. "
                  f"Model: {model} @ {base_url}")

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            while True:
                try:
                    user_input = input("\nyou> ").strip()
                except EOFError:
                    break
                if not user_input:
                    continue
                if user_input in ("exit", "quit"):
                    break
                messages.append({"role": "user", "content": user_input})

                while True:
                    resp = llm.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=openai_tools,
                    )
                    choice = resp.choices[0].message
                    messages.append(choice.model_dump(exclude_none=True))

                    if not choice.tool_calls:
                        print(f"\nassistant> {choice.content}")
                        break

                    for call in choice.tool_calls:
                        args = json.loads(call.function.arguments or "{}")
                        print(f"  [tool] {call.function.name}({args})")
                        result = await session.call_tool(call.function.name, args)
                        text = "".join(
                            block.text for block in result.content
                            if getattr(block, "type", None) == "text"
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": text,
                        })


if __name__ == "__main__":
    asyncio.run(run())
