#!/usr/bin/env python3
"""Scan repository files for common secret patterns before commit."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_EXCLUDES = {
    '.git',
    '__pycache__',
    '.idea',
    '.vs',
    'node_modules',
}

PATTERNS = [
    ('GitHub token', re.compile(r'\bgho_[A-Za-z0-9_]+\b')),
    ('GitHub PAT', re.compile(r'\bgithub_pat_[A-Za-z0-9_]+\b')),
    ('AWS access key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('Private key', re.compile(r'BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY')),
    ('Authorization header', re.compile(r'authorization\s*:\s*\S+', re.IGNORECASE)),
    ('Password assignment', re.compile(r'\b(password|passwd)\b\s*[:=]\s*\S+', re.IGNORECASE)),
    ('Secret assignment', re.compile(r'\b(secret|client_secret)\b\s*[:=]\s*\S+', re.IGNORECASE)),
    ('Token assignment', re.compile(r'\b(access_token|refresh_token|api_key|apikey|token)\b\s*[:=]\s*\S+', re.IGNORECASE)),
]

TEXT_SUFFIXES = {
    '.md', '.txt', '.py', '.ps1', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.cs', '.csproj', '.props', '.targets', '.xml'
}


def run_git(args: list[str], cwd: Path) -> list[str]:
    proc = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    try:
        with path.open('rb') as f:
            chunk = f.read(1024)
        return b'\0' not in chunk
    except OSError:
        return False


def iter_candidate_files(repo_root: Path, staged_only: bool) -> list[Path]:
    if staged_only:
        files = run_git(['diff', '--cached', '--name-only', '--diff-filter=ACMR'], repo_root)
        return [repo_root / rel for rel in files]

    result: list[Path] = []
    for path in repo_root.rglob('*'):
        if not path.is_file():
            continue
        if any(part in DEFAULT_EXCLUDES for part in path.parts):
            continue
        result.append(path)
    return result


def scan_file(path: Path, repo_root: Path) -> list[str]:
    if not path.exists() or not path.is_file() or not is_probably_text(path):
        return []

    try:
        content = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []

    hits: list[str] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        for label, pattern in PATTERNS:
            if pattern.search(line):
                hits.append(f'{path.relative_to(repo_root)}:{line_no}: {label}: {stripped}')
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description='Scan repository files for common secret patterns.')
    parser.add_argument('--repo', default='.', help='Repository root to scan')
    parser.add_argument('--staged-only', action='store_true', help='Scan only staged files')
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    findings: list[str] = []

    for path in iter_candidate_files(repo_root, args.staged_only):
        if any(part in DEFAULT_EXCLUDES for part in path.parts):
            continue
        findings.extend(scan_file(path, repo_root))

    if findings:
        print('Potential secrets detected:')
        for item in findings:
            print(f'  {item}')
        print('\nCommit blocked. Remove or redact the values, then try again.')
        return 1

    print('Security check passed: no obvious secrets found.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
