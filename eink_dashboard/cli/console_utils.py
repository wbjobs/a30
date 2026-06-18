from __future__ import annotations

import sys

from rich.console import Console
from rich.theme import Theme


_theme = Theme({
    "success": "green bold",
    "error": "red bold",
    "info": "cyan",
    "warning": "yellow",
    "muted": "dim",
})


def _get_console() -> Console:
    try:
        return Console(theme=_theme, safe_box=True, emoji=False)
    except Exception:
        return Console(theme=_theme, force_terminal=False, safe_box=True, emoji=False)


console = _get_console()


def safe_print(*args, **kwargs) -> None:
    try:
        console.print(*args, **kwargs)
    except UnicodeEncodeError:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        text = sep.join(str(arg) for arg in args) + end
        cleaned = text.encode(sys.stdout.encoding or "ascii", "replace").decode(
            sys.stdout.encoding or "ascii", "replace"
        )
        sys.stdout.write(cleaned)
        sys.stdout.flush()
