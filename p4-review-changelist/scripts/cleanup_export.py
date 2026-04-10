#!/usr/bin/env python3
"""Clean up temporary artifacts produced by export_changelist.py.

Only deletes directories under the system temp root whose name matches
the ``p4-review-*`` pattern, refusing to touch anything else.
"""

from __future__ import annotations

import argparse
import ctypes
import fnmatch
import os
import shutil
import sys
import tempfile


def _resolve_long_path(path: str) -> str:
    """Resolve 8.3 short paths (e.g. JIANGY~1) to their full long form on Windows."""
    resolved = os.path.abspath(path)
    if sys.platform == "win32":
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetLongPathNameW(resolved, buf, len(buf)):
            resolved = buf.value
    return resolved


def is_managed_temp_export_dir(path: str) -> bool:
    resolved = os.path.normcase(_resolve_long_path(path))
    temp_root = os.path.normcase(_resolve_long_path(tempfile.gettempdir()))
    parent = os.path.dirname(resolved)
    dirname = os.path.basename(resolved)
    return (
        os.path.normcase(parent) == temp_root
        and fnmatch.fnmatch(dirname, "p4-review-*")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up p4-review export artifacts.")
    parser.add_argument("--output-dir", required=True, help="Export directory to remove")
    args = parser.parse_args()

    resolved = os.path.abspath(args.output_dir)

    if not os.path.exists(resolved):
        print(f"Skipped=missing:{resolved}")
        return

    if not is_managed_temp_export_dir(resolved):
        print(
            f"Refusing to delete directory outside managed temp scope: {resolved}",
            file=sys.stderr,
        )
        sys.exit(1)

    shutil.rmtree(resolved)
    print(f"Removed={resolved}")


if __name__ == "__main__":
    main()
