"""Convert a review file from the review-translation-pr skill into a GitHub review payload.

Usage: python3 -I build_review.py <review.md> <payload.json>

The script reads the head commit, the review body, and the inline comments from the review file.
Each inline comment needs a heading in the format of the skill: "### N. `path` line L" or "### N. `path` lines S–L".
The payload posts as a REQUEST_CHANGES review. To post it as a plain comment, change "event" to COMMENT in the payload.
"""
import json
import re
import sys

src, out = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()

commit = re.search(r"Head commit: `([0-9a-f]{40})`", text).group(1)
body = text.split("## Review body\n", 1)[1].split("## Inline comments\n", 1)[0].strip()
inline = text.split("## Inline comments\n", 1)[1]

heading = re.compile(r"^### \d+\. `([^`]+)` lines? (\d+)(?:[–-](\d+))?\s*$", re.M)
matches = list(heading.finditer(inline))
comments = []
for i, m in enumerate(matches):
    end = matches[i + 1].start() if i + 1 < len(matches) else len(inline)
    comment = {"path": m.group(1), "side": "RIGHT", "body": inline[m.end():end].strip()}
    if m.group(3):
        comment.update(start_line=int(m.group(2)), start_side="RIGHT", line=int(m.group(3)))
    else:
        comment["line"] = int(m.group(2))
    comments.append(comment)

payload = {"commit_id": commit, "event": "REQUEST_CHANGES", "body": body, "comments": comments}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2)
print(src, "->", out, "| comments:", len(comments))
for c in comments:
    print("  ", c["path"], c.get("start_line", ""), c["line"], "|", c["body"].splitlines()[0][:70])
