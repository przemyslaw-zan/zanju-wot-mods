# Testing

Unit tests here belong to the **mods**, not to the repository tooling. Their job is to keep shipped runtime behaviour stable: the logic that renders a label, parses a translation file, or decides when a subscription has lapsed. Tooling breakage surfaces immediately to whoever is running it, so it is fixed as it appears rather than guarded by tests.

Run them with:

```bash
zwm test --all          # every mod
zwm test premium-time   # one mod
zwm test --all --verbose
```

CI runs `zwm test --all` as part of the lint workflow, so mod tests gate releases.

## Opting a mod in

A mod has tests when it has a `tests/` directory. There is nothing to register: `zwm test` discovers by convention, the same way `zwm build` picks up an optional `ui/compile_ui.py`.

| File in `mods/<name>/tests/` | Runs under | Notes |
| --- | --- | --- |
| `test_*.py` | Python 2.7 `unittest` | Same interpreter the WoT client uses |
| `*.test.js` | `node --test` | Node's built-in runner; no npm dependencies |
| `run_tests.py` | Python 3 | Escape hatch: takes over the whole run for that mod |

Suites are reported per mod, and the command exits non-zero if any of them fail.

## Python 2.7 tests

Mod runtime code cannot simply be imported outside the game, for two reasons:

- every package imports `._mod_meta`, which `zwm build` generates from `meta.xml` and which therefore does not exist in the source tree;
- some modules import client APIs (`BigWorld`, `ResMgr`, `gui.*`) at module scope.

`testing/run_py27_tests.py` handles both before discovery: it puts the mod's `src/` on the path, synthesizes `_mod_meta` from the mod's own `meta.xml`, and installs the stub modules listed in `testing/zwm_test_env.py`. Test files therefore import mod modules directly:

```python
from zanju_pt import localization


class ParseFlatYamlTest(unittest.TestCase):
    def test_skips_untranslated_empty_values(self):
        self.assertEqual(localization._parse_flat_yaml('KEY: ""'), {})
```

Write tests as plain `unittest.TestCase` classes so they stay runnable by any unittest-compatible runner rather than being tied to `zwm test`.

**Keep the stubs thin.** They exist so that *import* succeeds for modules whose logic is pure. A stub that quietly returns plausible client data turns a failing test green — if a test needs client behaviour, fake it explicitly in the test.

**Non-ASCII source needs `# -*- coding: utf-8 -*-`.** Python 2 defaults to ASCII source, so a stray en dash in a docstring makes the module unimportable. This is easy to miss because neither other gate reports it: flake8 stays quiet, and `py_compile` — what `zwm build` uses — accepts the file and emits a working `.pyc`, so the mod still runs in-game. It surfaces only when something imports the source, i.e. the moment you write a test for it. `zwm lint py27-lint` now fails on it directly.

Both `mods/*/tests` and `testing/` are linted as Python 2.7 (`zwm lint py27-lint`), so test code is held to the same standard as the runtime it covers.

## JavaScript tests

Gameface-side JavaScript is plain ES modules, which Node can import directly. A mod with JS tests carries a minimal `package.json` (`{"type": "module"}`) so Node parses `res/` and `tests/` the same way Gameface does. It declares no dependencies and is not packaged into the `.wotmod`.

Modules under test must not start themselves on import. The header patch guards its bootstrap on the presence of the Gameface view registry:

```js
if (typeof window !== 'undefined' && window.subViews) {
    start();
}

export { formatRemaining, overrides, newState, tick, start, setLabel, updateSubscription };
```

Importing it under Node is then side-effect free, and each test drives the exported functions against its own fake model, DOM and clock.

Node is optional: mods without JavaScript never need it. If JS tests exist but Node is missing, those suites are reported as **skipped** rather than failing, so the command still works on a toolchain image built before Node was added. Pass `--strict` to turn such a skip into a failure.

## What is worth testing

Favour logic that is pure, that users see, and that has already gone wrong once:

- string and time formatting (label widths, date/offset rendering);
- parsers fed by hand-edited files, such as `i18n/*.yml`;
- state machines around client events, such as what a header button shows between a subscription expiring and the server confirming it.

Deeply client-coupled code (inventory walks, view construction) is not worth faking — the stubs needed to reach it would encode more assumptions than the test verifies.

ActionScript is not covered: executing a SWF test suite needs a Flash Player, which has been end-of-life since 2020. `mxmlc` compiling during `zwm build` is the practical check there, so logic worth testing is better placed in Python or JavaScript.
