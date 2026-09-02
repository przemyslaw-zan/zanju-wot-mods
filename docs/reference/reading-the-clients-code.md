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
| `scripts.pkg` | `scripts/client/**`, `scripts/common/**`, `scripts/client_common/**` — the core Python, as `.pyc` |
| `gui-part1.pkg` … `gui-part4.pkg` | `gui/gameface/`, `gui/flash/`, `gui/maps/icons/`, and `gui/unbound/` |
| `<feature>.pkg` | one mode or seasonal feature: its own Python, Gameface documents and SWFs |
| `<map-name>.pkg` | per-map assets |

Extract only what you need; `scripts.pkg` is large and decompiling it wholesale is slow.

```bash
unzip -o -q /game/res/packages/scripts.pkg \
    'scripts/client/gui/shared/gui_items/Tankman.py*' -d out/
```

## `scripts.pkg` is not all of the Python

Every mode and seasonal system ships as its own **extension package** beside it. On 2.3.1.3 those are `comp7.pkg`, `comp7_core.pkg`, `comp7_light.pkg`, `fun_random.pkg`, `last_stand.pkg`, `frontline.pkg`, `battle_royale.pkg`, `story_mode.pkg`, `event_platform.pkg`, `battle_modifiers.pkg`, `in_battle_achievements.pkg`, `resource_well.pkg`, `journey_marathon.pkg` and `open_bundle.pkg`.

Each holds a tree of its own, rooted at the feature name rather than at `scripts/`:

```text
comp7_light/extension.xml
comp7_light/scripts/client/comp7_light/gui/impl/lobby/hangar/...
comp7_light/gui/gameface/_dist/production/lobby/MembersWindow/...
comp7_light/gui/flash/comp7_light_battle.swf
```

Ten of them carry **2,644 `.pyc` files**, against 8,428 in `scripts.pkg`. So a search that stops at `scripts.pkg` misses every mode implementation, and it misses them silently: `grep` reports absence, not an error. Two claims in this section were wrong for exactly that reason before it was written down.

`extension.xml` declares the feature name, its enabled state, its personality module and its components. A personality module usually exposes `preInit()`, `init()`, `start()` and `fini()`, which is where the feature registers its controllers, views and routes. The guide's [source-navigation](https://modding.wot-tools.dev/source-navigation.html) page covers that anatomy in full.

Extract the extension packages next to the core tree and search both:

```bash
for pkg in comp7 comp7_core comp7_light fun_random last_stand \
           frontline battle_royale story_mode event_platform battle_modifiers; do
    unzip -o -q "/game/res/packages/$pkg.pkg" '*.pyc' -d ext/
done
grep -rl --binary-files=text "LoadoutPresenter" full/scripts/client/ ext/
```

**A claim of the form "there is only one X in the client" needs both trees searched.** Anything that names a *mode* — Onslaught, Frontline, Fun Random, Last Stand, Battle Royale — almost certainly has an implementation outside `scripts.pkg`.

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

A version stamp is not the same as a verified claim. Two pages here carried a 2.3.1.3 stamp and a
wrong statement at the same time, because the stamp records when the search ran and not how wide
it reached. State what was searched as well as when.

For how much weight each kind of evidence carries — a definition against a caller against a
firing site against a runtime log — use the guide's
[source-evidence-ladder](https://modding.wot-tools.dev/source-evidence-ladder.html) rather than
repeating it here. See [The Upstream Modding Guide](upstream-guide.md).
