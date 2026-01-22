# Copyright (c) 2024-2025 Datalayer, Inc.
#
# BSD 3-Clause License

"""Helpers for creating MCP server toolsets."""

import logging
from urllib.parse import urljoin

from pydantic_ai.mcp import MCPServerStreamableHTTP

logger = logging.getLogger(__name__)


def create_mcp_server(
    base_url: str,
    token: str | None = None,
) -> MCPServerStreamableHTTP:
    """
    Create an MCP server connection to the local jupyter-mcp-server.

    The MCP server runs on the same Jupyter server and exposes tools via
    the MCP protocol over HTTP at the /mcp endpoint.

    Args:
        base_url: Server base URL (e.g., "http://localhost:8888")
        token: Authentication token

    Returns:
        MCPServerStreamableHTTP instance connected to the MCP server
    """
    # Construct the MCP endpoint URL
    mcp_url = urljoin(base_url.rstrip("/") + "/", "mcp")

    logger.info(f"Creating MCP server connection to {mcp_url}")

    # Create MCP server with authentication headers if token is provided
    if token:
        headers = {"Authorization": f"token {token}"}
        server = MCPServerStreamableHTTP(mcp_url, headers=headers)
        logger.info("MCP server connection created successfully with authentication")
    else:
        server = MCPServerStreamableHTTP(mcp_url)
        logger.info("MCP server connection created successfully without authentication")

    return server
