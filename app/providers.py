from dataclasses import dataclass
from typing import Protocol


class Provider(Protocol):
    name: str

    async def query(self, text: str) -> dict[str, object]: ...


@dataclass
class DemoAnalyticsProvider:
    name: str = "analytics"

    async def query(self, text: str) -> dict[str, object]:
        return {"provider": self.name, "query": text, "sessions": 128, "conversion_rate": 0.034}


class ProviderRegistry:
    def __init__(self, providers: list[Provider]) -> None:
        self._providers = {provider.name: provider for provider in providers}

    async def execute(self, name: str, query: str) -> dict[str, object]:
        provider = self._providers.get(name)
        if provider is None:
            raise KeyError(name)
        return await provider.query(query)
