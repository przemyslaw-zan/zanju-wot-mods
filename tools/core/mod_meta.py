"""Single source of truth for reading authored mod meta.xml files.

meta.xml is the optional WoT package manifest (World of Tanks: Mod Packages
spec). When present it holds the package <id>, <version>, and <name>. All
repository scripts read it through this helper so the authored meta.xml stays
the only source of these values.

The spec also allows <description>, which this repo does not author: nothing in
the tooling consumed it, and it shipped inside every package as a second copy of
text the mod READMEs already own.
"""

import os
import xml.etree.ElementTree as ET

from .paths import MODS_DIR

# The author that Mod Menu shows under the name of each mod, and the page that it links to. meta.xml
# has no field for them.
MOD_AUTHOR = "Zanju"
MOD_URL = "https://github.com/przemyslaw-zan/zanju-wot-mods/issues"
# The brand at the start of each <name>. A list of the mods leaves it out, because every row has it.
_MOD_NAME_PREFIX = "Zanju's "


def meta_path_for(mod_name):
    return os.path.join(MODS_DIR, mod_name, "meta.xml")


def read_meta(mod_name):
    root = ET.parse(meta_path_for(mod_name)).getroot()
    return {
        "id": root.findtext("id", "").strip(),
        "version": root.findtext("version", "0.0.0.0").strip(),
        "name": root.findtext("name", "").strip(),
    }


def display_name(mod_name):
    """The name of a mod in a list of the mods: its <name> without the brand, or the folder name."""
    name = read_meta(mod_name)["name"]
    if name.startswith(_MOD_NAME_PREFIX):
        name = name[len(_MOD_NAME_PREFIX) :]
    return name or mod_name
