from __future__ import annotations

import sys
from typing import Any

try:
    from rich.console import Console
    from rich.theme import Theme

    _theme = Theme({
        "success": "green bold",
        "error": "red bold",
        "info": "cyan",
        "warning": "yellow",
        "muted": "dim",
    })

    _console = Console(theme=_theme, safe_box=True, emoji=False)
    console = _console
    _rich_available = True
except ImportError:
    _rich_available = False
    console = None


def safe_print(*args: Any, **kwargs: Any) -> None:
    if _rich_available:
        try:
            _console.print(*args, **kwargs)
            return
        except (UnicodeEncodeError, Exception):
            pass

    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    text = sep.join(str(arg) for arg in args) + end

    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except (UnicodeEncodeError, Exception):
        cleaned = text.encode(sys.stdout.encoding or "ascii", "replace").decode(
            sys.stdout.encoding or "ascii", "replace"
        )
        sys.stdout.write(cleaned)
        sys.stdout.flush()


def get_console():
    if _rich_available:
        return _console
    return None
