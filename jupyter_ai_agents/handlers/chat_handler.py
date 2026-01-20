# Copyright (c) 2024-2025 Datalayer, Inc.
#
# BSD 3-Clause License

"""Tornado handlers for chat API compatible with Vercel AI SDK."""

import json
import logging
from typing import Any

from jupyter_server.base.handlers import APIHandler
from pydantic_ai import UsageLimits
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from starlette.requests import Request

from jupyter_ai_agents.mcp_namespace import NamespacedToolset, resolve_mcp_server_id

logger = logging.getLogger(__name__)


def _parse_enabled_tool_names(raw_tools: Any) -> set[str]:
    if isinstance(raw_tools, list):
        return {tool for tool in raw_tools if isinstance(tool, str) and tool}
    if isinstance(raw_tools, str) and raw_tools:
        return {raw_tools}
    return set()


class TornadoRequestAdapter(Request):
    """Adapter to make Tornado request compatible with Starlette Request interface."""

    def __init__(self, handler: APIHandler) -> None:
        """
        Initialize the adapter with a Tornado handler.

        Args:
            handler: The Tornado RequestHandler instance
        """
        self.handler = handler
        self._body_cache = None

        # Create a minimal scope for Starlette Request
        scope = {
            "type": "http",
            "method": handler.request.method,
            "path": handler.request.path,
            "query_string": handler.request.query.encode("utf-8"),
            "headers": [
                (k.lower().encode(), v.encode())
                for k, v in handler.request.headers.items()
            ],
            "server": (
                handler.request.host.split(":")[0],
                int(handler.request.host.split(":")[1])
                if ":" in handler.request.host
                else 80,
            ),
        }

        # Initialize the parent Starlette Request
        # We need to provide a receive callable
        async def receive() -> dict[str, Any]:
            return {
                "type": "http.request",
                "body": handler.request.body,
                "more_body": False,
            }

        super().__init__(scope, receive)

    async def body(self) -> bytes:
        """Get request body as bytes."""
        if self._body_cache is None:
            self._body_cache = self.handler.request.body
        return self._body_cache if self._body_cache is not None else b""


class VercelAIChatHandler(APIHandler):
    """
    Handler for /api/chat endpoint.

    This handler implements the Vercel AI protocol for streaming chat responses.
    It receives chat messages and streams back AI responses with support for:
    - Text responses
    - Tool calls
    - Reasoning steps
    - Source citations
    """

    async def post(self) -> None:
        """Handle chat POST request with streaming."""
        try:
            # Get agent from application settings
            agent = self.settings.get("chat_agent")
            if not agent:
                self.set_status(503)
                self.finish(
                    json.dumps(
                        {
                            "error": "Chat agent not available",
                            "message": "The chat service is currently unavailable. Please check that required API keys (e.g., ANTHROPIC_API_KEY, OPENAI_API_KEY) are configured.",
                        }
                    )
                )
                return

            # Create request adapter (Starlette-compatible)
            tornado_request = TornadoRequestAdapter(self)

            # Parse request body to extract model and options
            body = {}
            try:
                body = await tornado_request.json()
                if not isinstance(body, dict):
                    body = {}
            except Exception:
                pass
            
            model = body.get("model")
            
            # Check if any MCP tools are enabled (builtinTools contains enabled tool names)
            enabled_tools = _parse_enabled_tool_names(body.get("builtinTools", []))
            enabled_servers = _parse_enabled_tool_names(body.get("enabledServers", []))
            enabled_prefixes = {tool.split(".", 1)[0] for tool in enabled_tools if "." in tool}
            use_mcp_server = bool(enabled_tools or enabled_servers)

            # Build toolsets list
            toolsets = list(self.settings.get("chat_toolsets", []))

            if use_mcp_server:
                namespaced_toolsets = []
                for index, server in enumerate(self.settings.get("mcp_servers", [])):
                    server_id = resolve_mcp_server_id(server, fallback=f"mcp_server_{index}")
                    if enabled_servers and server_id not in enabled_servers:
                        continue
                    if enabled_prefixes and server_id not in enabled_prefixes:
                        continue
                    namespaced_toolsets.append(
                        NamespacedToolset(wrapped=server, namespace=server_id)
                    )
                toolsets.extend(namespaced_toolsets)
                logger.info(
                    "Using shared MCP servers for chat request "
                    f"with {len(enabled_tools)} enabled tools"
                )

            # Get builtin tools (empty list - tools metadata is only for UI display)
            # The actual pydantic-ai tools are registered in the agent itself
            builtin_tools: list[str] = []

            # Create usage limits for the agent
            usage_limits = UsageLimits(
                tool_calls_limit=10,  # Increased for MCP tool usage
                output_tokens_limit=5000,
                total_tokens_limit=100000,
            )

            response = await VercelAIAdapter.dispatch_request(
                tornado_request,
                agent=agent,
                model=model,
                usage_limits=usage_limits,
                toolsets=toolsets,
                builtin_tools=builtin_tools,
            )
            
            await self._stream_response(response)

        except Exception as e:
            logger.error(f"Error in chat handler: {e}", exc_info=True)
            if not self._finished:
                self.set_status(500)
                self.finish(json.dumps({"error": str(e)}))

    async def _stream_response(self, response) -> None:
        """Stream the response back to the client."""
        # Set headers from FastAPI response
        for key, value in response.headers.items():
            self.set_header(key, value)

        # Stream the response body
        if hasattr(response, "body_iterator"):
            try:
                async for chunk in response.body_iterator:
                    if isinstance(chunk, bytes):
                        self.write(chunk)
                    else:
                        self.write(
                            chunk.encode("utf-8")
                            if isinstance(chunk, str)
                            else chunk
                        )
                    await self.flush()
            except Exception as stream_error:
                self.log.debug(
                    f"Stream iteration completed with: {stream_error}"
                )
        else:
            body = response.body
            if isinstance(body, bytes):
                self.write(body)
            else:
                self.write(
                    body.encode("utf-8") if isinstance(body, str) else body
                )

        # Finish the response
        if not self._finished:
            self.finish()
