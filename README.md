# P4 Review Changelist Skill

A shareable Codex skill repository for reviewing Perforce changelists by changelist number.

## What this skill does

- exports a changelist into review artifacts with Python
- supports submitted, pending, and shelved changelists
- recovers patch hunks for pending CLs from local workspace files when `p4 describe -du` is incomplete
- gives a fast first-pass verdict before deeper investigation
- detects binary-only or unreadable CLs and lowers confidence instead of pretending to review code
- keeps cleanup safe by only removing managed temp export directories when review is done

## Repository layout

- `p4-review-changelist/SKILL.md`: main skill instructions
- `p4-review-changelist/scripts/export_changelist.py`: changelist export helper
- `p4-review-changelist/scripts/cleanup_export.py`: safe cleanup helper
- `p4-review-changelist/scripts/requirements.txt`: runtime requirements
- `p4-review-changelist/references/review-checklist.md`: review checklist
- `p4-review-changelist/agents/openai.yaml`: optional agent metadata

## Requirements

- Windows workstation with Perforce CLI available as `p4`
- Python 3.10+
- a valid Perforce workspace and login session

No third-party Python packages are required.

## Install

Copy the `p4-review-changelist` folder into your Codex skills directory.

Typical location:

```text
%USERPROFILE%\\.codex\\skills\\p4-review-changelist
```

If you are cloning this repository for local use, copy or symlink only the inner `p4-review-changelist` folder into `%USERPROFILE%\\.codex\\skills`.

For Chinese instructions, see [`README_zh.md`](./README_zh.md).

## Basic usage

Ask Codex with a changelist number, for example:

```text
Please review P4 changelist 6969680
```

The skill will usually:

1. export the changelist artifacts
2. read metadata and diff
3. give a short initial verdict
4. continue deeper only if the user asks
5. clean temp exports after review unless the user wants to keep them

## Manual helper commands

Export a CL:

```powershell
python ".\\p4-review-changelist\\scripts\\export_changelist.py" --change 6969680
```

Export a shelved CL:

```powershell
python ".\\p4-review-changelist\\scripts\\export_changelist.py" --change 6969680 --shelved
```

Clean a managed temp export directory:

```powershell
python ".\\p4-review-changelist\\scripts\\cleanup_export.py" --output-dir "C:\\Users\\<you>\\AppData\\Local\\Temp\\p4-review-6969680"
```

## Notes

- this repository is intended to be shared as a skill library, not as an application package
- the exporter preserves older review exports until explicit cleanup, which is safer for follow-up review rounds
- binary-only CLs are reported as low-confidence instead of being treated like normal source reviews
