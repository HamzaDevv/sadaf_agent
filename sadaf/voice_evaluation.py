"""Opt-in evaluation hook for a separately supplied live/microphone adapter.

No live adapter, capture device, credentials, or provider is constructed here.
"""
from dataclasses import dataclass
import math
import re
from typing import Awaitable, Callable


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    transcript: str
    recognition_targets: tuple[str, ...]


CASES = (
    EvaluationCase('names_numbers', 'Ask Sadaf about Nila, ticket 407 and build 12.', ('Nila','407','12')),
    EvaluationCase('language_switch', 'Reply in English. Ab Hindi mein bolo. Then English again.', ('Hindi','English')),
    EvaluationCase('interruption', 'Explain the fixture task. Stop midway, then resume only verified results.', ()),
)


@dataclass(frozen=True)
class Observation:
    recognized_text: str
    useful_answer_seconds: float
    interruption_recovery_seconds: float | None
    connected_seconds: float
    voice_cost: float | None  # Actual billed value or caller's declared estimate.
    backend_cost: float | None
    cost_basis: str = 'unavailable'

    def __post_init__(self):
        for value in (self.useful_answer_seconds, self.interruption_recovery_seconds,
                      self.connected_seconds, self.voice_cost, self.backend_cost):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError('Measurements must be finite and nonnegative')


async def evaluate(runner: Callable[[str, EvaluationCase], Awaitable[Observation]], *,
                   candidates: tuple[str, ...], confirm_live: bool = False,
                   microphone: bool = False, confirm_microphone: bool = False) -> tuple[dict, ...]:
    """Run identical synthetic cases for each candidate after explicit opt-in.

    The host supplies a runner that measures from final input to useful playback,
    and from interruption to recovered playback. It must supply measured costs
    or a labeled estimate; this harness never infers a winner or live access.
    """
    if not confirm_live: raise ValueError('Provider evaluation requires confirm_live=True')
    if microphone and not confirm_microphone:
        raise ValueError('Microphone evaluation requires confirm_microphone=True')
    if not candidates or len(set(candidates)) != len(candidates):
        raise ValueError('Provide distinct explicit candidate model IDs')
    rows = []
    for candidate in candidates:
        for case in CASES:
            observed = await runner(candidate,case)
            recognized = observed.recognized_text.casefold()
            rows.append({'candidate':candidate,'case':case.id,'observation':observed,
                'recognition_hits':tuple(t for t in case.recognition_targets if re.search(r'\b' + re.escape(t.casefold()) + r'\b', recognized)),
                'recognition_targets':case.recognition_targets})
    return tuple(rows)
