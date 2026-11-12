---
name: review-translation-pr
description: Review community translation pull requests for the mods in this repository, and write one review file per pull request to `/workspace/.tmp/` for the maintainer to edit and post. Use when the user asks to review translator, translation, language, or i18n pull requests, with or without pull request numbers.
---

# Review translation pull requests

The maintainer does not speak most of the languages that community translators send. This skill makes an AI review that the maintainer reads, edits, and then posts on GitHub. Never post the review yourself.

## Rules for the review

- Write only actionable notes: things to fix and things to improve. Do not praise the work, do not say what works, and do not summarize the pull request.
- Start the review body with this disclaimer, word for word. Replace `[language]` with the English name of the language, for example "Russian" or "Chinese":

  > Hi! Thank you for this pull request. Since I do not speak [language], this review is AI-generated, so please take it with a grain of salt. Apply the requested changes that you agree with, and explain why you disagree with the others.

- Post the review as "Request changes", not as a comment. The translator can still refuse a request, but the pull request shows that it has open requests.

- Anchor each request at a line of the diff when possible. GitHub accepts an inline comment only on a line in a diff hunk: a changed line, or one of the three context lines around it. In a new file, every line is in the diff. A note about a line outside the hunks goes in the review body, with a permalink on the head commit: `[<path>:<L>](https://github.com/przemyslaw-zan/zanju-wot-mods/blob/<head_sha>/<path>#L<L>)`. For a range of lines, use `#L<S>-L<L>`.
- When one problem occurs on many lines, explain it once in the review body. Then put a short inline comment with a `suggestion` block on each line, and refer to the review body for the reason.
- Give each inline comment a GitHub `suggestion` block with the full replacement line, so that the translator can apply it with one click. To remove lines, anchor the comment on the range and use an empty `suggestion` block.
- When the choice of a term is for the translator, give no `suggestion` block. Give the condition that the term must meet, for example which meanings it must keep apart. Put the full comment on the main line, and on the other lines put a short comment that refers to it.
- Do not put a required fix (for example, the brand) and an optional change in one `suggestion` block. A translator who rejects the optional change can drop the required fix with it. If both changes are on the same line, say which change is required, and say how to apply only that change.
- Keep each reason to one to three short sentences. Many translators read English as a second language. Write the English prose in the STE-flavored mode of the `ste-writing` skill. Do not apply STE to the disclaimer, or to quoted text in another language.
- Review only the strings that the pull request adds or changes. Cite an existing string only when a new string must agree with it.
- Do not ask the translator for these:
  - Changelog lines or version bumps. The maintainer adds them after the merge.
  - A fix for a coverage-table conflict with another open translation pull request. The maintainer regenerates the tables after the merge.
  - Changes to `#` comment lines, in English or translated. The exception is a comment that is wrong in a way that misleads the next translator.

## Procedure

1. Find the pull requests. If the user gives no numbers, list the open pull requests, and keep the ones that change `i18n/*.yml` files. The `gh` CLI is not in the Dev Container, so use the public API:

   ```bash
   curl -s "https://api.github.com/repos/przemyslaw-zan/zanju-wot-mods/pulls?state=open" | jq '[.[] | {number, title, user: .user.login, head_sha: .head.sha, base_sha: .base.sha, body}]'
   ```

2. Fetch the head commit of each pull request. This command writes only `FETCH_HEAD`. It makes no branch, ref, or tag:

   ```bash
   git fetch --no-tags origin pull/<N>/head
   ```

3. Read the full diff with `git diff <base_sha>...<head_sha>`. If the pull request changes files other than `i18n/*.yml` files and README coverage tables, tell the user, and review those files with more care.
4. Run the mechanical check. It reads the files with `git show`, and it prints a `PROBLEM` line for each defect that it finds:

   ```bash
   python3 -I .claude/skills/review-translation-pr/check_i18n.py <base_sha> <head_sha>
   ```

   Do not check out the pull request, and do not run its tooling, for example `python3 -m tools.commands.lint`. That is code from an external fork, and auto mode blocks it.

5. For each changed key, read the English text and the `#` comment above the key in `en.yml`. Then read the files of the same language in the other mods and in `mods-common/i18n/`.
6. Find where each key shows in the game: grep the key in `mods/<mod>/src` and `mods/<mod>/res`.
7. Examine each string with the checklist below.
8. Get the line numbers on the head commit with `git show <head_sha>:<path> | grep -n ""`.
9. Write the review file in the format below.
10. Lint the review file with the `ste-lint.py` script of the `ste-writing` skill, in flavored mode. The script also counts the quoted translations and the `suggestion` blocks, so fix only the findings in the English sentences.
11. Report to the user. See the last section.
12. When the user tells you to post, first read the review file again, because the user can edit it. Then make sure that the head commit of the pull request did not change. If it changed, the line numbers can be wrong, so do steps 3–10 again for the new commit.
13. Build the payload next to the review file:

    ```bash
    python3 -I .claude/skills/review-translation-pr/build_review.py .tmp/pr-<N>-<code>-review.md .tmp/pr-<N>-<code>-review.json
    ```

14. Give the user the commands to post. Auto mode blocks the agent when it tries to read the GitHub token from the git credential helper, so the user runs them. From the host, with `gh`:

    ```bash
    gh api --method POST repos/przemyslaw-zan/zanju-wot-mods/pulls/<N>/reviews --input .tmp/pr-<N>-<code>-review.json
    ```

    In the Dev Container, which has no `gh`:

    ```bash
    TOKEN=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | sed -n 's/^password=//p')
    curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "https://api.github.com/repos/przemyslaw-zan/zanju-wot-mods/pulls/<N>/reviews" --data-binary @.tmp/pr-<N>-<code>-review.json | jq '{state, html_url, message}'
    ```

15. After the user posts, read `https://api.github.com/repos/przemyslaw-zan/zanju-wot-mods/pulls/<N>/comments` without a token, and make sure that each comment is on its line.

## Checklist

Mechanical checks (the check script and the diff):

- The key set agrees with `en.yml`. There is no extra key. An empty or missing key falls back to English, which is permitted.
- The placeholders (`{stage}`), the line breaks (`\n`), and the HTML tags (`<b>`) are the same as in English. A translation can use the quote marks of its language in place of `\"`.
- Each value is a flat `KEY: "value"` line, in double quotes.
- The root `README.md` and `mods/<mod>/README.md` show the new coverage counts. A mod README also counts the shared strings that the mod uses. Continuous integration runs `i18n-check` and fails on a table that is out of date.
- Template header: a file copied from `_template.yml` starts with "Auto-generated translation template", and it says "do not edit by hand". The lint writes only `_template.yml`, so ask the translator to remove lines 1–6 and the blank line after them. The `# en:` lines can stay.

Language checks:

- Meaning: compare the translation with the English text and with the `#` comment above the key. The comment often names a case that the translation must cover, for example "The same text shows with a Crucible active and with none active".
- UI context: in Mod Menu, `make_tooltip` shows the setting label as the header of the tooltip, above the `TOOLTIP_*_BODY` text. Some strings have little room. For example, each `UNIT_*` string must stay at one or two letters.
- Choices of a setting: a word in a label or a tooltip must fit all choices. For example, "bar" does not fit a setting where one of the choices is a round dial.
- Game terms: use the term that the client shows in that language. The client in `/game` has only its own language, so do not claim that you compared a term with another language of the client. Say where a term comes from, or say that you could not examine it.
- Consistency across mods: the same word for the same thing in all files of the language, and in `mods-common/i18n/`. The term of the client comes before the other files of this repository. For example, the Chinese client uses 坦克 for "vehicle", also in its Crucible strings, so `zh_cn` uses 坦克, although older Campaign Tracker strings use 车辆. If the other files differ from the client, ask for a separate pull request that aligns them.
- Consistency in the file: sibling labels have the same form, sibling tooltips have the same sentence form, and one English verb gets one translated verb.
- Brand: "Zanju's" stays word for word, with the 's, in every language. "Zanju 模组" and "модов от Zanju" are wrong.
- Typography: obey the conventions of the language and of the file. Examples are the full-width punctuation in Chinese (：，。), the «» quote marks in Russian, and the use of ё in the rest of the file.

## Review file format

Save each review as `/workspace/.tmp/pr-<N>-<language code>-review.md`, for example `pr-37-ru-review.md`. The `.tmp/` folder is in `.gitignore`. Write each paragraph on one line.

````markdown
# PR #<N> review: <PR title>

Posting data (do not post this part):

- PR: https://github.com/przemyslaw-zan/zanju-wot-mods/pull/<N>
- Head commit: `<head_sha>`
- Each inline comment goes on the right side of the diff, at the line or lines in its heading. The line numbers are for the head commit.

## Review body

<the disclaimer>

<notes that have no line, if there are any>

## Inline comments

### 1. `<path>` line <L>

<reason>

```suggestion
<full replacement line>
```

### 2. `<path>` lines <S>–<L>

<reason>

```suggestion
```
````

Put the inline comments in the order of the diff: file by file, and line by line in each file.

## Report to the user

- Give the path of each review file, and the number of notes in it.
- Give the issues that are for the maintainer, not for the translator. Examples are two open pull requests that change the same row of a coverage table, or the same problem in files that are already on `master`.
- Give the notes that need the judgment of the maintainer, for example a request against a pattern that the maintainer merged before.

## When the translator answers

1. Read the answer. Conversation comments are at `https://api.github.com/repos/przemyslaw-zan/zanju-wot-mods/issues/<N>/comments`. Thread replies are at `.../pulls/<N>/comments`. A translator often amends and force-pushes, so get the head SHA again from `.../pulls/<N>`. An answer can be only a new commit, with no comment.
2. Fetch the new head, and compare it with the head that you reviewed: `git diff <old_head> <new_head>`. For each inline comment, find the result: applied, rejected with a reason, or dropped without a reason.
3. Run the check script on the new head.
4. Judge each rejection by its reason. Accept a reason that rests on the text of the client. A required fix, for example the brand, stays required.
5. Write the reply to `/workspace/.tmp/pr-<N>-<code>-reply.md`. Put the answer to the whole message in a conversation comment. Put each request that stays in a reply in the thread of its review comment. A thread reply can have a new `suggestion` block if its comment still has a `line` value in `.../pulls/<N>/comments`. If the value is null, the comment is outdated, so post a new review comment on the new head. When all the requests that stay are outdated, write the reply in the review file format, so that `build_review.py` can make its payload. Put the answer in the review body. The first review has the disclaimer already, so do not add it again.
6. When the user tells you to post, write each part to its own file, for example `.tmp/pr-<N>-<code>-reply-1.md`. Then give the user the commands:

   ```bash
   gh api --method POST repos/przemyslaw-zan/zanju-wot-mods/issues/<N>/comments -F body=@.tmp/pr-<N>-<code>-reply-1.md
   gh api --method POST repos/przemyslaw-zan/zanju-wot-mods/pulls/<N>/comments/<comment id>/replies -F body=@.tmp/pr-<N>-<code>-reply-2.md
   ```

7. When the translator applies each request, or gives a reason that you accept, tell the user that the review still shows "Changes requested". The user can approve the pull request before the merge.
