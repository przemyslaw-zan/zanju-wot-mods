# In-Game Settings (Mod Menu)

The repo's convention for exposing a mod's settings in the in-game settings menu.

## API and import

Settings render in Aslain's Mod Menu, under the `gui.aslainMenu` namespace. It is bundled as a
companion artifact (pinned in `tools/companion_artifacts_manifest.json`) and imported directly:

```python
try:
    from gui.aslainMenu import g_modsSettingsApi
except Exception:
    g_modsSettingsApi = None
```

Mod Menu stays backward-compatible with izeberg's `g_modsSettingsApi`
(`setModTemplate` / `updateModSettings`), so the template is a plain dict — no rewrite
onto Aslain's `templates.*` helpers is required to integrate.

Mod Menu replaced `aslain.modssettingsapi` and keeps its API, so a mod that reads
`g_modsSettingsApi` needs no change. The package changed and that part matters. Both ids ship the
same `gui/aslainMenu` scripts, so a client holding one of each refuses one and raises a dialog
about it. This repo bundled the old id until 2 September 2026, which broke the install for anyone
whose modpack had already moved. Two copies of Mod Menu carry one id and load without complaint.

## Integration shape

Register the template with a change callback, then push the current values:

```python
api.setModTemplate(mod_id, template, on_settings_changed)
# guard updateModSettings against re-entrancy so its echo doesn't re-trigger the callback
api.updateModSettings(mod_id, current_values)
```

- Each control's `value` in the template is the mod's **factory default** (see Per-mod
  Reset below); the user's saved values are applied separately via `updateModSettings`.
- The change callback writes menu edits back into the config and saves.

## Config is the source of truth; the menu cache is a mirror

A mod's settings live in its AppData `config.json` (see
[Runtime Layout And Packaging](runtime-layout-and-packaging.md)). At startup the template
is **built from** that config and the values are re-pushed via `updateModSettings`. The
Mod Menu keeps its own cached copy, but it is downstream — anything the API resets
is re-filled from config on the next launch.

This single fact drives the `settingsVersion` convention below.

## Do not set `settingsVersion`

`settingsVersion` is an optional integer Mod Menu uses to decide whether a
re-registered template should replace its cached one. **Leave it out.** Verified against
the fork's `gui.aslainMenu/api.py` (`compareTemplates` / `_settingsStructure`,
fork ≥ 1.3.2):

| Template change | No `settingsVersion` (the convention) | `settingsVersion` present |
| --- | --- | --- |
| **Cosmetic** — a control's title/tooltip text, a default, reordering | applied; user values kept | applied; values kept (no bump needed) |

Re-verified against fork 1.7.0: `compareTemplates` and `_settingsStructure` are byte-identical
to 1.6.4, so nothing above changed with that release. One caveat on the cosmetic row: since
1.7.0 a changed **default** is applied to the template but no longer refreshes the API's stored
defaults, so the Reset target goes stale — see *Declare the defaults explicitly* below.
| **Structural** — control added/removed/retyped, a radio/dropdown's option **labels or set**, a slider's range | applied automatically; the API resets its cached values to the template's `value` fields | applied + reset **only if you bump**; **silently ignored + warning if you forget to bump** |

- The "silently ignored" trap is **opt-in**: it only fires when `settingsVersion` is
  present but not bumped. Omitting the field means every change always applies.
- The structural reset is **lossless**, because the mod re-pushes the user's saved values
  with `updateModSettings` immediately after registering the template. (It is *not* lossless
  because the template carries the user's values — it must not; see Per-mod Reset below.)
- **Option labels are structural.** `_settingsStructure` includes each radio/dropdown's
  option labels in its signature, so a language switch (which re-translates option labels)
  is a *structural* change. With no `settingsVersion` it now applies — the old izeberg
  "labels stuck on cache until you bump" problem is gone. Adding `settingsVersion` would
  bring it back.

## `settingsVersion` is not `configVersion`

Two unrelated version fields:

- **`configVersion`** — a mod's own AppData `config.json` schema version, for migrating
  the config file's shape over time.
- **`settingsVersion`** — the Mod Menu template field described above.

Changing one has nothing to do with the other.

## Per-mod Reset and template defaults

Aslain's menu shows a per-mod reset control that restores a mod to the values the API
recorded as its defaults — and it captures those from the template's `value` fields at
registration. So the template must carry the mod's **factory defaults**, with the user's
current values applied separately:

- `setModTemplate` carries factory-default `value`s → the API records the real defaults.
- `updateModSettings` then sets the live values to the user's saved config.

If the template instead embeds the current values, the API records those as "defaults" and
Reset becomes a no-op — it restores whatever was present when the template was first
registered, not the mod's real defaults.

### Declare the defaults explicitly from 1.7.0

Deriving them from the template is no longer enough on its own. **1.7.0 stopped re-deriving
defaults when a re-registered template differs from the cached one without a structural
change** — it only re-derives on first registration or a structural change. Changing a value
in the mod's `_DEFAULT_CONFIG` is precisely a non-structural change, so from 1.7.0 on it
leaves Reset restoring the *previous* default, for existing users only, forever.

That removal was a deliberate fix, aimed at the opposite mistake: its release notes describe
defaults being "refreshed whenever a mod registered a template whose controls were unchanged
but whose values differed", so a mod that embedded *live* values in its template had Reset
restoring last session's settings. A mod following the factory-defaults rule above was never
affected by that bug and is the one the removal inconveniences — hence the explicit API.

1.7.0 adds `setModDefaults(linkage, {varName: value})` for this. Call it alongside
`setModTemplate`, feature-detected, since a modpack may ship an older build where derivation
is still the only mechanism:

```python
declare = getattr(g_modsSettingsApi, 'setModDefaults', None)
if callable(declare):
    declare(linkage, factory_defaults)
```

A partial declaration is fine — options left out fall back to the template's `value`. Note it
is a **one-way door**: the API records `defaultsLocked` for that linkage in the user's
`aslainMenu.json`, so removing the call later leaves the defaults frozen at whatever was last
declared rather than reverting to derivation.

This is not a reason to start setting `settingsVersion` — that trade-off is unchanged.

The other 1.7.0 addition, `resetFeatureHighlights(linkage, varNames=None)`, re-arms
`templates.markNew` highlights for a mod that wants to re-announce an option without bumping
the control's token.

## Notes

- Pin a recent fork build; the behavior above holds for the fork at ≥ 1.3.2. A user
  running an older `gui.aslainMenu` from a stale modpack may still see izeberg-style
  all-or-nothing template caching.
- The richer template features (`templates.createControlsGroup`, `enableWhen` /
  `visibleWhen`, `createImage`) are available under `gui.aslainMenu` but must be
  feature-gated with `hasattr(templates, ...)` / `g_modsSettingsApi.getVersionTuple()`,
  because older fork builds lack them.
