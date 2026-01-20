# Copyright (c) 2024-2025 Datalayer, Inc.
#
# BSD 3-Clause License

"""Config handler."""

import json
import logging
import os

import tornado

from agent_runtimes.mcp.servers import initialize_mcp_servers
from jupyter_server.base.handlers import APIHandler
from jupyter_server.extension.handler import ExtensionHandlerMixin
from jupyter_ai_agents.__version__ import __version__
from jupyter_ai_agents.mcp_namespace import (
    build_namespaced_tool_name,
    resolve_mcp_server_id,
)


logger = logging.getLogger(__name__)


class ConfigHandler(ExtensionHandlerMixin, APIHandler):
    """The handler for configurations.
    
    Returns the agent configuration including available models and tools.
    This endpoint is queried by the agent-runtimes Chat component.
    """

    @tornado.web.authenticated
    async def get(self):
        """Returns the configuration for the chat agent.
        
        Returns a JSON object with:
        - models: List of available models
        - builtinTools: List of built-in tools
        - mcpServers: List of MCP servers (optional)
        """
        # Build model list based on available API keys
        models = []
        
        # Check for Anthropic
        if os.environ.get("ANTHROPIC_API_KEY"):
            models.append({
                "id": "anthropic:claude-sonnet-4-20250514",
                "name": "Claude Sonnet 4",
                "isAvailable": True,
            })
            models.append({
                "id": "anthropic:claude-3-5-sonnet-latest",
                "name": "Claude 3.5 Sonnet",
                "isAvailable": True,
            })
        
        # Check for OpenAI
        if os.environ.get("OPENAI_API_KEY"):
            models.append({
                "id": "openai:gpt-4o",
                "name": "GPT-4o",
                "isAvailable": True,
            })
            models.append({
                "id": "openai:gpt-4o-mini",
                "name": "GPT-4o Mini",
                "isAvailable": True,
            })
        
        # If no models available, add a placeholder
        if not models:
            models.append({
                "id": "none",
                "name": "No models available",
                "isAvailable": False,
            })
        
        # Build MCP servers list from agent-runtimes
        mcp_servers = []
        try:
            servers = await initialize_mcp_servers()
        except Exception as exc:
            logger.warning("Failed to initialize MCP servers: %s", exc)
            servers = []

        for index, server in enumerate(servers):
            if hasattr(server, "model_dump"):
                server_data = server.model_dump(by_alias=True)
            elif hasattr(server, "dict"):
                server_data = server.dict()
            else:
                server_data = {}

            server_id = resolve_mcp_server_id(server, fallback=f"mcp_server_{index}")
            tools = []
            try:
                server_tools = await server.list_tools()
                for tool in server_tools or []:
                    tool_name = getattr(tool, "name", None)
                    tool_description = getattr(tool, "description", None)
                    if tool_name is None and isinstance(tool, dict):
                        tool_name = tool.get("name")
                        tool_description = tool.get("description")
                    tools.append({
                        "name": build_namespaced_tool_name(server_id, tool_name or ""),
                        "description": tool_description or "",
                        "enabled": True,
                    })
            except Exception as exc:
                logger.warning(
                    "Failed to list tools for MCP server %s: %s",
                    server_data.get("id", ""),
                    exc,
                )

            mcp_servers.append({
                "id": server_id,
                "name": server_data.get("name") or getattr(server, "name", ""),
                "description": server_data.get("description") or getattr(server, "description", ""),
                "url": server_data.get("url") or "",
                "isAvailable": server_data.get("isAvailable", True),
                "enabled": server_data.get("enabled", True),
                "tools": tools,
            })
        
        res = json.dumps({
            "models": models,
            "builtinTools": [],  # No builtin tools for now
            "mcpServers": mcp_servers,
        })
        self.finish(res)
