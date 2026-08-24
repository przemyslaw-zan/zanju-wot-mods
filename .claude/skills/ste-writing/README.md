# ste-writing — vendored third-party skill

This directory is a verbatim copy of a third-party Claude Code skill. It is not maintained here. Do not edit these files in place: report problems upstream, then re-vendor.

## Source

- **Upstream:** https://github.com/woosal1337/blog — `videos/ep01-the-cure-for-ai-slop/ste-writing/`
- **Author:** Ege Çelebi
- **Commit:** `e0d5c34ef3b0f8db8b83d995e62c02a7213a1183` (2026-08-24)
- **Vendored:** 2026-08-24
- **License:** MIT — see [LICENSE](LICENSE), copied unchanged from the upstream repository root.

## What was copied

`SKILL.md`, `ste-recurring-errors.md`, and `ste-lint.py`, byte-for-byte with no modifications. The upstream episode directory also holds an `experiment/` folder with the author's cross-model benchmark; it is not part of the skill and was left out.

## What it does

The skill rewrites prose into ASD-STE100 Simplified Technical English. It applies to documentation, README text, pull-request descriptions, and release notes. It does not apply to code. `ste-lint.py` scores a draft for rule violations per 100 words. It needs Python 3 and the standard library only:

```
python3 .claude/skills/ste-writing/ste-lint.py docs/installing-mods.md
```

The repository lint task does not read this directory, so `ste-lint.py` is not held to the `zwm lint` rules for the Python 3 tooling.

## Upstream notices

The skill is unofficial and has no affiliation with ASD. ASD-STE100 is a registered EU trademark (No. 017966390). The standard itself is free at https://asd-ste100.org and is copyrighted; the skill quotes rule numbers but does not reproduce it.
