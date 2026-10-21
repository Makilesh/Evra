"""Console output that never crashes on text the console cannot encode.

A redirected Windows console uses cp1252; transcripts and notes can hold any character (arrows,
names, other scripts). Unencodable characters print as "?" instead of raising.
"""

from __future__ import annotations

import io
import sys


def safe_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="replace")
