# Copyright (c) 2024-2025 Datalayer, Inc.
#
# BSD 3-Clause License

"""Helpers for MCP tool namespacing and toolset wrapping."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import re
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


logger = logging.getLogger(__name__)
_ALLOWED_TOOL_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


def sanitize_tool_component(value: str, fallback: str = "tool") -> str:
    """Sanitize a tool name component to match provider constraints."""
    cleaned = _ALLOWED_TOOL_NAME_RE.sub("_", value or "")
    cleaned = cleaned.strip("_-")
    if not cleaned:
        cleaned = fallback
    return cleaned[:128]


def build_namespaced_tool_name(server_id: str, tool_name: str) -> str:
    """Build a stable namespaced tool name for UI/selection."""
    safe_server = sanitize_tool_component(server_id, fallback="mcp")
    safe_tool = sanitize_tool_component(tool_name)
    if not safe_server:
        return safe_tool
    return f"{safe_server}_{safe_tool}"


@dataclass
class NamespacedToolset(WrapperToolset[AgentDepsT]):
    """A toolset that namespaces tool names using a provider-safe separator."""

    namespace: str
    separator: str = "_"
    _name_map: dict[str, str] = None

    @property
    def tool_name_conflict_hint(self) -> str:
        return "Change the namespace to avoid name conflicts."

    async def get_tools(self, ctx: RunContext[AgentDepsT]) -> dict[str, ToolsetTool[AgentDepsT]]:
        self._name_map = {}
        safe_namespace = sanitize_tool_component(self.namespace, fallback="mcp")
        tool_map: dict[str, ToolsetTool[AgentDepsT]] = {}
        for name, tool in (await super().get_tools(ctx)).items():
            safe_name = sanitize_tool_component(name)
            new_name = (
                f"{safe_namespace}{self.separator}{safe_name}"
                if safe_namespace
                else safe_name
            )
            base_name = new_name
            suffix = 1
            while new_name in tool_map:
                suffix += 1
                suffix_str = f"{self.separator}{suffix}"
                new_name = f"{base_name[: 128 - len(suffix_str)]}{suffix_str}"
            self._name_map[new_name] = name
            tool_map[new_name] = replace(
                tool,
                toolset=self,
                tool_def=replace(tool.tool_def, name=new_name),
            )
        return tool_map

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[AgentDepsT], tool: ToolsetTool[AgentDepsT]
    ) -> Any:
        original_name = None
        if self._name_map:
            original_name = self._name_map.get(name)
        if original_name is None:
            prefix = f"{sanitize_tool_component(self.namespace, fallback='mcp')}{self.separator}"
            original_name = name[len(prefix):] if name.startswith(prefix) else name
        ctx = replace(ctx, tool_name=original_name)
        tool = replace(tool, tool_def=replace(tool.tool_def, name=original_name))
        try:
            return await super().call_tool(original_name, tool_args, ctx, tool)
        except Exception as exc:
            logger.exception(
                "MCP tool call failed: tool=%s namespaced=%s args=%s",
                original_name,
                name,
                tool_args,
            )
            raise RuntimeError(
                f"MCP tool call failed for {original_name}: {type(exc).__name__}: {exc}"
            ) from exc
