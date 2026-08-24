# Translating

This page is for translators adding or updating a language for a mod.

You do **not** need the build toolchain (Docker, the VS Code Dev Container, Java/Flex). That setup is only for building `.wotmod` packages. Translating needs just **Python 3** and Git.

## How translations work

- Each mod keeps its text under `mods/<mod-name>/i18n/`, one file per language: `en.yml`, `pl.yml`, and so on.
- `en.yml` is the source of truth — it defines every string key. Other languages translate those same keys; anything a language is missing falls back to English in-game.
- Files are flat `KEY: "value"` YAML. Translate the **value**, never the key. Keep:
  - escapes such as `\n` (line break) and `\"` (a literal quote) intact,
  - `{placeholders}` like `{xp}`, `{level}`, `{count}` untouched — the mod fills those in at runtime.

## Add or update a language

1. Use the language code the WoT client uses (`pl`, `de`, `fr`, `ru`, `uk`, ...).
2. In `mods/<mod-name>/i18n/`, copy `_template.yml` to `<code>.yml` (or open the existing language file). The template has every key with an empty value and the English source text in the `# en:` comment above it — fill in the values. Copying `en.yml` and translating in place works too.
3. Translate each value:

   ```yaml
   # en.yml
   MODE_RESEARCH: "Research"

   # pl.yml
   MODE_RESEARCH: "Badania"
   ```

You do not have to translate every key at once — untranslated keys simply show in English, and the coverage table (below) tracks how complete each language is. A key can also be kept in the file with an empty value (`SOME_KEY: ""`) as a "still to translate" placeholder: empty values are treated exactly like missing keys, both in-game (English fallback) and in the coverage table.

## Refresh the coverage table

Every mod README has a `## Translations` table with each language's coverage. After editing a `.yml`, regenerate it:

```bash
python3 -m tools.commands.lint i18n
```

This needs only Python 3 — no Docker, no Dev Container. (Inside the Dev Container the same command is `zwm lint i18n`.)

Continuous integration runs `python3 -m tools.commands.lint i18n-check` and will fail the pull request if the table is out of date, so run the command and commit the updated README alongside your `.yml` changes.

## Submit your changes

Contribute via a fork and a pull request. New to that? GitHub's guide walks through the whole flow: [Contributing to a project](https://docs.github.com/en/get-started/exploring-projects-on-github/contributing-to-a-project).

No local setup at all? You can edit the `.yml` file directly in GitHub's web editor and open a pull request from there — a maintainer can regenerate the coverage table during review.
