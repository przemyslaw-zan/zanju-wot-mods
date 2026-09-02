# Debugging

General debugging technique now lives upstream. The guide's [debugging-runtime](https://modding.wot-tools.dev/debugging-runtime.html) page covers instrumentation, context fields, the transition test matrix and traceback-bearing logs better than a local paraphrase would. See [The Upstream Modding Guide](reference/upstream-guide.md).

This page keeps the parts that belong to this repository, plus one client trap worth knowing before any of it.

## A Failure Inside `init()` Can Be Silent

The loader calls each mod's lifecycle methods through one helper, and the call is inside the `try`:

```python
def _callModMethod(mod, methodName, *args, **kwargs):
    try:
        return getattr(mod, methodName)(*args, **kwargs)
    except AttributeError:
        pass
```

So an `AttributeError` raised anywhere inside a mod's `init()` or `fini()` disappears with **no log line at all**. The mod then looks like one that never loaded, and the first three steps of the triage below all pass.

A wrong hook target after a client update raises exactly this. Every mod here therefore wraps its own `init()` body and logs the traceback itself. Keep that wrapper.

## Triage Order

1. Confirm the active WoT version folder.
2. Confirm the mod logged its own start line. No line means either a packaging fault or the silent `AttributeError` above.
3. Reproduce with as few mods enabled as possible.
4. Capture `game.log`, beside `WorldOfTanks.exe`. It **appends across launches**, so read forward from the last `starting on` banner, or start the run with `zwm cycle --fresh-log`.
5. Find the first relevant traceback or state transition. `[SCRIPT]` lines are Python and carry the logger name, `[UI] [Gameface]` lines are a document's JS console.
6. Re-enable dependencies one by one if the issue only appears in a modpack.

## Common Failure Classes

- wrong hook target after a patch
- missing optional dependency
- stale package deployed to the wrong `mods/<version>/` folder
- config schema mismatch
- UI assets moved or removed by the client
- a stale Gameface resource map, which needs a client restart rather than a view reload

## Daily Validation Loop

1. deploy the target mod
2. restart the game
3. reproduce the scenario once
4. inspect `game.log`
5. narrow the failing surface before editing again

## Where Findings Belong

Record a version-bound finding next to the mod or subsystem it belongs to, not here. Each reference page opens with the client version it was checked against.

State what was searched as well as when. A version stamp records the date of a search, not its reach, and two pages here carried a correct stamp beside a wrong claim because the search stopped at `scripts.pkg`. See [Reading The Client's Own Code](reference/reading-the-clients-code.md#scriptspkg-is-not-all-of-the-python).

## Related Reading

- [Developing Mods](developing-mods.md)
- [The Upstream Modding Guide](reference/upstream-guide.md)
- [Technical Reference](reference/README.md)
