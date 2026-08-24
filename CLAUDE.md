# CLAUDE.md

## Prose style

Always use the `ste-writing` skill for prose, including when nobody asks for it. Prose means Markdown files, code comments and docstrings, commit messages, and user-visible strings such as error messages and translation source text. It never means code, identifiers, or command syntax.

Use strict mode for procedures, install steps, and error messages. Use STE-flavored mode everywhere else.

## Markdown line wrapping

Write each paragraph, list item, and table row as a single long line. Never wrap text at a fixed column. The only correct hard break is two trailing spaces or a `<br>` tag.
