import pytest

from sadaf.runtime import FakeTextProvider, InMemoryTurnStore, TextSession, Turn


def test_injected_provider_gets_exact_prior_turns():
    class RecordingProvider:
        def __init__(self):
            self.calls = []

        def reply(self, text, history):
            self.calls.append((text, tuple(history)))
            return "Synthetic reply"

    provider = RecordingProvider()
    store = InMemoryTurnStore()
    session = TextSession(provider, store)
    assert session.respond("Synthetic first turn") == "Synthetic reply"
    session.respond("Synthetic second turn")
    assert provider.calls[0][1] == ()
    assert provider.calls[1][1] == (Turn("user", "Synthetic first turn"),
                                    Turn("assistant", "Synthetic reply"))
    assert len(store.history()) == 4


def test_sessions_do_not_share_ephemeral_history():
    first = TextSession(FakeTextProvider(), InMemoryTurnStore())
    second = TextSession(FakeTextProvider(), InMemoryTurnStore())
    first.respond("Fixture")
    assert "turn 2" in first.respond("Fixture")
    assert "turn 1" in second.respond("Fixture")


@pytest.mark.parametrize("failure", ["raise", "", None])
def test_provider_failure_does_not_record_an_exchange(failure):
    class FailingProvider:
        def reply(self, text, history):
            if failure == "raise":
                raise RuntimeError("fixture failure")
            return failure

    store = InMemoryTurnStore()
    with pytest.raises((RuntimeError, ValueError)):
        TextSession(FailingProvider(), store).respond("Fixture")
    assert store.history() == ()


def test_empty_input_does_not_invoke_provider():
    class ForbiddenProvider:
        def reply(self, text, history):
            raise AssertionError("Must validate first")

    with pytest.raises(ValueError, match="nonempty"):
        TextSession(ForbiddenProvider(), InMemoryTurnStore()).respond("  ")
