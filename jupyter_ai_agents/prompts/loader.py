from __future__ import annotations

from importlib import resources
from pathlib import Path


def load_prompt_text(packaged_name: str, override_path: str | None = None) -> str:
    if override_path:
        prompt_path = Path(override_path).expanduser()
        if prompt_path.is_file():
            return prompt_path.read_text(encoding="utf-8")

    return (
        resources.files("jupyter_ai_agents.prompts")
        .joinpath(packaged_name)
        .read_text(encoding="utf-8")
    )
