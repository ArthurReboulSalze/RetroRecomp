# Interface and generated-game languages

The converter contains English, French, Italian, Spanish, German,
Simplified Chinese, Japanese and Russian, selected from its header. Generated
games carry the five Latin-script languages (English, French, Italian, Spanish,
German) and cycle through them with **F7**, without opening a selection menu.
A converter set to Chinese, Japanese or Russian generates games that start in
English; their glyph tables made every game larger and read poorly in the
small menus. Game menus draw plain ASCII: accents are dropped (German umlauts
become ae/oe/ue), so games carry no glyph table.

The choice is saved in each console folder's `datas/Retro-Recomp.ini`, under
`[Interface] language`, using the stable IDs `en/fr/it/es/de` (`zh/ja/ru`
remain converter-only IDs; a game reading one falls back to English).
Game Boy also retains its runtime preferences in
`datas/Retro-Recomp-GameBoy.ini`; the common language setting takes precedence
and F7 updates both. Display settings, bindings and other entries are preserved.
These options translate Retro-Recomp's menus, not a cartridge's dialogue.
Window execution labels remain English (`Native code` / `Interpreter fallback`).

Translation sources are `smsrecomp/i18n.py` for the original converter EN/FR
strings and `assets/locales/*.json` for additional converter/runtime text.
All runtime adapters use the shared catalogue and ASCII drawing service in
`native/retro_menu.c`; stray accented Latin-1 letters fall back to their base
letter and other characters to `?`. Existing language IDs 0/1 remain EN/FR; new IDs append
without changing controller settings. Format placeholders are checked before
the generated catalogue is accepted.

The converter privately loads two renamed Noto font subsets for its own process.
Windows retains its original Segoe UI face for Latin languages and Russian;
only Chinese/Japanese select the matching subset. Linux retains the Noto-based
interface. Tooltips follow the active interface font. No system fonts are
installed or replaced. Exported games contain no Noto glyphs: their menus use
the public-domain X.Org Misc Fixed 10x20 bitmap (printable ASCII, 3,840 bytes),
drawn for the window's scale by area coverage on Windows and Linux alike.
`tools/build_languages.py` regenerates the five-language ASCII game catalogue.
Final executable size also depends on the catalogue, license notice and packing.
See the retained [Noto license](../licenses/Noto.md).

`tools/build_languages.py` regenerates the C catalogue. To also regenerate the
converter's font subsets, install fontTools in a development environment and
pass `--cjk <NotoSansCJK-Regular.ttc>`.
Full source fonts stay outside the public snapshot. Python tests check complete
UI catalogues, placeholders, stable settings and glyph coverage.
`tools/language_selftest.py` compiles and renders an authored eight-language
menu sheet without a commercial ROM. Console witnesses then validate the actual
generated hosts; CPU/reference agreement and physical hardware/latency remain
separate measurements.
