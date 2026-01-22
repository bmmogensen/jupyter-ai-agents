# Copyright (c) 2024-2025 Datalayer, Inc.
#
# BSD 3-Clause License

"""Config handler."""

import json
import logging
import os

import tornado

from jupyter_server.base.handlers import APIHandler
from jupyter_server.extension.handler import ExtensionHandlerMixin
from jupyter_ai_agents.__version__ import __version__


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
        
        server = self.settings.get("mcp_server")

        tools = []
        is_available = False
        server_id = "active-mcp"
        server_name = "Active MCP Server"
        server_url = ""

        if server:
            server_id = getattr(server, "id", None) or getattr(server, "name", None) or server_id
            server_name = getattr(server, "name", None) or server_id
            server_url = getattr(server, "url", "") or ""

            try:
                async with server:
                    tools_list = await server.list_tools()

                for tool in tools_list or []:
                    tools.append(
                        {
                            "name": getattr(tool, "name", "")
                            or (tool.get("name", "") if isinstance(tool, dict) else ""),
                            "description": getattr(tool, "description", "")
                            or (tool.get("description", "") if isinstance(tool, dict) else ""),
                            "enabled": True,
                        }
                    )
                is_available = len(tools) > 0
            except Exception as e:
                logger.warning(f"Failed to list tools from active MCP server: {e}")
                tools = []
                is_available = False

        mcp_servers = [
            {
                "id": server_id,
                "name": server_name,
                "description": "Tools from the selected MCP server (agent-runtimes).",
                "url": server_url,
                "isAvailable": is_available,
                "enabled": is_available,
                "tools": tools,
            }
        ]

        res = json.dumps({
            "models": models,
            "builtinTools": [],  # No builtin tools for now
            "mcpServers": mcp_servers,
        })
        self.finish(res)
