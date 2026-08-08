# Reading The Client's Own Code

Every version-scoped claim in this section was checked against the shipped client rather than
against community documentation. This page records how, so those checks are repeatable and so a
patch-day investigation does not start from scratch.

There is no published decompiled-source repository for WoT. Guides that point at one are out of
date — see [Resources And External Links](../resources.md). The client ships everything needed
to read it directly.

## The packages are ZIP archives

`res/packages/*.pkg` are plain ZIPs. Nothing special is needed to open them.

| Package | Holds |
| --- | --- |
| `scripts.pkg` | `scripts/client/**` and `scripts/common/**` — all the Python, as `.pyc` |
| `gui-part1.pkg` … `gui-part4.pkg` | `gui/gameface/`, `gui/unbound/`, `gui/flash/`, `gui/maps/icons/` |
| `<map-name>.pkg` | per-map assets |

Extract only what you need; `scripts.pkg` is large and decompiling it wholesale is slow.

```bash
unzip -o -q /game/res/packages/scripts.pkg \
    'scripts/client/gui/shared/gui_items/Tankman.py*' -d out/
```

## Find the symbol before decompiling it

The useful step, and the one that saves the most time: `.pyc` files keep their identifier names
as plain bytes, so a text-mode grep finds every module referencing a symbol **without**
decompiling anything. Extract the tree once, then search it.

```bash
unzip -o -q /game/res/packages/scripts.pkg 'scripts/client/*' -d full/
grep -rl --binary-files=text "crewMemberRealSkillLevel" full/scripts/client/
```

That narrows a question like "who calls this, and what do they pass?" from thousands of files to
a handful, which are then worth decompiling. Going the other way — decompiling broadly and then
reading — is much slower and often unnecessary.

## Decompiling

`uncompyle6` is installed in the toolchain image and runs under Python 3. The output directory
must already exist; it fails rather than creating one.

```bash
mkdir -p out/
uncompyle6 -o out/ full/scripts/client/gui/shared/gui_items/Tankman.pyc
```

It handles the client's 2.7 bytecode well. Decompiled output is reference material only — never
copy it into the repository.

## What cannot be read this way

- **`scripts/item_defs/**/*.xml`** are packed binary, not text XML. Grepping them for a tag or a
  price returns nothing. Read the values through a running client instead, or through the code
  that parses them.
- **The Wwise sound banks** (`res/audioww/*.bnk`) need dedicated tooling.

## Flash

`swfdump` ships in the toolchain image (Apache Flex SDK) and disassembles a SWF's ABC to AVM2
opcodes:

```bash
/opt/apache-flex-sdk/bin/swfdump -abc gui/flash/battle.swf
```

Most SWFs are `CWS` (zlib-compressed): the payload is `zlib.decompress` of everything after the
8-byte header, rewrapped as `FWS` if a tool insists on the uncompressed form.

## Other people's `.wotmod` packages

A `.wotmod` is a ZIP as well, so the same steps apply to an installed mod under
`/game/mods/<version>/`. Two things differ:

- Some mods ship **obfuscated** Python — scrambled `co_code`, XOR-encoded names, payloads hidden
  in an outer loader. Clean decompilation of those is impractical.
- Their **Flash is usually not obfuscated** even when the Python is, so when a mod has a SWF, its
  behaviour is normally easier to read there. The DAAPI naming convention is the key: methods
  named `as_*` are Python→SWF, while methods the SWF calls but does not define are SWF→Python.

## Recording what you find

Cite the client version in any page built from a decompilation — the client is a moving target
and an uncited claim cannot be rechecked. The pages in this section that carry findings all open
with the version they were verified against.
