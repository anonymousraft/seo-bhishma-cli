from typing import Protocol


class ProgressCallback(Protocol):
    """Protocol for progress reporting callbacks.

    Core functions accept an optional callback matching this signature.
    The CLI layer bridges this to Rich progress bars; MCP/agents ignore it.
    """

    def __call__(self, current: int, total: int, message: str = "") -> None: ...
