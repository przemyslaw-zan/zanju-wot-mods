# -*- coding: utf-8 -*-
"""Import environment for mod runtime tests (Python 2.7).

Mod runtime packages cannot be imported outside the running game as-is:

* every package imports `._mod_meta`, which does not exist in the source tree —
  `zwm build` generates it from `meta.xml` into the package (see
  `bundle_generated_mod_meta` in tools/commands/build.py);
* the shared modules live in mods-common/, not in the package — `zwm build`
  compiles them into it (see `bundle_shared_modules`);
* some modules import WoT client APIs (`BigWorld`, `ResMgr`, `gui.*`, ...) at
  import time, which only exist inside the client.

`install()` recreates just enough of that: it synthesizes `_mod_meta` for every
internal package of the mod under test, loads the shared modules that the mod takes
into each of those packages, and registers stub modules for the client APIs listed
in `GAME_STUB_MODULES`. It is called by `run_py27_tests.py` before test discovery,
so test files themselves import mod modules directly with no boilerplate.

Keep the stubs minimal: they exist so that *import* succeeds for modules whose logic
is pure. Anything that needs real client behaviour should be faked by the test itself,
not blessed here — a stub that quietly returns plausible data turns a failing test green.
"""
from __future__ import print_function, unicode_literals

import imp
import importlib
import os
import sys
import types

# Client modules that mod code imports at module scope. Values are attribute dicts;
# an empty dict yields a bare module object. Modules guarded by try/except at the
# import site (e.g. `ResMgr` in localization.py) deliberately stay absent so tests
# exercise the same no-client fallback path the mod uses when a dependency is missing.
GAME_STUB_MODULES = {
    # constants.py reads two hangar aliases off VIEW_ALIAS at import time. The import
    # needs the names. The strings behind them are placeholders, not the client's own
    # values. Never match a real route against them.
    "gui.Scaleform.daapi.settings.views": {
        "VIEW_ALIAS": type(str("VIEW_ALIAS"), (object,), {
            "LOBBY_HANGAR": "<stub:lobbyHangar>",
            "LEGACY_LOBBY_HANGAR": "<stub:legacyLobbyHangar>",
        }),
    },
}


def install(src_dir=None, mod_id=None, mod_name=None, shared_dir=None, shared_names=(),
            stand_in_package=None):
    """Make the mod under test importable. Safe to call more than once.

    With `stand_in_package`, there is no mod: the shared modules load into an empty package
    of that name, so that their own tests can import them.
    """
    mod_id = mod_id or os.environ.get("ZWM_MOD_ID", "")
    mod_name = mod_name or os.environ.get("ZWM_MOD_NAME", "")

    if stand_in_package:
        packages = [_install_stand_in_package(stand_in_package)]
    else:
        src_dir = src_dir or os.environ.get("ZWM_MOD_SRC", "")
        if not src_dir:
            raise RuntimeError("ZWM_MOD_SRC is not set; run tests through `zwm test`")

        src_dir = os.path.abspath(src_dir)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        packages = list(_iter_internal_packages(src_dir))

    _install_game_stubs()
    for package in packages:
        _install_mod_meta(package, mod_id, mod_name)
        _install_shared_modules(package, shared_dir, shared_names)


def _iter_internal_packages(src_dir):
    """Yield immediate sub-package names of src/ (mirrors the build's own rule)."""
    if not os.path.isdir(src_dir):
        return
    for name in sorted(os.listdir(src_dir)):
        if os.path.isfile(os.path.join(src_dir, name, "__init__.py")):
            yield name


def _install_mod_meta(package, mod_id, mod_name):
    """Register `<package>._mod_meta`, the module `zwm build` generates from meta.xml."""
    full_name = "{0}._mod_meta".format(package)
    if full_name in sys.modules:
        return
    module = types.ModuleType(str(full_name))
    module.MOD_ID = mod_id
    module.MOD_NAME = mod_name
    # Placeholders: a test compares with these names, so a new release changes no test.
    module.MOD_VERSION = "<stub:version>"
    module.MOD_AUTHOR = "<stub:author>"
    module.MOD_URL = "<stub:url>"
    sys.modules[full_name] = module


def _install_shared_modules(package, shared_dir, names):
    """Load each shared module as `<package>.<name>`, the place where `zwm build` puts it.

    Only the modules that the mod takes, the same set that `zwm build` ships: what the mod
    imports, closed over what those modules import. Python finds a module in sys.modules
    before it searches a path, so nothing in src/ can hide a module loaded here.
    """
    if not names:
        return
    # The relative `from ._mod_meta import ...` in a shared module needs its package loaded.
    parent = importlib.import_module(package)
    for name in names:
        full_name = "{0}.{1}".format(package, name)
        if full_name in sys.modules:
            continue
        module = imp.load_source(str(full_name), os.path.join(shared_dir, "{0}.py".format(name)))
        setattr(parent, name, module)


def _install_stand_in_package(name):
    """Register an empty package to hold the shared modules while their own tests run."""
    if name not in sys.modules:
        package = types.ModuleType(str(name))
        package.__path__ = []
        sys.modules[name] = package
    return name


def _install_game_stubs():
    for name, attributes in sorted(GAME_STUB_MODULES.items()):
        if name in sys.modules:
            continue
        _install_parent_packages(name)
        module = types.ModuleType(str(name))
        for attribute, value in attributes.items():
            setattr(module, attribute, value)
        sys.modules[name] = module
        # A stubbed `a.b` must also be reachable as an attribute of package `a`.
        if "." in name:
            parent_name, child = name.rsplit(".", 1)
            parent = sys.modules.get(parent_name)
            if parent is not None:
                setattr(parent, child, module)


def _install_parent_packages(name):
    """Register the empty packages above a dotted stub name.

    `from gui.Scaleform.daapi.settings.views import VIEW_ALIAS` imports every package in
    the chain, so a stub of the leaf alone still raises ImportError. None of these parents
    exist outside the client, so an empty module is all they need to be.
    """
    parts = name.split(".")[:-1]
    walked = []
    for part in parts:
        walked.append(part)
        parent_name = ".".join(walked)
        if parent_name in sys.modules:
            continue
        package = types.ModuleType(str(parent_name))
        package.__path__ = []
        sys.modules[parent_name] = package
        if len(walked) > 1:
            setattr(sys.modules[".".join(walked[:-1])], part, package)
