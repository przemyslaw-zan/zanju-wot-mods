# Architecture

This page explains how mods in this repository are structured, packaged, and loaded by World of Tanks.

## Packaging Model

A distributable mod is a `.wotmod` archive (a no-compression zip) whose only
required element is `res/`. An optional root `meta.xml` manifest carries
`<id>`/`<version>`/`<name>`/`<description>` (the `<id>`/`<version>` drive load
order and version de-dup; the loader falls back to the filename when it is
absent). See [Runtime Layout And Packaging](reference/runtime-layout-and-packaging.md#package-shape)
for the full package contents.

## Repository Layout

A typical mod in this repo looks like this:

```text
mods/<mod-name>/
  meta.xml
  src/
    mod_<bootstrap>.py
    <internal_package>/
      __init__.py
      main.py
      ...
  i18n/
  ui/
```

## Python Entry Points

In this client stack, the stable pattern is:

- keep a thin top-level `mod_*.py` bootstrap in `src/`
- place real implementation in a uniquely named internal package
- keep `__init__.py` in that package for Python 2 recognition
- prefer explicit relative imports inside the package

Do not rely on a package-only entry point.
Do not use the same name for the bootstrap file and the internal package.

## Runtime Locations And Build Rules

Both live in [Runtime Layout And Packaging](reference/runtime-layout-and-packaging.md), so they
are not repeated here. `zwm build` is the entry point, and [Building From Source](building-from-source.md)
covers running it.

## UI Pattern Used In This Repo

For custom lobby UI, the stable pattern is:

- compile ActionScript externally
- load the SWF through WoT view registration
- keep the SWF root on a WoT-compatible `IView` implementation such as `AbstractView`
- let WoT own the display tree attachment

For more detailed UI/runtime notes, see [UI And Scaleform](reference/ui-and-scaleform.md).

## Dependency Philosophy

Shared mod APIs should be optional unless the mod truly cannot run without them. If a dependency
is absent, the mod degrades instead of crashing. How to gate one so a missing package disables
only the feature that needs it is upstream, in
[optional-systems](https://modding.wot-tools.dev/optional-systems.html).

## Related Reading

- [Building From Source](building-from-source.md)
- [Developing Mods](developing-mods.md)
- [Technical Reference](reference/README.md)
