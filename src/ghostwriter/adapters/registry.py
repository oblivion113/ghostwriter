from __future__ import annotations

from collections.abc import Iterable

from ghostwriter.model import Draft

from .base import InjectionAdapter, InjectionRequest, InjectionTarget
from .pi import PiAdapter


class AdapterRegistry:
    def __init__(self, adapters: Iterable[InjectionAdapter] | None = None) -> None:
        configured = list(adapters) if adapters is not None else [PiAdapter()]
        self._adapters = {adapter.id: adapter for adapter in configured}

    def discover_targets(self) -> list[InjectionTarget]:
        targets: list[InjectionTarget] = []
        for adapter in self._adapters.values():
            targets.extend(adapter.discover_targets())
        return targets

    def serialize(self, draft: Draft, target: InjectionTarget) -> str:
        return self._adapters[target.adapter_id].serialize(draft, target)

    async def inject(
        self,
        target: InjectionTarget,
        request: InjectionRequest,
    ) -> dict[str, object]:
        return await self._adapters[target.adapter_id].inject(target, request)
