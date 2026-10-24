# Compiled games

Since 1.1.8, a controller can browse the visible game list
with the D-pad or left stick. **A** launches the selected game; the **Play**
button, Enter and double-click remain available. Holding a direction repeats
after a short delay. Navigation pauses whenever a game is running, a dialog is
open or the converter loses focus; release held buttons before resuming. It
uses the same small SDL2 controller bridge on Windows and Linux. This requires
no additional Python package or controller remapping in the converter.

The collection is restored from `datas/compiled-games.json` beside Retro-Recomp.
It keeps export paths, exact console/cartridge identities, source paths and
favorites. No executable or ROM scan is needed at startup. An explicit scan
updates the collection and removes entries whose files are confirmed missing.
Unavailable drives or unreadable folders stay listed so an offline library is
not lost. Cancelled or incomplete scans do not prune entries. Click the star, sort its
column or enable Favorites only. Favorites survive rescans and regeneration.

The inventory remembers the converter's base folder. Moving the app together
with `Games` and `datas` rebases its own game/report paths and scan folders;
external libraries and ROM folders keep their own locations. No scan
of game contents is required on reopening. Older inventories are repaired in a
background task when opening Compiled Games, using copied reports or matching
exact console/cartridge entries. A matching name alone is insufficient. Stale
aliases merge into the local entry, retaining favorites. A copy of the original
inventory is kept as `datas/compiled-games.before-path-migration.json`.
Two existing exports in separate folders remain separate collection entries.

## Keeping the list current

Each row remembers the sizes and dates of the files it shows: the game, its
report and its gameplay hints. When a game launched with **Play** closes, its
row is read again at once, so discoveries saved on exit appear without a
scan. When the collection is shown or the window regains focus, only rows
whose files changed are read again (about 0.2 s for 1,068 unchanged games).
**Scan games** still walks every folder, for new folders and moved games.

**New paths (N)**, one toolbar button shared by both views, reconverts only
the games whose play found new paths since their last conversion, upgrading them without rediscovery when nothing else
changed. Games whose ROM cannot be found are left for later. When
Retro-Recomp closes with such games on Master System, Game Gear, Game Boy,
NES, Mega Drive or Super Nintendo, a card offers the same recompilation
before closing. Its **Send and close** button, like **Send to the shared
Retro-Recomp base** in the Knowledge menu, stays disabled until the
connection to the Retro-Recomp web server and database exists.

## Toolbar

The queue/collection switch is the toolbar's first button and keeps its place
and width. It reads **Compiled Games** in the conversion queue and
**Conversion queue** in the collection. The buttons of the visible view follow
it: **Add ROMs…**, then pictures for Add games ROM folder (a folder with a
cartridge), Remove and Clear list in the queue; **Play game**, then pictures
for Scan games, Add games exe folder (a folder with a play sign) and Stop in
the collection. A picture's hover hint names it first. **New paths (N)**
comes next in both views. The **Knowledge** menu, Options, updates and
credits stay on the right. Every language fits at the default window
width. While games are being reconverted, the last two converter lines appear
quietly under the progress bar.

When the ROMs you add (files, a folder or a mixed drop) include games that
already have an export in the output folder, the queue asks once whether to
keep them for a reconversion. **No** leaves them out and keeps only the games
not compiled yet, so a mixed folder needs no sorting by hand; the log says how
many were left out.

Under the cover, the game card shows a few small lines of text without a
frame or scrollbar. The mouse wheel scrolls them. Left untouched, they scroll
on their own and then return to the top.

## Finding a source again

Options includes a ROM folder for each console, on both Windows and Linux.
Reconvert tries remembered paths, other known copies and then that folder and
its subfolders. ZIPs use the same console reader as conversion; names only order
the search. The exact normalized cartridge identity must match. Neo Geo sets
are revalidated with their parent-set context. The search runs in a worker and
does not write beside ROMs. `datas/rom-index.json` caches unchanged candidates;
conversion independently checks the selected source before using it.

New conversion reports also retain `source_rom` and the published directory.
The collection retains manually relocated sources after successful validation.
An unavailable old source still needs the original cartridge, not merely a game
with the same title. Windows and Linux can have different source-folder paths.

## Covers and short summaries

The right-hand pane loads local data only when selecting a game. It tries the
converter's cached artwork and conversion report first, then exported artwork
or the Linux launcher icon. As a last resort it can read PE icon resources or
the SDL bitmap in an uncompressed ELF; it never executes the game. A compacted
standalone ELF may need its cache, exported icon or a manual cover instead.

Choose cover copies an image into the converter's private card folder. Search
online explicitly uses the existing cover sources and requires a front cover.
Both choices become an exact-game override used by subsequent conversions,
including reconversion from the collection. Reconvert updates the executable's
icon through the normal conversion checks. A new cover is never patched into
an unrelated executable. The original image may be removed after choosing it.

Find / refresh game info is **manual**. It is also available by right-clicking
one or several selected games. Bulk searches reuse existing cards, proceed one
game at a time and can stop after the current request. Opening the collection,
selecting a game or scanning executables never searches online for metadata.

Configured IGDB or TheGamesDB accounts can supply descriptions. Otherwise a
public Wikidata search restricts matches to the console and offers ambiguous
results for selection. Wikipedia's TextExtracts API can supply a short existing
introduction in the requested language, or English when available. No generated
or machine-translated synopsis is used. Descriptions are capped at 850 characters;
missing descriptions stay missing. Release dates without platform qualifiers
are labelled as the first release across platforms. Fields absent from a source
are omitted rather than invented.

Cards, covers, source attribution, original text language and retrieval date
are retained under `datas/game-cards/<console>/<exact-identity>/`. They remain
available offline and after moving an export. Wikipedia text retains its source
link and CC BY-SA attribution; Wikidata facts are CC0. API credentials remain in
the existing protected account storage and are excluded from cards.

These private display records are separate from compilation observations and
the qualified shared knowledge snapshot. They are not bundled or published.

Sources: [IGDB API](https://api-docs.igdb.com/),
[TheGamesDB API](https://api.thegamesdb.net/),
[Wikibase API](https://www.wikidata.org/w/api.php),
[TextExtracts](https://www.mediawiki.org/wiki/Extension:TextExtracts).
