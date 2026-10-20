"""Read a small configuration or rule file without hanging, and without reading it all.

A path named on a command line is the author's choice, so it can be a FIFO that never
produces data, a device, or a file far larger than any real configuration. Reading it
with ``Path.read_text`` would block the hook or fill memory.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

MAX_FILE_BYTES = 1024 * 1024
"""Largest configuration or rule file guardline reads, in bytes."""


class FileRefused(Exception):  # noqa: N818 - a refusal, not an error condition of the program
    """The path is not a small regular file. ``str(error)`` says why, and never names content."""


def read_small_file(path: str | Path, limit: int = MAX_FILE_BYTES) -> bytes:
    """Return the bytes of a regular file of at most ``limit`` bytes.

    The file is opened without blocking, so a FIFO with no writer returns at once and is
    then refused, and its type is checked on the open descriptor rather than on the path.

    Raises:
        FileRefused: the path is not a regular file, or the file is larger than ``limit``.
        OSError: the file cannot be opened or read.
    """
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise FileRefused("not a regular file")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise FileRefused(f"larger than {limit} bytes")
    return data
