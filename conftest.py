"""
conftest.py — Sadaf test session configuration

Notes on aclose warning:
  The Groq SDK's httpx transport maintains a connection pool whose internal
  coroutine objects emit 'AsyncClient.aclose was never awaited' when GC'd after
  the function-scoped event loop closes. This is a library-internal cleanup
  ordering issue — pytest.ini suppresses it with a narrow filterwarning.
  Our GroqProxyImpl.close() is still called as best-effort cleanup.
"""
import asyncio
import pytest
from llm_proxy import llm_proxy


@pytest.fixture(scope="session", autouse=True)
def close_llm_proxy_on_exit():
    """
    Best-effort cleanup of AsyncGroq HTTP clients at session end.
    Uses a fresh event loop since the test's function-scoped loop is already closed.
    The filterwarning in pytest.ini handles any residual httpx pool warnings.
    """
    yield
    try:
        asyncio.run(llm_proxy.close())
    except Exception:
        pass
