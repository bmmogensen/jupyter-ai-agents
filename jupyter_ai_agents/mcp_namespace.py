# Copyright (c) 2024-2025 Datalayer, Inc.
#
# BSD 3-Clause License

"""Helpers for MCP tool namespacing and toolset wrapping."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from pydantic_ai._run_context import AgentDepsT, RunContext
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai.toolsets.wrapper import WrapperToolset


def resolve_mcp_server_id(server: Any, fallback: str | None = None) -> str:
    """Resolve a stable identifier for an MCP server."""
    server_id = getattr(server, "id", None)
    if not server_id:
        server_id = getattr(server, "name", None)
    if not server_id:
        server_id = fallback
    return server_id or ""


def build_namespaced_tool_name(server_id: str, tool_name: str) -> str:
    """Build a stable namespaced tool name for UI/selection."""
    if not server_id:
        return tool_name
    return f"{server_id}.{tool_name}"


@dataclass
class NamespacedToolset(WrapperToolset[AgentDepsT]):
    """A toolset that namespaces tool names using a dot separator."""

    namespace: str
    separator: str = "."

    @property
    def tool_name_conflict_hint(self) -> str:
        return "Change the namespace to avoid name conflicts."

    async def get_tools(self, ctx: RunContext[AgentDepsT]) -> dict[str, ToolsetTool[AgentDepsT]]:
        return {
            new_name: replace(
                tool,
                toolset=self,
                tool_def=replace(tool.tool_def, name=new_name),
            )
            for name, tool in (await super().get_tools(ctx)).items()
            if (new_name := f"{self.namespace}{self.separator}{name}")
        }

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[AgentDepsT], tool: ToolsetTool[AgentDepsT]
    ) -> Any:
        prefix = f"{self.namespace}{self.separator}"
        original_name = name[len(prefix):] if name.startswith(prefix) else name
        ctx = replace(ctx, tool_name=original_name)
        tool = replace(tool, tool_def=replace(tool.tool_def, name=original_name))
        return await super().call_tool(original_name, tool_args, ctx, tool)
