# Interface and generated-game languages

The development build contains English, French, Italian, Spanish, German,
Simplified Chinese, Japanese and Russian. The converter changes language from
its header selector. Generated games cycle directly through the same eight
languages with **F7**, without opening a selection menu.

The choice is saved in each console folder's `datas/Retro-Recomp.ini`, under
`[Interface] language`, using the stable IDs `en/fr/it/es/de/zh/ja/ru`.
Game Boy also retains its runtime preferences in
`datas/Retro-Recomp-GameBoy.ini`; the common language setting takes precedence
and F7 updates both. Display settings, bindings and other entries are preserved.
These options translate Retro-Recomp's menus, not a cartridge's dialogue.
Window execution labels remain English (`Native code` / `Interpreter fallback`).

Translation sources are `smsrecomp/i18n.py` for the original converter EN/FR
strings and `assets/locales/*.json` for additional converter/runtime text.
All runtime adapters use the shared catalogue and UTF-8 drawing service in
`native/retro_menu.c`. Existing language IDs 0/1 remain EN/FR; new IDs append
without changing controller settings. Format placeholders are checked before
the generated catalogue is accepted.

The converter privately loads two renamed Noto font subsets for its own process.
Windows retains its original Segoe UI face for Latin languages and Russian;
only Chinese/Japanese select the matching subset. Linux retains the Noto-based
interface. Tooltips follow the active interface font. No system fonts are
installed or replaced. Exported games contain only the small menu
glyph atlas, alongside their original ASCII rendering. The complete CJK source
font is not copied into games. The current extended atlas has 437 characters
and 39,024 alpha bytes; the generated C source file is larger than that payload.
CJK and Cyrillic bitmaps are one third smaller than the initial atlas, with
the existing line height preserved. ASCII and accented Latin glyphs retain
their original sizes. This adjustment applies to Windows and Linux games;
the converter's font subsets are unchanged.
Final executable size also depends on the catalogue, license notice and packing.
See the retained [Noto license](../licenses/Noto.md).

`tools/build_languages.py` regenerates the C catalogue. To also regenerate font
subsets/glyphs, install Pillow and fontTools in a development environment and
pass `--cjk <NotoSansCJK-Regular.ttc> --mono <NotoSansMono-Regular.ttf>`.
Add `--runtime-only` to update game glyphs without rebuilding converter fonts.
Full source fonts stay outside the public snapshot. Python tests check complete
UI catalogues, placeholders, stable settings and glyph coverage.
`tools/language_selftest.py` compiles and renders an authored eight-language
menu sheet without a commercial ROM. Console witnesses then validate the actual
generated hosts; CPU/reference agreement and physical hardware/latency remain
separate measurements.
