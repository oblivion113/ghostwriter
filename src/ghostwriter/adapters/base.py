from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ghostwriter.model import Draft


@dataclass(frozen=True, slots=True)
class InjectionTarget:
    adapter_id: str
    target_id: str
    label: str
    cwd: Path
    metadata: dict[str, Any]

    @property
    def selection_id(self) -> str:
        return f"{self.adapter_id}:{self.target_id}"


@dataclass(frozen=True, slots=True)
class InjectionRequest:
    text: str
    draft_id: str
    revision: int


class InjectionAdapter(Protocol):
    id: str
    display_name: str

    def discover_targets(self) -> list[InjectionTarget]: ...

    def serialize(self, draft: Draft, target: InjectionTarget) -> str: ...

    async def inject(
        self,
        target: InjectionTarget,
        request: InjectionRequest,
    ) -> dict[str, Any]: ...
