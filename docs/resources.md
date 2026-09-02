# Resources And External Links

This page links to public resources that are useful for coding, debugging, migration work, and release checks.

## Source Repositories And Community Knowledge

- **WoT Modding Guide: https://modding.wot-tools.dev/** — the broadest and most careful public
  handbook, 79 pages covering lifecycle, hooks, Gameface, BigWorld, packaging and update
  migration. This repository now defers to it for everything general. Read
  [The Upstream Modding Guide](reference/upstream-guide.md) first: it lists what to use it for and
  the three claims that fail against client 2.3.1.3.
- wgmods.dev modding documentation: https://wgmods.dev/docs/wot/getting-started
  (also at https://github.com/wgmods-dev/wgmods.dev). Beginner-oriented and strongest on the
  areas this repository does not touch: battle-side APIs (`Avatar`, arena), Wwise sound events,
  vehicle icon naming, and the JPEXS workflow for editing the game's own SWFs. Its pages link a
  `wgmods-dev/wot-src` decompiled-source repository that does not exist; read the client
  directly instead, per [Reading The Client's Own Code](reference/reading-the-clients-code.md).
- Kurzdor WoT mods: https://github.com/Kurzdor/wotmods-public/
- Aslain forum: https://aslain.com/forums/
- KoreanRandom technical board: https://koreanrandom.com/forum/forum/44-mods-and-software/

## Optional Mod APIs And Shared Libraries

This repository prefers linking to third-party APIs instead of restating their documentation.
Use the upstream docs or source when an integration depends on them.

- ModsList API: https://gitlab.com/wot-public-mods/mods-list/
- ModsSettings API (Aslain's fork — bundled by this repo): https://github.com/Aslain/modssettingsapi
- ModsSettings API (izeberg original): https://bitbucket.org/IzeBerg/modssettingsapi/

## Policy And Release Gate

- Fair Play overview: https://worldoftanks.com/en/content/guide/fair_play/
- Prohibited mods: https://worldoftanks.com/en/content/guide/fair_play/prohibited_mods
- Wargaming EULA: https://legal.wargaming.net/en/user-documents/eula/end-user-license-agreement/view

## Notes

- Re-check policy pages before every public release.
- Prefer upstream API docs over local paraphrases when those APIs are maintained elsewhere.
- Treat public mods as reference implementations, not stable APIs.
