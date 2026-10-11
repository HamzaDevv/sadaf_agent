"""Minimal injected text path. These fakes do not implement durable memory or M2."""

from dataclasses import dataclass, field
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str


class TextProvider(Protocol):
    def reply(self, text: str, history: Sequence[Turn]) -> str: ...


class TurnStore(Protocol):
    def history(self) -> Sequence[Turn]: ...
    def append_exchange(self, user: Turn, assistant: Turn) -> None: ...


class FakeTextProvider:
    def reply(self, text: str, history: Sequence[Turn]) -> str:
        return f"[offline fake; turn {len(history) // 2 + 1}] Received: {text}"


@dataclass
class InMemoryTurnStore:
    _turns: list[Turn] = field(default_factory=list)

    def history(self) -> Sequence[Turn]:
        return tuple(self._turns)

    def append_exchange(self, user: Turn, assistant: Turn) -> None:
        self._turns.extend((user, assistant))


@dataclass
class TextSession:
    provider: TextProvider
    store: TurnStore

    def respond(self, text: str) -> str:
        if not text.strip():
            raise ValueError("Text must be nonempty")
        result = self.provider.reply(text, self.store.history())
        if not isinstance(result, str) or not result.strip():
            raise ValueError("Provider returned no text")
        self.store.append_exchange(Turn("user", text), Turn("assistant", result))
        return result
