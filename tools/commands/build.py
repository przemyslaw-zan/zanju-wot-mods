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

Optional prebuild hooks:
- If mods/<name>/ui/compile_ui.py exists, it is run before packaging that mod.
- Generated packaged assets should land under mods/<name>/ui/build/res/.
- The build tool stages both mods/<name>/res/ and generated ui/build/res/ into the final archive.

Internal .wotmod layout:
    meta.xml                                (authored manifest: id/version/name)
    LICENSE.md                              (repo-root license, when present)
    res/scripts/client/gui/mods/<file>.pyc  (compiled from mods/<name>/src/)
    res/scripts/client/gui/mods/<pkg>/_mod_meta.pyc  (generated from meta.xml: MOD_ID/MOD_NAME)
    res/...                                 (from mods/<name>/res/ plus generated ui/build/res/)

Additional release output:
    dist/<mod-id>_<version>/<mod-id>_<version>.zip
    dist/<mod-id>_<version>/mods/<target_wot_version>/<mod-id>_<version>.wotmod

Neither config nor localisation ships as loose files. Each mod self-creates its config
in AppData on first run (so settings survive modpack reinstalls), and translations are
bundled inside the .wotmod (so end users get no loose files alongside the package).

Authored source layout:
    mods/<name>/i18n/*.yml                 →  res/mods/<meta.id>/text/*.yml (inside the .wotmod)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from ..core.companion_artifacts import resolve_bundle_artifacts_if_defined, should_include_companion_bundle
from ..core.console import detail, section, success, warning
from ..core.env import load_env
from ..core.i18n_audit import TEMPLATE_FILE_NAME
from ..core.mod_assets import (
    copy_tree_contents,
    directory_has_entries,
)
from ..core.mod_cli import parse_companion_targeting_args, resolve_mod_targets, run_entrypoint
from ..core.env import subprocess_env
from ..core.mod_meta import read_meta
from ..core.paths import DIST_DIR, LICENSE_PATH, MODS_DIR
from ..core.wot_version import resolve_target_wot_version

# The build runs inside the toolchain image; Python 2.7 lives at this path there.
DEFAULT_PY2_EXE = "/opt/python2.7/bin/python2.7"


def compile_py2_to_pyc(py2_exe, src_path, out_pyc_path):
    # WoT runtime for this client/mod stack expects Python 2 bytecode.
    cmd = [
        py2_exe,
        "-c",
        "import py_compile,sys; py_compile.compile(sys.argv[1], sys.argv[2])",
        src_path,
        out_pyc_path,
    ]
    subprocess.check_call(cmd, env=subprocess_env())


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
    if not os.path.isdir(i18n_dir):
        return

    legacy_text_dir = os.path.join(mod_dir, "res", "mods", mod_id, "text")
    if directory_has_entries(legacy_text_dir):
        raise RuntimeError(
            "{} defines both i18n/ and res/mods/{}/text/; keep exactly one localisation source.".format(
                os.path.basename(mod_dir),
                mod_id,
            )
        )

    # The translation template is a repository-only aid for translators, not a language.
    copy_tree_contents(
        i18n_dir,
        os.path.join(staged_res_dir, "mods", mod_id, "text"),
        ignore_names=(TEMPLATE_FILE_NAME,),
    )


def stage_resource_trees(mod_dir, mod_id, staged_res_dir):
    copy_tree_contents(os.path.join(mod_dir, "res"), staged_res_dir)
    stage_i18n_resources(mod_dir, mod_id, staged_res_dir)
    copy_tree_contents(os.path.join(mod_dir, "ui", "build", "res"), staged_res_dir)


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
    ).format(id=json.dumps(meta["id"]), name=json.dumps(meta["name"]))


def bundle_generated_mod_meta(src_dir, meta, temp_dir, py2_exe, zf):
    """Compile a meta-derived _mod_meta module into each internal package.

    Keeps meta.xml the single authored source of MOD_ID/MOD_NAME: the runtime
    imports these from the generated module instead of hardcoding them.
    """
    source = render_mod_meta_module(meta)
    for package in iter_internal_packages(src_dir):
        py_path = os.path.join(temp_dir, "gen", package, "_mod_meta.py")
        os.makedirs(os.path.dirname(py_path), exist_ok=True)
        with open(py_path, "w", encoding="utf-8") as fh:
            fh.write(source)
        pyc_path = "{}c".format(py_path)
        compile_py2_to_pyc(py2_exe, py_path, pyc_path)
        archive_path = "res/scripts/client/gui/mods/{}/_mod_meta.pyc".format(package)
        zf.write(pyc_path, archive_path)


def build_mod(mod_name, py2_exe, target_wot_version, include_companion_bundle=None, verbose=False):
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

    os.makedirs(DIST_DIR, exist_ok=True)
    if os.path.isdir(bundle_root):
        shutil.rmtree(bundle_root)
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
                compile_py2_to_pyc(py2_exe, abs_path, compiled_path)
                archive_path = "res/scripts/client/gui/mods/{}".format(compiled_rel_path.replace(os.sep, "/"))
                zf.write(compiled_path, archive_path)
            bundle_generated_mod_meta(src_dir, meta, temp_dir, py2_exe, zf)

        # Stage packaged resources from committed source plus generated build output.
        staged_res_dir = os.path.join(temp_dir, "staged_res")
        stage_resource_trees(mod_dir, mod_id, staged_res_dir)
        if os.path.isdir(staged_res_dir):
            for dirpath, dirnames, filenames in os.walk(staged_res_dir):
                dirnames[:] = sorted(dirnames)
                for filename in sorted(filenames):
                    abs_path = os.path.join(dirpath, filename)
                    archive_path = "res/{}".format(os.path.relpath(abs_path, staged_res_dir).replace(os.sep, "/"))
                    zf.write(abs_path, archive_path)

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

    success("Target WoT client version: {}".format(target_wot_version))

    for mod_name in mod_names:
        build_mod(
            mod_name,
            py2_exe,
            target_wot_version,
            include_companion_bundle=include_companion_bundle,
            verbose=verbose,
        )


def main():
    return run_entrypoint(_main)


if __name__ == "__main__":
    main()
