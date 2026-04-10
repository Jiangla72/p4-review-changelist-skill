# P4 Changelist Review Checklist

Use this checklist to turn a raw changelist diff into a focused review.

## First-pass output

- Give a short verdict before doing deep repository reads unless the user already asked for a deep review.
- Prefer one of: `looks okay`, `likely issue`, `needs deeper check`.
- Include 0-3 top findings, a confidence level, and a brief note about any missing patch coverage.
- End with short numbered follow-up options so the user can choose the next step.
- If all visible artifacts are binary-only or unreadable, say that plainly and avoid pretending the implementation was reviewed.
- Remember whether temporary exported review artifacts should be cleaned after the response.

## Core correctness

- Verify the implementation matches the apparent intent of the changelist description and touched files.
- Look for broken control flow, inverted conditions, missing null checks, and incomplete error handling.
- Check whether added or removed parameters stay consistent across declarations, callers, serialization, and config.

## Regression risk

- Identify caller or callee changes that were only applied on one side of an interface.
- Check renamed, moved, or deleted files for stale references in build files, asset manifests, includes, or registration lists.
- When a requirement looks complete, ask whether any old files should have been removed instead of kept around.
- Watch for config and default-value changes that alter behavior outside the target feature.

## Data and state

- Inspect persistence, serialization, network payloads, and save-data compatibility.
- Check ordering-sensitive logic, lifecycle transitions, threading assumptions, and cleanup paths.
- Flag migrations or versioning changes that lack backward-compatibility handling.

## Tests and validation

- Ask whether the risky behavior in the changelist should have updated tests, assertions, or tooling.
- If no tests changed, decide whether that is acceptable or a gap worth calling out.
- Mention when the review is limited because required files are absent from the local workspace.

## Concurrency and threading

- Check whether shared state is accessed from multiple threads without proper synchronization (locks, atomics, or thread-safe containers).
- Look for lock ordering inversions, double-lock risks, or fire-and-forget async calls that silently swallow errors.
- Verify that new callbacks, delegates, or event handlers do not assume single-threaded execution when the caller may be on a different thread.
- For game engine code: check whether operations are restricted to the game thread, render thread, or a background task, and whether the changelist respects that boundary.

## Memory and resource management

- Look for allocations without corresponding cleanup (missing Dispose, Release, destructor, or GC root removal).
- Check for event subscription leaks: subscribing in initialization without unsubscribing on teardown.
- Watch for large per-frame or per-tick allocations that could cause GC pressure or frame hitches.
- In C++/UE code, verify UPROPERTY marking for any new UObject pointers and check for raw `new` without proper ownership transfer.

## Performance impact

- Identify changes to code on hot paths (tick, update, render, network serialization) and evaluate algorithmic complexity changes.
- Check for new O(n^2) or worse patterns introduced in loops over collections that may grow large.
- Look for blocking I/O, synchronous loads, or expensive string operations introduced in latency-sensitive paths.
- When a changelist modifies data structures, consider cache locality and memory layout implications.

## Perforce-specific risks

- Spot generated files, user-local settings, or accidental workspace artifacts that should not be submitted.
- Distinguish normal `describe` output from shelved reviews and use `-Shelved` when appropriate.
- Treat huge binary or asset-only changes as context-sensitive and note when correctness cannot be established from diff alone.
- For pending changelists, prefer real patch hunks over file lists. If only a summary is available, mark the review as low confidence.
- If a pending changelist is text-like but `p4 describe -du` still lacks patch hunks, recover by resolving depot paths to local paths and inspect those files before concluding.
- If the touched files are all DLL/PDB/EXE or similar binary artifacts, tell the user the contents are not directly inspectable and ask for source-level changes or a text diff.
- Watch for cleanup debt: temporary files, deprecated implementations, compatibility shims, duplicate configs, or transitional assets that should be deleted before submission.
- Clean the temporary export directory produced for the review unless the user asked to keep it for inspection.

