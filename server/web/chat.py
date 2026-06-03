"""Web chat UI handler.

Serves a browser-based chat interface at GET / and streams OpenAI responses
via SSE at POST /api/chat. Tools are called directly as async Python functions
(same process — no MCP OAuth round-trip needed for internal calls).

Session history is kept in-memory keyed by a client-generated UUID that the
browser stores in sessionStorage. History is lost on server restart, which is
acceptable for this use case.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import AsyncIterator

from openai import AsyncOpenAI
from starlette.requests import Request
from starlette.responses import HTMLResponse, StreamingResponse

from server.settings import settings

logger = logging.getLogger(__name__)

# ── In-memory session store ────────────────────────────────────────────────────
_sessions: dict[str, list[dict]] = {}

_SYSTEM_PROMPT = (
    "You are a friendly assistant for Volkswagen vehicle owners. "
    "You have access to real-time telemetry from the user's VW via the tools provided. "
    "Data comes from the VW EU Data Act portal and may be up to 15 minutes old — always "
    "mention how fresh the data is (data_age_seconds). "
    "Be concise. Use metric units. "
    "If a tool returns an error about data not being available yet, explain the 15-minute "
    "batch delivery cycle and suggest the user tries again shortly."
)

_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_vehicle_battery",
            "description": "Returns battery level (%), estimated range (km), and whether the car is charging.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vin": {"type": "string", "description": "VIN (leave blank to use the default vehicle)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vehicle_location",
            "description": "Returns the vehicle's last known GPS coordinates and odometer reading.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vin": {"type": "string", "description": "VIN (leave blank to use the default vehicle)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_climate_status",
            "description": "Returns cabin and exterior temperature and whether climatisation is active.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vin": {"type": "string", "description": "VIN (leave blank to use the default vehicle)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_charging_status",
            "description": "Returns charging power (kW), charge target SoC, and session state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vin": {"type": "string", "description": "VIN (leave blank to use the default vehicle)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vehicle_summary",
            "description": "Returns a full snapshot of all vehicle telemetry: battery, location, climate, charging, and odometer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vin": {"type": "string", "description": "VIN (leave blank to use the default vehicle)"},
                },
            },
        },
    },
]

_TOOL_LABELS: dict[str, str] = {
    "get_vehicle_battery": "Checking battery…",
    "get_vehicle_location": "Getting location…",
    "get_climate_status": "Checking climate…",
    "get_charging_status": "Checking charging…",
    "get_vehicle_summary": "Fetching vehicle status…",
}


async def _dispatch(name: str, args: dict) -> dict:
    """Call a tool function directly (no MCP round-trip)."""
    from server.tools.battery import get_vehicle_battery
    from server.tools.charging import get_charging_status
    from server.tools.climate import get_climate_status
    from server.tools.location import get_vehicle_location
    from server.tools.summary import get_vehicle_summary

    fn_map = {
        "get_vehicle_battery": get_vehicle_battery,
        "get_vehicle_location": get_vehicle_location,
        "get_climate_status": get_climate_status,
        "get_charging_status": get_charging_status,
        "get_vehicle_summary": get_vehicle_summary,
    }
    fn = fn_map.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await fn(**args)
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return {"error": str(exc)}


async def _sse_stream(session_id: str, user_message: str) -> AsyncIterator[str]:
    """Run the OpenAI → tool → OpenAI loop and yield SSE events."""
    history = _sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": user_message})

    if not settings.openai_api_key:
        yield f"data: {json.dumps({'type': 'error', 'message': 'OPENAI_API_KEY is not configured on the server.'})}\n\n"
        return

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}] + history

    while True:
        response_text = ""
        tool_calls_acc: dict[int, dict] = {}
        finish_reason = None

        try:
            stream = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                stream=True,
            )

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                delta = choice.delta

                # Stream text content
                if delta.content:
                    response_text += delta.content
                    yield f"data: {json.dumps({'type': 'text', 'content': delta.content})}\n\n"

                # Accumulate tool call deltas
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["arguments"] += tc.function.arguments

        except Exception as exc:
            logger.exception("OpenAI stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        if finish_reason == "tool_calls" and tool_calls_acc:
            # Add assistant message containing the tool_calls
            messages.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls_acc.values()
                ],
            })

            # Execute each tool and append results
            for tc in tool_calls_acc.values():
                label = _TOOL_LABELS.get(tc["name"], f"Calling {tc['name']}…")
                yield f"data: {json.dumps({'type': 'tool', 'label': label})}\n\n"

                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                result = await _dispatch(tc["name"], args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })

            # Loop back to let OpenAI process tool results

        else:
            # Final assistant turn — persist to history and signal done
            if response_text:
                history.append({"role": "assistant", "content": response_text})
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
            break


# ── Starlette handlers ─────────────────────────────────────────────────────────

async def index_handler(request: Request) -> HTMLResponse:
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


async def chat_endpoint(request: Request) -> StreamingResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}

    message = (body.get("message") or "").strip()
    if not message:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'Empty message'})}\n\n"]),
            media_type="text/event-stream",
        )

    session_id = body.get("session_id") or str(uuid.uuid4())

    return StreamingResponse(
        _sse_stream(session_id, message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables nginx/traefik response buffering
        },
    )


async def clear_session_endpoint(request: Request) -> HTMLResponse:
    body = await request.json()
    session_id = body.get("session_id", "")
    _sessions.pop(session_id, None)
    return HTMLResponse("{}", status_code=200)
