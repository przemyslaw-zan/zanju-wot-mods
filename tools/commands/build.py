"""
Package mods under mods/<name>/ into .wotmod archives.

Usage:
    zwm build --all                  # build all mods under mods/
    zwm build research-progress-bar  # build one specific mod
    zwm build mod-a mod-b            # build selected mods
    zwm build --no-companion-bundle research-progress-bar
    zwm build --verbose research-progress-bar
    python -m tools.commands.build research-progress-bar

Output: dist/<mod-id>_<version>/mods/<target_wot_version>/<mod-id>_<version>.wotmod

Each run empties dist/ before it builds. Thus dist/ holds only the mods of the last run, also when that
run built one mod.

Optional prebuild hooks:
- If mods/<name>/ui/compile_ui.py exists, it is run before packaging that mod.
- Generated packaged assets should land under mods/<name>/ui/build/res/.
- The build tool stages both mods/<name>/res/ and generated ui/build/res/ into the final archive.

Internal .wotmod layout:
    meta.xml                                (authored manifest: id/version/name)
    LICENSE.md                              (repo-root license, when present)
    res/scripts/client/gui/mods/<file>.pyc  (compiled from mods/<name>/src/)
    res/scripts/client/gui/mods/<pkg>/_mod_meta.pyc  (generated from meta.xml: MOD_ID/MOD_NAME/MOD_VERSION, with MOD_AUTHOR/MOD_URL)
    res/scripts/client/gui/mods/<pkg>/<name>.pyc     (compiled from mods-common/<name>.py, when the mod imports it)
    res/gui/gameface/mods/<namespace>/<name>.js      (copied from mods-common/gameface/<name>.js, when the mod imports it)
    res/...                                 (from mods/<name>/res/ plus generated ui/build/res/)

Additional release output:
    dist/<mod-id>_<version>/<mod-id>_<version>.zip
    dist/<mod-id>_<version>/mods/<target_wot_version>/<mod-id>_<version>.wotmod

Neither config nor localisation ships as loose files. Each mod self-creates its config
in AppData on first run (so settings survive modpack reinstalls), and translations are
bundled inside the .wotmod (so end users get no loose files alongside the package).

Authored source layout:
    mods/<name>/i18n/*.yml                 →  res/mods/<meta.id>/text/*.yml (inside the .wotmod)
    mods-common/i18n/*.yml                 →  added to the end of those files: the shared keys the mod uses
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from ..core import mods_common
from ..core.companion_artifacts import resolve_bundle_artifacts_if_defined, should_include_companion_bundle
from ..core.console import detail, section, success, warning
from ..core.env import load_env
from ..core.i18n_audit import TEMPLATE_FILE_NAME, shared_lines_for
from ..core.mod_assets import (
    copy_tree_contents,
    directory_has_entries,
)
from ..core.mod_cli import ensure_mod_dirs_exist, parse_companion_targeting_args, resolve_mod_targets, run_entrypoint
from ..core.env import subprocess_env
from ..core.mod_meta import MOD_AUTHOR, MOD_URL, read_meta
from ..core.paths import DIST_DIR, LICENSE_PATH, MODS_DIR
from ..core.wot_version import resolve_target_wot_version

# The build runs inside the toolchain image; Python 2.7 lives at this path there.
DEFAULT_PY2_EXE = "/opt/python2.7/bin/python2.7"


def compile_py2_to_pyc(py2_exe, src_path, out_pyc_path, dfile):
    """Compile one module to Python 2 bytecode, recording `dfile` as its source path.

    WoT runtime for this client/mod stack expects Python 2 bytecode.

    `dfile` is the third argument py_compile takes, and it decides what the bytecode carries as
    its own filename -- which is what a traceback prints. Left out, Python records the path it
    compiled from, so every traceback a mod logs in the game names a directory that exists only
    on the machine that built it. Pass the path inside the .wotmod instead: the game's own
    bytecode carries a path relative to its package root, and a reader of game.log can find
    the file that way.
    """
    cmd = [
        py2_exe,
        "-c",
        "import py_compile,sys; py_compile.compile(sys.argv[1], sys.argv[2], sys.argv[3])",
        src_path,
        out_pyc_path,
        dfile,
    ]
    subprocess.check_call(cmd, env=subprocess_env())


def assert_no_build_paths(package_path):
    """Fail the build if the package carries a path from the machine that built it.

    Compiled bytecode records where it was compiled from, and a traceback prints that path, so
    a mod that logs an exception in the game used to name a directory on the build machine. The
    compile step passes the in-package path instead, and this is the check that it kept doing
    so -- the leak was silent for four releases, and only a log a player sent in exposed it.

    Scans everything rather than the bytecode alone: a generated resource can leak the same way
    and would read exactly as badly.
    """
    root = os.path.dirname(MODS_DIR).encode("utf-8")
    if not root or root == b"/":
        return
    with zipfile.ZipFile(package_path) as zf:
        for entry in zf.namelist():
            if root in zf.read(entry):
                raise RuntimeError(
                    "{} leaks the build path {} -- see compile_py2_to_pyc".format(
                        entry, root.decode("utf-8")))


def run_optional_prebuild(mod_dir, verbose=False):
    hook_path = os.path.join(mod_dir, "ui", "compile_ui.py")
    if not os.path.isfile(hook_path):
        return

    cmd = [sys.executable, hook_path]
    if not verbose:
        cmd.append("--quiet")
    detail("Running prebuild hook: {}".format(os.path.basename(hook_path)), verbose=verbose)
    subprocess.check_call(cmd)


def stage_i18n_resources(mod_dir, mod_id, staged_res_dir):
    i18n_dir = os.path.join(mod_dir, "i18n")
    text_dir = os.path.join(staged_res_dir, "mods", mod_id, "text")
    if os.path.isdir(i18n_dir):
        legacy_text_dir = os.path.join(mod_dir, "res", "mods", mod_id, "text")
        if directory_has_entries(legacy_text_dir):
            raise RuntimeError(
                "{} defines both i18n/ and res/mods/{}/text/; keep exactly one localisation source.".format(
                    os.path.basename(mod_dir),
                    mod_id,
                )
            )

        # The translation template is a repository-only aid for translators, not a language.
        copy_tree_contents(i18n_dir, text_dir, ignore_names=(TEMPLATE_FILE_NAME,))
    stage_shared_strings(os.path.basename(mod_dir), text_dir)


def stage_shared_strings(mod_name, text_dir):
    """Add the shared keys that the mod uses to the end of its staged language files.

    A language that the mod does not have gets a file with the shared keys only. The game merges
    the English file under it, so the other keys of the mod stay in English.
    """
    for code, lines in sorted(shared_lines_for(mod_name).items()):
        path = os.path.join(text_dir, "{}.yml".format(code))
        text = ""
        if os.path.isfile(path):
            with io.open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            if text and not text.endswith("\n"):
                text += "\n"
            text += "\n"
        text += "# Shared strings, from mods-common/i18n/{}.yml\n".format(code)
        text += "\n".join(lines) + "\n"
        os.makedirs(text_dir, exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as handle:
            handle.write(text)


def stage_resource_trees(mod_dir, mod_id, staged_res_dir):
    copy_tree_contents(os.path.join(mod_dir, "res"), staged_res_dir)
    stage_i18n_resources(mod_dir, mod_id, staged_res_dir)
    copy_tree_contents(os.path.join(mod_dir, "ui", "build", "res"), staged_res_dir)


def clear_dist_dir():
    """Empty dist/, so that it holds only what this run builds.

    This removes the entries in dist/ but keeps dist/ itself. A shell whose working directory is
    dist/ thus keeps a directory that exists.
    """
    os.makedirs(DIST_DIR, exist_ok=True)
    for name in os.listdir(DIST_DIR):
        path = os.path.join(DIST_DIR, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def write_release_zip(bundle_root, bundle_name):
    mods_dir = os.path.join(bundle_root, "mods")
    zip_path = os.path.join(bundle_root, "{}.zip".format(bundle_name))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for dirpath, dirnames, filenames in os.walk(mods_dir):
            dirnames[:] = sorted(dirnames)
            for filename in sorted(filenames):
                abs_path = os.path.join(dirpath, filename)
                archive_path = os.path.relpath(abs_path, bundle_root).replace(os.sep, "/")
                zf.write(abs_path, archive_path)

    return zip_path


def create_release_bundle(mod_name, target_wot_version, output_path, include_companion_bundle=False):
    archive_name = os.path.basename(output_path)
    bundle_name = os.path.splitext(archive_name)[0]
    bundle_root = os.path.join(DIST_DIR, bundle_name)
    package_dir = os.path.join(bundle_root, "mods", target_wot_version)
    os.makedirs(package_dir, exist_ok=True)

    bundled_output_path = os.path.join(package_dir, archive_name)
    if os.path.normcase(os.path.abspath(output_path)) != os.path.normcase(os.path.abspath(bundled_output_path)):
        shutil.copy2(output_path, bundled_output_path)

    companion_artifacts = []
    if include_companion_bundle:
        companion_artifacts = stage_companion_bundle(package_dir, mod_name)

    write_release_zip(bundle_root, bundle_name)
    return bundle_root, companion_artifacts


def stage_companion_bundle(package_dir, mod_name):
    companion_artifacts = resolve_bundle_artifacts_if_defined(mod_name)
    for item in companion_artifacts:
        shutil.copy2(item["path"], os.path.join(package_dir, item["artifact"]["filename"]))
    return companion_artifacts


def iter_python_source_files(src_dir):
    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = sorted(name for name in dirnames if name != "__pycache__")
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, src_dir)
            yield abs_path, rel_path


def iter_internal_packages(src_dir):
    """Yield immediate sub-package dirs of src/ (those holding an __init__.py)."""
    if not os.path.isdir(src_dir):
        return
    for name in sorted(os.listdir(src_dir)):
        pkg_dir = os.path.join(src_dir, name)
        if os.path.isfile(os.path.join(pkg_dir, "__init__.py")):
            yield name


def render_mod_meta_module(meta):
    return (
        "# -*- coding: utf-8 -*-\n"
        '"""Generated at build time from meta.xml. Do not edit; not committed."""\n'
        "from __future__ import unicode_literals\n"
        "\n"
        "MOD_ID = {id}\n"
        "MOD_NAME = {name}\n"
        "MOD_VERSION = {version}\n"
        "MOD_AUTHOR = {author}\n"
        "MOD_URL = {url}\n"
    ).format(
        id=json.dumps(meta["id"]),
        name=json.dumps(meta["name"]),
        version=json.dumps(meta["version"]),
        author=json.dumps(MOD_AUTHOR),
        url=json.dumps(MOD_URL),
    )


def bundle_generated_mod_meta(src_dir, meta, temp_dir, py2_exe, zf):
    """Compile a meta-derived _mod_meta module into each internal package.

    Keeps meta.xml the single authored source of MOD_ID/MOD_NAME/MOD_VERSION: the
    runtime imports these from the generated module instead of hardcoding them.
    """
    source = render_mod_meta_module(meta)
    for package in iter_internal_packages(src_dir):
        py_path = os.path.join(temp_dir, "gen", package, "_mod_meta.py")
        os.makedirs(os.path.dirname(py_path), exist_ok=True)
        with open(py_path, "w", encoding="utf-8") as fh:
            fh.write(source)
        pyc_path = "{}c".format(py_path)
        archive_path = "res/scripts/client/gui/mods/{}/_mod_meta.pyc".format(package)
        compile_py2_to_pyc(py2_exe, py_path, pyc_path, archive_path[:-1])
        zf.write(pyc_path, archive_path)


def bundle_shared_modules(mod_name, src_dir, temp_dir, py2_exe, zf, built_together, verbose=False):
    """Compile each shared module this mod takes into each internal package.

    The module lands at the path an in-tree copy would have, under the mod's own package. Thus
    two mods that take the same module do not share a file or a module object in the game.
    """
    names = mods_common.modules_for(mod_name)
    for package in iter_internal_packages(src_dir):
        for name in names:
            pyc_path = os.path.join(temp_dir, "shared", package, "{}.pyc".format(name))
            os.makedirs(os.path.dirname(pyc_path), exist_ok=True)
            archive_path = "res/scripts/client/gui/mods/{}/{}.pyc".format(package, name)
            compile_py2_to_pyc(py2_exe, mods_common.module_path(name), pyc_path, archive_path[:-1])
            zf.write(pyc_path, archive_path)
            detail("Shared module: {}".format(archive_path), verbose=verbose)

    # A partial build leaves the other mods that take a module with their old copy. That is
    # safe, but a change to the module is then not in them yet.
    for name in names:
        left_out = [other for other in mods_common.consumers_of(name) if other not in built_together]
        if left_out:
            warning(
                "Shared module {} also goes into {}. If you changed {}, build {} too.".format(
                    name, ", ".join(left_out), name, "them" if len(left_out) > 1 else "it"
                )
            )


def stage_shared_scripts(mod_name, staged_res_dir, built_together, verbose=False):
    """Copy each shared Gameface script this mod takes into the mod's one Gameface folder.

    The script lands beside the mod's own modules, so `import ... from './tray.js'` finds it in
    the game. Each mod thus carries its own copy at its own path, the same rule as for the shared
    Python modules.
    """
    names = mods_common.scripts_for(mod_name)
    if not names:
        return
    namespace = mods_common.gameface_namespace(mod_name)
    target_dir = os.path.join(staged_res_dir, "gui", "gameface", "mods", namespace)
    os.makedirs(target_dir, exist_ok=True)
    for name in names:
        shutil.copy2(mods_common.script_path(name), os.path.join(target_dir, "{}.js".format(name)))
        detail("Shared script: res/gui/gameface/mods/{}/{}.js".format(namespace, name), verbose=verbose)

    for name in names:
        left_out = [other for other in mods_common.script_consumers_of(name) if other not in built_together]
        if left_out:
            warning(
                "Shared script {} also goes into {}. If you changed {}, build {} too.".format(
                    name, ", ".join(left_out), name, "them" if len(left_out) > 1 else "it"
                )
            )


def build_mod(mod_name, py2_exe, target_wot_version, include_companion_bundle=None, verbose=False, built_together=()):
    mod_dir = os.path.join(MODS_DIR, mod_name)
    if not os.path.isdir(mod_dir):
        raise RuntimeError("Mod directory not found: {}".format(mod_dir))

    section("Building {}".format(mod_name))

    run_optional_prebuild(mod_dir, verbose=verbose)

    meta = read_meta(mod_name)
    mod_id = meta["id"]
    version = meta["version"]

    if not mod_id or "yourname" in mod_id:
        warning("WARNING: {} - mod id looks like a placeholder: {}".format(mod_name, mod_id))

    output_name = "{}_{}.wotmod".format(mod_id, version)
    bundle_name = os.path.splitext(output_name)[0]
    bundle_root = os.path.join(DIST_DIR, bundle_name)
    package_dir = os.path.join(bundle_root, "mods", target_wot_version)

    os.makedirs(package_dir, exist_ok=True)
    output_path = os.path.join(package_dir, output_name)

    with (
        tempfile.TemporaryDirectory(prefix="wot-build-") as temp_dir,
        zipfile.ZipFile(output_path, "w", zipfile.ZIP_STORED) as zf,
    ):
        # WoT's package loader rejects compressed entries in some client versions.
        # Use store-only zip members for maximum compatibility.
        # meta.xml and LICENSE at archive root (spec: optional utility files).
        zf.write(os.path.join(mod_dir, "meta.xml"), "meta.xml")
        if os.path.isfile(LICENSE_PATH):
            zf.write(LICENSE_PATH, os.path.basename(LICENSE_PATH))

        # src/**/*.py  →  res/scripts/client/gui/mods/<relative-path>.pyc
        src_dir = os.path.join(mod_dir, "src")
        if os.path.isdir(src_dir):
            for abs_path, rel_path in iter_python_source_files(src_dir):
                compiled_rel_path = "{}c".format(rel_path)
                compiled_path = os.path.join(temp_dir, compiled_rel_path)
                compiled_dir = os.path.dirname(compiled_path)
                if compiled_dir:
                    os.makedirs(compiled_dir, exist_ok=True)
                archive_path = "res/scripts/client/gui/mods/{}".format(compiled_rel_path.replace(os.sep, "/"))
                compile_py2_to_pyc(py2_exe, abs_path, compiled_path, archive_path[:-1])
                zf.write(compiled_path, archive_path)
            bundle_generated_mod_meta(src_dir, meta, temp_dir, py2_exe, zf)
            bundle_shared_modules(mod_name, src_dir, temp_dir, py2_exe, zf, built_together, verbose=verbose)

        # Stage packaged resources from committed source plus generated build output.
        staged_res_dir = os.path.join(temp_dir, "staged_res")
        stage_resource_trees(mod_dir, mod_id, staged_res_dir)
        stage_shared_scripts(mod_name, staged_res_dir, built_together, verbose=verbose)
        if os.path.isdir(staged_res_dir):
            for dirpath, dirnames, filenames in os.walk(staged_res_dir):
                dirnames[:] = sorted(dirnames)
                for filename in sorted(filenames):
                    abs_path = os.path.join(dirpath, filename)
                    archive_path = "res/{}".format(os.path.relpath(abs_path, staged_res_dir).replace(os.sep, "/"))
                    zf.write(abs_path, archive_path)

    assert_no_build_paths(output_path)

    success("Package built: {}".format(output_name))
    detail("Path: {}".format(output_path), verbose=verbose)

    release_bundle_dir, companion_artifacts = create_release_bundle(
        mod_name,
        target_wot_version,
        output_path,
        include_companion_bundle=should_include_companion_bundle(mod_name, include_companion_bundle),
    )
    success("Release bundle ready")
    detail("Path: {}".format(release_bundle_dir), verbose=verbose)

    if companion_artifacts:
        success("Companion artifacts staged: {}".format(len(companion_artifacts)))
        for item in companion_artifacts:
            detail("Companion: {}".format(item["artifact"]["filename"]), verbose=verbose)


def _main():
    env = load_env()
    py2_exe = env.get("WOT_PYTHON2_EXE", "").strip() or DEFAULT_PY2_EXE
    if not os.path.isfile(py2_exe):
        raise RuntimeError(
            "Python 2.7 not found at {}. Builds run inside the toolchain image "
            "(see docs/building-from-source.md).".format(py2_exe)
        )
    target_wot_version = resolve_target_wot_version(env, require_game_dir=False)

    include_companion_bundle, run_all, verbose, targets = parse_companion_targeting_args(sys.argv[1:])
    mod_names = resolve_mod_targets(run_all, targets, "build")
    if mod_names is None:
        return
    ensure_mod_dirs_exist(mod_names)

    success("Target WoT client version: {}".format(target_wot_version))

    # The whole repository, also on a partial build: a partial build must never pass what
    # `--all` would stop on.
    mods_common.check()

    # After the checks, so that a mistyped mod name or a failed check keeps the last output.
    clear_dist_dir()

    for mod_name in mod_names:
        build_mod(
            mod_name,
            py2_exe,
            target_wot_version,
            include_companion_bundle=include_companion_bundle,
            verbose=verbose,
            built_together=mod_names,
        )


def main():
    return run_entrypoint(_main)


if __name__ == "__main__":
    main()
