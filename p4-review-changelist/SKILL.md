---
name: p4-review-changelist
description: Review a Perforce changelist by changelist number, including pending, submitted, or shelved changes, and assess whether the edits are correct, risky, or incomplete. Use when a user gives a P4 changelist number and wants a quick first-pass verdict first, then optional deeper review, regression analysis, or fix guidance on that specific diff instead of a whole-repository review.
---

# P4 Review Changelist

## Overview

Review a changelist from the changelist number first, then deepen into local repository context only where it makes the review sharper. The default behavior is a two-stage review: give a short first-pass verdict quickly, then let the user decide whether to dig deeper.

## Quick Start

1. Work from the user's workspace root if one is known. Perforce settings may come from `P4CONFIG`, so the current directory matters.
2. Run `scripts/export_changelist.py` to validate the Perforce environment and export the changelist summary, file list, metadata, and best available unified diff.
3. Read `references/review-checklist.md` before writing the review.
4. Start with a quick triage based on `metadata.txt`, `summary.txt`, `files.txt`, and `diff.txt`.
5. Return a short first-pass result before deciding whether deeper context reads are worth the extra time.
6. After the review is finished, clean temporary exported artifacts unless the user asked to keep them.

## Workflow

> In all command examples below, `<skill-root>` refers to the directory
> containing this SKILL.md file.

### 1. Collect the changelist safely

Prefer:

```
python "<skill-root>/scripts/export_changelist.py" --change 123456
```

Use `--shelved` when the user explicitly says the changelist is shelved or standard `p4 describe` does not target the requested review content.

For pending changelists, the helper script may fall back from `p4 describe -du` to per-file `p4 diff -du` so that the review still has real patch hunks instead of only the summary header. If `p4 opened -ztag` does not provide local paths, resolve depot paths from the summary via `p4 where` and continue the review instead of stopping early.

If the script fails on `p4 info`, stop and explain the exact environment issue. Common fixes:

- run from the repo or workspace directory that contains `P4CONFIG`
- set `P4PORT`, `P4USER`, or `P4CLIENT`
- run `p4 login` if authentication expired

### 2. Read the exported artifacts

The script writes:

- `metadata.txt`
- `p4-info.txt`
- `summary.txt`
- `diff.txt`
- `files.txt` if file extraction succeeds
- `local-paths.txt` when the helper resolves depot paths to local files for pending changelists

`local-paths.txt` uses tab-separated columns: `{action}\t{depot_path}\t{local_path}`.
- `action`: the Perforce action (`add`, `edit`, `delete`, `unknown`).
- `depot_path`: the depot path (may be empty if the path was resolved from `p4 opened` rather than the summary).
- `local_path`: the absolute local filesystem path.

Start with `metadata.txt` and `summary.txt` to understand what kind of changelist this is, then use `files.txt` and `diff.txt` for the actual review. If `local-paths.txt` exists, use it to open added files or verify local context during pending reviews.

Key metadata fields:

- `DiffSource`: where the patch came from (`describe`, `pending-opened`, `pending-where`, or `missing`)
- `IsPending`: whether the changelist is still open
- `FileCount`: rough review scope
- `FileKindHint`: whether the touched files look mostly text, mixed, or likely binary-only
- `AutoCleanupRecommended`: whether the export directory is a temp artifact that should normally be deleted after the review
- `HasLocalPathMap`: whether the helper resolved local file paths for the pending changelist
- `DiffWarning`: limitation to mention in the review if patch coverage is incomplete

### 3. Large CL triage

Before proceeding to the full review, check `FileCount` in `metadata.txt`:

- **FileCount <= 20**: proceed normally with full review.
- **FileCount 21-50**: review all files, but group findings by subsystem or directory prefix. Summarize low-risk files in bulk rather than listing each one.
- **FileCount > 50**: inform the user of the scope and ask whether to:
  1. Review the full CL with a summary-level pass (high-level findings only, no line-by-line comments).
  2. Focus on a user-specified subset of files or directories.
  3. Focus only on files matching `FileKindHint=text-like` and skip binary assets.

When the user has not specified a preference and FileCount > 50, default to option 1 (summary-level pass) and mention the other options as follow-ups.

### 4. Deepen context selectively

Do not automatically do a long investigation. First produce a quick result from the exported artifacts alone.

Only open local files when one of these is true:

- API or schema changes and their callers
- serialization, config, and asset references
- state transitions, threading, lifetime, and error paths
- tests that should have changed but did not
- the first-pass verdict is `needs deeper check` or `likely issue`

If the changelist mentions files that are not present in the local workspace, review the diff directly and call out the missing context as a limitation.

### 5. Produce the first-pass result

The first reply after receiving a changelist number should be short and decision-friendly. Mirror the user's language. Prefer this structure:

- `Initial verdict`: `looks okay`, `likely issue`, or `needs deeper check`
- `Top findings`: 0-3 concise points, highest risk first
- `Confidence`: `high`, `medium`, or `low`, plus why
- `Next options`: short numbered options so the user can decide what to do next

Keep this first-pass response compact. The user should be able to decide in a few seconds whether to stop, ask for deeper review, or request a fix suggestion.

If the changelist appears to be binary-only or otherwise non-readable, say that directly. Do not fake a code review when the contents cannot be inspected. Prefer wording like:

- `Initial verdict: needs deeper check`
- `Top findings: this changelist looks binary-only / non-readable from the current artifacts, so I cannot verify the implementation itself`
- `Confidence: low, because there are no readable patch hunks`

Then suggest practical next steps such as asking for the source changelist, a text diff, or the related source files.

### 6. Deeper follow-up only on demand

If the user asks for more after the first pass, continue with a fuller code-review style response:

- findings first, ordered by severity
- include file references when local files are available
- explain impact and likely failure mode
- mention missing tests or validation
- summarize blind spots if review coverage is incomplete

### 7. Clean exported artifacts

If the export directory was created under the system temp directory and the user did not ask to keep it, clean it after the review is complete.

Prefer:

```
python "<skill-root>/scripts/cleanup_export.py" --output-dir "<dir-from-export>"
```

Cleanup rules:

- clean only after the review result has been delivered
- keep artifacts if the user asks to inspect them or if you still need them for a follow-up step
- mention briefly when cleanup was skipped on purpose
- never delete arbitrary user paths; only delete export directories created for this workflow

## Review Heuristics

Read `references/review-checklist.md` when you need the fuller checklist. Pay extra attention to depot-specific risks:

- accidental workspace-only files or generated files
- rename or delete mismatches and stale references
- requirement-finish cleanup that was forgotten, such as obsolete files that should have been deleted
- config or default changes that affect unrelated users
- partial refactors where interface and implementation diverge
- changelists that modify assets or build files without corresponding code updates

## Fallback

If `p4` is unavailable or the environment cannot connect, do not guess. Ask the user for one of:

- the output of `p4 describe -du <cl>`
- a pasted diff
- the touched file list plus the relevant patch

If `diff.txt` has no real patch hunks and no pending fallback succeeded, still give a limited first-pass result from the summary and file list, but explicitly mark confidence as low.
If `metadata.txt` says `FileKindHint=binary-only-likely`, explicitly tell the user that the changelist contents are not directly reviewable from this workspace and that any verdict is only about packaging risk, not implementation correctness.
If `metadata.txt` says `AutoCleanupRecommended=true`, remember to remove the temp export directory when the review is done unless the user wants to keep it.
If `metadata.txt` says `FileKindHint=text-like` but `DiffSource=missing`, treat that as a recovery path instead of a stopping point: use `local-paths.txt` or resolve depot paths with `p4 where` before concluding.

