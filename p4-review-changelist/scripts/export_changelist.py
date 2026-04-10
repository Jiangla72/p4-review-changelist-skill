#!/usr/bin/env python3
"""Export a Perforce changelist into review artifacts.

Produces metadata.txt, summary.txt, diff.txt, files.txt, p4-info.txt,
and optionally local-paths.txt under an output directory. These artifacts
are consumed by the p4-review-changelist skill for AI code review.
"""

from __future__ import annotations

import argparse
import ctypes
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# File-type classification
# ---------------------------------------------------------------------------

TEXT_LIKE_EXTENSIONS: set[str] = {
    ".cs", ".csproj", ".json", ".toml", ".yaml", ".yml", ".xml", ".txt",
    ".md", ".cpp", ".c", ".h", ".hpp", ".py", ".js", ".ts", ".tsx",
    ".jsx", ".ini", ".cfg", ".props", ".targets", ".sln", ".sql", ".csv",
    ".proto", ".graphql", ".lua", ".go", ".rs", ".sh", ".bat", ".ps1",
    ".cmake", ".build.cs", ".uplugin", ".uproject",
}

BINARY_LIKE_EXTENSIONS: set[str] = {
    ".dll", ".pdb", ".exe", ".lib", ".so", ".dylib", ".a",
    ".uasset", ".umap", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
    ".ico", ".pdf", ".zip", ".7z", ".rar", ".mp3", ".wav", ".bank",
    ".tga", ".exr", ".fbx", ".abc", ".ttf", ".otf", ".woff", ".woff2",
}

ARTIFACT_NAMES = [
    "metadata.txt",
    "p4-info.txt",
    "summary.txt",
    "diff.txt",
    "files.txt",
    "local-paths.txt",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class P4Result(NamedTuple):
    exit_code: int
    stdout: str
    stderr: str


class FileRecord(NamedTuple):
    depot_path: str
    action: str


class LocalFileRecord(NamedTuple):
    depot_path: str
    local_path: str
    action: str


class FileKindHint(NamedTuple):
    hint: str
    binary_like_count: int
    text_like_count: int


class PendingFallback(NamedTuple):
    diff_source: str
    diff_text: str
    warning: str
    local_file_records: list[LocalFileRecord]


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
        parent == temp_root
        and fnmatch.fnmatch(dirname, "p4-review-*")
    )


def clear_managed_artifact_files(directory: str) -> None:
    for name in ARTIFACT_NAMES:
        p = os.path.join(directory, name)
        if os.path.exists(p):
            os.remove(p)


def write_text_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


def run_p4(args: list[str], *, allow_failure: bool = False) -> P4Result:
    try:
        proc = subprocess.run(
            ["p4"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        if allow_failure:
            return P4Result(1, "", "p4 executable not found")
        raise RuntimeError("p4 executable not found")

    combined = proc.stdout.rstrip() + ("\n" + proc.stderr.rstrip() if proc.stderr.strip() else "")
    combined = combined.strip()

    if proc.returncode == 0:
        result = P4Result(0, combined, "")
    else:
        result = P4Result(proc.returncode, "", combined)

    if not allow_failure and result.exit_code != 0:
        msg = (result.stderr.strip() or result.stdout.strip())
        raise RuntimeError(f"p4 {' '.join(args)} failed.\n{msg}")

    return result


_PATCH_HUNK_RE = re.compile(r"^@@ ", re.MULTILINE)


def has_patch_hunks(content: str) -> bool:
    return bool(_PATCH_HUNK_RE.search(content))


_FILE_LINE_RE = re.compile(r"^\.\.\.\s+(//.+?)#\d+\s+(\w+)")


def get_depot_paths_from_summary(summary_text: str) -> list[str]:
    paths: list[str] = []
    for line in summary_text.splitlines():
        m = _FILE_LINE_RE.match(line)
        if m:
            paths.append(m.group(1))
    return list(dict.fromkeys(paths))


def get_file_records_from_summary(summary_text: str) -> list[FileRecord]:
    records: list[FileRecord] = []
    for line in summary_text.splitlines():
        m = _FILE_LINE_RE.match(line)
        if m:
            records.append(FileRecord(depot_path=m.group(1), action=m.group(2).lower()))
    return records


def _get_ext(path: str) -> str:
    # Handle compound extensions like ".build.cs"
    basename = os.path.basename(path)
    parts = basename.split(".")
    if len(parts) >= 3:
        compound = "." + ".".join(parts[-2:]).lower()
        if compound in TEXT_LIKE_EXTENSIONS or compound in BINARY_LIKE_EXTENSIONS:
            return compound
    _, ext = os.path.splitext(path)
    return ext.lower()


def get_file_kind_hint(depot_paths: list[str]) -> FileKindHint:
    if not depot_paths:
        return FileKindHint("unknown", 0, 0)

    binary_count = 0
    text_count = 0
    for p in depot_paths:
        ext = _get_ext(p)
        if not ext:
            continue
        if ext in BINARY_LIKE_EXTENSIONS:
            binary_count += 1
        elif ext in TEXT_LIKE_EXTENSIONS:
            text_count += 1

    if binary_count > 0 and text_count == 0 and binary_count == len(depot_paths):
        hint = "binary-only-likely"
    elif text_count > 0 and binary_count == 0 and text_count == len(depot_paths):
        hint = "text-like"
    else:
        hint = "mixed-or-unknown"

    return FileKindHint(hint, binary_count, text_count)


def is_text_like_path(path: str) -> bool:
    ext = _get_ext(path)
    return bool(ext) and ext in TEXT_LIKE_EXTENSIONS


def convert_added_file_to_unified_diff(local_path: str) -> str:
    lines: list[str] = []
    if os.path.isfile(local_path):
        lines = Path(local_path).read_text(encoding="utf-8", errors="replace").splitlines()

    diff_lines = [
        "--- /dev/null",
        f"+++ {local_path}",
        f"@@ -0,0 +1,{len(lines)} @@",
    ]
    for line in lines:
        diff_lines.append(f"+{line}")
    return "\n".join(diff_lines)


def get_local_path_from_depot_path(depot_path: str) -> str | None:
    result = run_p4(["where", depot_path], allow_failure=True)
    if result.exit_code != 0 or not result.stdout.strip():
        return None

    for line in result.stdout.splitlines():
        m = re.match(r"^\S+\s+\S+\s+(.+)$", line)
        if m:
            local_path = m.group(1).strip()
            if local_path:
                return local_path
    return None


def get_opened_file_paths(pending_change: int) -> list[str]:
    result = run_p4(["-ztag", "opened", "-c", str(pending_change)], allow_failure=True)
    if result.exit_code != 0 or not result.stdout.strip():
        return []

    paths: list[str] = []
    for line in result.stdout.splitlines():
        m = re.match(r"^\.\.\. path (.+)$", line)
        if m:
            candidate = m.group(1).strip()
            if candidate:
                paths.append(candidate)
    return list(dict.fromkeys(paths))


def get_pending_patch_fallback(
    pending_change: int, summary_text: str
) -> PendingFallback:
    local_file_records: list[LocalFileRecord] = []
    paths = get_opened_file_paths(pending_change)
    for p in paths:
        local_file_records.append(LocalFileRecord(depot_path="", local_path=p, action="unknown"))

    path_source = "opened"
    if not local_file_records:
        for rec in get_file_records_from_summary(summary_text):
            local_path = get_local_path_from_depot_path(rec.depot_path)
            if local_path:
                local_file_records.append(
                    LocalFileRecord(depot_path=rec.depot_path, local_path=local_path, action=rec.action)
                )
        path_source = "summary-where"

    if not local_file_records:
        return PendingFallback(
            diff_source="missing",
            diff_text="",
            warning="No local file paths were returned by 'p4 opened -ztag' or resolved from summary depot paths.",
            local_file_records=[],
        )

    chunks: list[str] = []
    failures: list[str] = []

    for rec in local_file_records:
        if not os.path.exists(rec.local_path):
            failures.append(f"Missing local file: {rec.local_path}")
            continue

        if rec.action == "add":
            if is_text_like_path(rec.local_path):
                chunks.append(convert_added_file_to_unified_diff(rec.local_path).rstrip())
                continue
            failures.append(f"Added file requires direct binary inspection: {rec.local_path}")
            continue

        file_diff = run_p4(["diff", "-du", rec.local_path], allow_failure=True)
        if file_diff.exit_code != 0:
            failures.append(f"p4 diff failed for: {rec.local_path}")
            continue

        if file_diff.stdout.strip():
            chunks.append(file_diff.stdout.rstrip())

    diff_text = "\n\n".join(chunks).strip()
    warning = " | ".join(failures) if failures else ""

    if has_patch_hunks(diff_text):
        diff_source = "pending-opened" if path_source == "opened" else "pending-where"
        return PendingFallback(diff_source, diff_text, warning, local_file_records)

    if not warning:
        warning = "No patch hunks were produced for the pending changelist."
    return PendingFallback("missing", diff_text, warning, local_file_records)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a Perforce changelist for review.")
    parser.add_argument("--change", type=int, required=True, help="Changelist number")
    parser.add_argument("--output-dir", default=None, help="Output directory (defaults to temp)")
    parser.add_argument("--shelved", action="store_true", help="Treat as shelved changelist")
    args = parser.parse_args()

    change: int = args.change
    output_dir: str = args.output_dir or os.path.join(tempfile.gettempdir(), f"p4-review-{change}")
    shelved: bool = args.shelved

    auto_cleanup_recommended = is_managed_temp_export_dir(output_dir)

    os.makedirs(output_dir, exist_ok=True)
    clear_managed_artifact_files(output_dir)

    # -- p4 info --
    info_result = run_p4(["info"], allow_failure=True)
    info_path = os.path.join(output_dir, "p4-info.txt")
    write_text_file(info_path, "\n".join([
        "Command: p4 info",
        f"ExitCode: {info_result.exit_code}",
        "",
        info_result.stdout.rstrip(),
        info_result.stderr.rstrip(),
    ]))

    if info_result.exit_code != 0:
        print(
            f"Perforce environment check failed.\n"
            f"Saved diagnostics to: {info_path}\n"
            f"Common fixes:\n"
            f"- run from a workspace directory that contains P4CONFIG\n"
            f"- set P4PORT, P4USER, and P4CLIENT\n"
            f"- run p4 login if your session expired",
            file=sys.stderr,
        )
        sys.exit(1)

    # -- p4 describe --
    describe_args = ["describe"]
    if shelved:
        describe_args.append("-S")

    summary_result = run_p4(describe_args + ["-s", str(change)])
    summary_path = os.path.join(output_dir, "summary.txt")
    write_text_file(summary_path, summary_result.stdout)

    diff_result = run_p4(describe_args + ["-du", str(change)])
    diff_path = os.path.join(output_dir, "diff.txt")
    write_text_file(diff_path, diff_result.stdout)

    # -- files.txt --
    file_lines = [line for line in summary_result.stdout.splitlines() if line.startswith("... ")]
    files_path = os.path.join(output_dir, "files.txt")
    if file_lines:
        write_text_file(files_path, "\n".join(file_lines))

    # -- file kind analysis --
    depot_paths = get_depot_paths_from_summary(summary_result.stdout)
    file_kind = get_file_kind_hint(depot_paths)
    local_paths_path = os.path.join(output_dir, "local-paths.txt")
    local_path_lines: list[str] = []

    is_pending = "*pending*" in summary_result.stdout
    diff_source = "describe"
    diff_warning = ""
    final_diff_text = diff_result.stdout

    # -- pending fallback --
    if not shelved and is_pending and not has_patch_hunks(diff_result.stdout):
        fallback = get_pending_patch_fallback(change, summary_result.stdout)
        if fallback.diff_text.strip():
            final_diff_text = fallback.diff_text
            write_text_file(diff_path, final_diff_text)

        diff_source = fallback.diff_source
        diff_warning = fallback.warning

        for rec in fallback.local_file_records:
            if rec.local_path:
                local_path_lines.append(f"{rec.action}\t{rec.depot_path}\t{rec.local_path}")

    if local_path_lines:
        write_text_file(local_paths_path, "\n".join(local_path_lines))

    # -- metadata.txt --
    metadata_path = os.path.join(output_dir, "metadata.txt")
    file_count = len(file_lines)
    has_patch = has_patch_hunks(final_diff_text)
    has_local_map = len(local_path_lines) > 0
    write_text_file(metadata_path, "\n".join([
        f"Change={change}",
        f"IsPending={is_pending}",
        f"IsShelved={shelved}",
        f"DiffSource={diff_source}",
        f"HasPatchHunks={has_patch}",
        f"FileCount={file_count}",
        f"BinaryLikeFileCount={file_kind.binary_like_count}",
        f"TextLikeFileCount={file_kind.text_like_count}",
        f"FileKindHint={file_kind.hint}",
        f"AutoCleanupRecommended={auto_cleanup_recommended}",
        f"HasLocalPathMap={has_local_map}",
        f"DiffWarning={diff_warning}",
    ]))

    # -- output --
    print(f"OutputDir={output_dir}")
    print(f"Metadata={metadata_path}")
    print(f"Summary={summary_path}")
    print(f"Diff={diff_path}")
    if local_path_lines:
        print(f"LocalPaths={local_paths_path}")
    print(f"Info={info_path}")


if __name__ == "__main__":
    main()
