# Installing Mods

This page shows you how to install a ready-to-use mod. You do not build anything from source.

## What Is In The Download

The download is one zip file. It contains a `mods` folder. In that folder there is a folder with a game version number, for example `mods/2.3.1.3/`. That folder holds one or more files with the name ending in `.wotmod`.

Install all of the `.wotmod` files that you find there. Some mods need a shared component to operate, and that component comes in the same folder. If you install only one file, the mod will not work properly.

## Install A Mod

1. Close World of Tanks.
2. Open your World of Tanks game folder, then open the `mods` folder in it.
3. Open the folder with a game version number, for example `2.3.1.3`. Usually there is only one. The `mods` folder also holds other folders, such as `configs`. Do not use those.
4. Open the zip file. Go to the `mods` folder in the zip, then to the version folder in it.
5. Copy all of the `.wotmod` files from the zip into the folder from step 3.
6. If Windows asks you to replace a file, agree to the replacement.
7. Start the game and make sure that the mod loads.

Two things can make step 3 unclear. You can see more than one version folder. Or the number in the zip can be different from your number. For both cases, refer to [If The Version Numbers Are Different](#if-the-version-numbers-are-different).

## If Windows Asks To Replace A File

Agree to the replacement. It is safe. A shared component holds its own version number in the file name, for example `net.openwg.gameface_1.1.6.wotmod`. Two files with the same name always have the same content. Thus the replacement does not change the file.

## If The Version Numbers Are Different

Use this section for two cases. In the first case, the `mods` folder holds more than one version folder. In the second case, the version folder in the zip has a different number than the folder in your game. For both cases, find your game version first.

Your game folder contains a file with the name `version.xml`. Open that file with Notepad. Find the line that starts with `<version>`. The line looks like this:

```
<version> v.2.3.1.3 #926 </version>
```

The number that you need is the four-part number, `2.3.1.3` in this example. Ignore the `v.` in front of it and the `#926` after it. Use the folder in `mods` with that number.

Do not use the number that the game launcher shows. The launcher can show a different number, for example `2.3.1.5412`. Also, do not select a folder only because it has the highest number. The game can make the folder for the next game version before you play that version.

A different number in the zip shows that the release is for an older version of the game. Step 5 is still correct. Copy the files into your own version folder. Do not make a new folder for the number that you see in the zip.

First, examine the [Latest Releases](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest) index. If there is a release for your game version, install that release.

A mod for an older version usually operates correctly after a small game update. If the mod does not operate correctly, delete its `.wotmod` file. Then wait for a new release.

## Update A Mod

1. Close the game.
2. Install the new zip file with the same steps as above.
3. Agree to all the replacements that Windows asks about.
4. Start the game and make sure that the mod loads.

Your settings stay in place. The game keeps them in your WoT AppData folder, not in the mod file.

## Remove A Mod

1. Close the game.
2. Open the version folder in `mods`, for example `mods/2.3.1.3/`.
3. Delete the `.wotmod` file for the mod. That file also holds the translations, thus this step removes them too.
4. Keep the shared components if a different mod still needs them. For example, more than one mod uses `net.openwg.gameface_1.1.6.wotmod`.
5. To remove the settings too, delete the folder for the mod in your WoT AppData folder.

## More Help

- For the current list of public mods, refer to [Included Mods](../README.md#included-mods).
- To make the zip file yourself, refer to [Building From Source](building-from-source.md).
- To change the code or examine the behavior, refer to [Developing Mods](developing-mods.md).
