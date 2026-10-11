"""Tool package with an explicit, lazy registry import.

Importing a utility from this package must not load every optional legacy tool
dependency or start provider/application clients as a side effect.
"""

__all__ = ["TOOL_REGISTRY"]


def __getattr__(name):
    if name == "TOOL_REGISTRY":
        from tools.registry import TOOL_REGISTRY
        return TOOL_REGISTRY
    raise AttributeError(name)
