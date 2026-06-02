"""OpenAI tool-use agent that routes queries to MCP vehicle tools.

Converts MCP tool schemas to OpenAI function definitions, runs the
conversation loop, and dispatches tool calls back to the MCP server.
"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI
from rich.console import Console
from rich.markdown import Markdown

from agent.mcp_client import MCPClient
from server.settings import settings

logger = logging.getLogger(__name__)
console = Console()

_SYSTEM_PROMPT = """You are a helpful assistant for Volkswagen vehicle owners.
You have access to real-time telemetry data from the user's VW vehicle via MCP tools.

Important context:
- Vehicle data is sourced from the VW EU Data Act portal and may be up to 15 minutes old.
- Always mention data_age_seconds when reporting live values so the user knows how fresh the data is.
- If tools return an error about data not being available, explain the 15-minute delay and suggest trying again.
- When reporting location, offer to format coordinates as a maps link if helpful.
- Be concise and friendly."""


def _mcp_tools_to_openai(mcp_tools: list[dict]) -> list[dict]:
    """Convert MCP tool descriptors to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
            },
        }
        for t in mcp_tools
    ]


class ChatAgent:
    def __init__(self, mcp: MCPClient) -> None:
        self._mcp = mcp
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self._messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        self._tools: list[dict] = []

    async def initialize(self) -> None:
        mcp_tools = await self._mcp.list_tools()
        self._tools = _mcp_tools_to_openai(mcp_tools)
        logger.info("Loaded %d MCP tools", len(mcp_tools))

    async def _handle_tool_calls(self, tool_calls: list) -> None:
        for tc in tool_calls:
            fn = tc.function
            args = json.loads(fn.arguments or "{}")
            console.print(f"[dim]→ calling tool [bold]{fn.name}[/bold]({args})[/dim]")

            try:
                result = await self._mcp.call_tool(fn.name, args)
                content = json.dumps(result) if not isinstance(result, str) else result
            except Exception as exc:
                content = json.dumps({"error": str(exc)})

            self._messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                }
            )

    async def chat(self, user_input: str) -> None:
        self._messages.append({"role": "user", "content": user_input})

        while True:
            response = await self._openai.chat.completions.create(
                model=settings.openai_model,
                messages=self._messages,
                tools=self._tools or None,
                tool_choice="auto" if self._tools else None,
            )

            choice = response.choices[0]
            msg = choice.message
            self._messages.append(msg.model_dump(exclude_unset=True))

            if msg.tool_calls:
                await self._handle_tool_calls(msg.tool_calls)
                # Loop back to let OpenAI process tool results
                continue

            # Final assistant response
            if msg.content:
                console.print(Markdown(msg.content))
            break

    async def run_loop(self) -> None:
        console.print(
            "[bold green]VW Vehicle Agent[/bold green] — type your question or [bold]exit[/bold] to quit.\n"
        )
        while True:
            try:
                user_input = console.input("[bold blue]You:[/bold blue] ").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\nGoodbye!")
                break

            if user_input.lower() in {"exit", "quit", "q"}:
                console.print("Goodbye!")
                break

            if not user_input:
                continue

            try:
                await self.chat(user_input)
            except Exception:
                logger.exception("Chat error")
                console.print("[red]Something went wrong. Please try again.[/red]")
