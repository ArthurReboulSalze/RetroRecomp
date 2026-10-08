# Box art and game icons

RetroRecomp uses the same icon pipeline for Master System, Game Gear, Game Boy
and NES, plus the experimental Mega Drive and SNES profiles. Select **Options → Box art** to configure online sources.
Front covers are the default; real three-quarter boxes are an optional preference.
Icons are embedded during conversion;
existing game executables need regeneration to receive a different icon.

## Source order

1. An explicitly selected image.
2. Previously validated online covers in the converter's `datas/BoxArt/<console>`,
   matching the console, ROM identity and requested style.
3. Configured services: ScreenScraper, TheGamesDB, then IGDB.
4. The public Libretro `Named_Boxarts` library on GitHub, with the
   [Libretro thumbnail server](https://docs.libretro.com/guides/roms-playlists-thumbnails/#thumbnails)
   as an alternative host for both images and catalogue lookup.
5. Matching local artwork in the console's BoxArt directory, if online boxes
   are unavailable.
6. If no usable box art exists, the matching console's `Named_Titles` image,
   then its `Named_Snaps` image. No API credentials are needed for these sources.

Configured APIs select only box/front-cover media. Fan art, logos, cartridge
images, back covers and mixed-media compositions are excluded from API searches.
Public title screens and in-game images are used only after cover sources fail;
the log and icon report identify them as fallback images, not box art.
The console is checked in the service response as well as the request. Title
matching preserves sequel numbers: a similarly named sequel is not a cover
match. Ambiguous game identities or unidentified front-cover editions are
skipped rather than selecting the first search result.
Trailing articles keep their regional tags during exact matching:
`The Game (USA)` can select `Game, The (USA)` without confusing other editions.

Local images are read without changing them. Downloaded images are validated,
limited to 8 MiB and 16 million pixels, converted to PNG and cached locally.
**Prefer online box art** is enabled by default. Automatic matches from local
collections can be mixed-media compositions, so a real online cover takes
priority. An explicitly selected image always keeps priority.
Disabling **Prefer online box art** prevents all cover network requests;
existing local images and downloads remain usable offline. Missing artwork or
network failures do not prevent a game conversion.
Within one search, a blocked host is not retried for every image type. A failed
GitHub request can use the public server without a GitHub API catalogue.

Downloaded artwork is retained under `datas/BoxArt/<console>/Downloaded` beside
the converter. A small `Saved` record associates each ROM's SHA-256 with its image
using relative paths. Regeneration reuses the validated image before browsing local
collections or making any network request, even after a ROM rename, a new export
folder, a converter restart or changes to API credentials. Moving the app together
with `datas` preserves the cache. Conversions share this behavior across all consoles.

Changing the box-style preference looks for the saved version of that style first.
If it is missing, an online search can fetch it; switching back reuses the earlier
version. Separate image-content directories prevent one download from overwriting
another style or revision. Older named downloads remain readable and are indexed
on first reuse. The former Master System cache at `datas/BoxArt/Downloaded` is
imported into `datas/BoxArt/sms` without changing the old files or borrowing another
console's artwork. The converter never writes to the source ROM/boxart library.

A cached 3D box can be replaced with a Libretro front even without API accounts.
An online search in front-cover mode never reuses a known 3D box, even after a
failed style refresh. It continues with the other sources and fallback media.
The old box stays available for offline use or an explicit 3D preference; a later
online conversion can retry the front search. Offline use needs no request.
Cached title screens and screenshots are also reused during regeneration. New API
settings or an older image-policy marker do not trigger another download. A manual
image selection always overrides saved artwork. Missing, damaged or checksum-mismatched
images fall back to the regular search; empty cache lookups create no files.
To request artwork again, remove that game's cached image and its `Saved` record.

## Official service access

| Source | Access needed | Artwork used |
| --- | --- | --- |
| [ScreenScraper](https://www.screenscraper.fr/webapi2.php) | Developer ID and developer password; optional user name/password | Front covers by default; optional real 3D boxes with a front fallback; region preference follows the ROM name |
| [TheGamesDB](https://api.thegamesdb.net/) | TheGamesDB API key | Front box art for the matching console and exact title |
| [IGDB](https://api-docs.igdb.com/#account-creation) | Twitch application Client ID and Client Secret | Platform-filtered front covers |
| [ArcadeItalia](https://adb.arcadeitalia.net/service_scraper.php) | Its documented MAME API is public; no key is required | Reference only for now: the current console profiles are outside this API's scope |
| [Libretro](https://github.com/libretro-thumbnails/libretro-thumbnails) | None | Console-specific front box art; title screen or game image as last resort; GitHub and public thumbnail server |

Ordinary website accounts alone do not supply the developer access needed by
the first three APIs. The options page links to each service's access
documentation. ScreenScraper developer credentials must be obtained from that
service; IGDB uses a registered Twitch application, not an IGDB user password.
RetroRecomp does not bundle shared credentials or borrow credentials from other
scraper applications.

ArcadeItalia is shown in the same options selector with its documentation and
scope. It is deliberately not queried for Master System, Game Gear, Game Boy or
NES: an arcade game with the same name is not the console edition's box art.

Requests to each authenticated provider are serialized across concurrent game
conversions. API calls are spaced apart, and authentication/quota refusals cause
a temporary backoff. IGDB application tokens stay in memory. Provider failures
fall through to the next usable source.

The Libretro catalogue uses the GitHub tree API rather than a directory listing
limited to 1,000 files. A complete, filtered catalogue is cached for seven days;
truncated responses are rejected. Each console uses its own repository and cache.

## Front covers and optional three-quarter boxes

**Prefer real three-quarter boxes** is disabled by default. Automatic online
searches request front covers. Enable the option to look for real 3D images,
including their original spine and transparency. ScreenScraper then prefers
that media type and prefers PNG among equivalent editions. An explicitly saved
preference is retained across updates.

When only a front cover exists, RetroRecomp uses it flat. No spine, perspective,
border or decoration is generated. Local artwork retains its existing silhouette.

Explicitly selected images and local artwork keep their original appearance;
a three-quarter local image is not reshaped into a fabricated front. All icons preserve the full
image's aspect ratio within a transparent square. The ICO contains 16, 20, 24,
32, 40, 48, 64, 128 and 256 pixel sizes. The optional shooting badge remains a
separate, small overlay for applicable Master System games.

ScreenScraper selects the largest image for the preferred box type and edition,
without requesting thumbnail dimensions. TheGamesDB uses its original image URL
when supplied. IGDB uses its documented 1080p Fit image size, preserving the entire
front. The original download stays in the local cache. Every icon frame is rendered
directly from the full source, avoiding repeated scaling through a small thumbnail.
Transparent margins are trimmed so the cover uses the available icon area.

Windows Explorer's extra-large icon list uses 256 physical pixels, as described in
[Microsoft's icon documentation](https://learn.microsoft.com/en-us/windows/win32/menurc/about-icons).
The converter supplies a 256 × 256 frame along with the smaller sizes. Increasing
the source resolution improves detail up to that limit; enlarging a tiny source
cannot restore missing detail.

Icon generation only runs during conversion; it adds no rendering work or API
dependency to the generated game's runtime.

## Private settings and provenance

API settings live in the converter's `datas/cover-sources.json`, separate from
general preferences and game settings. Credential fields are encrypted with
Windows DPAPI for the current Windows account. Moving the file to another
account may require entering credentials again. Loading empty/default settings
does not create a file. Removing all credentials removes the encrypted payload.

Credentials are never included in generated games, icon reports, cache metadata
or publication resources. Authenticated request URLs and raw API error responses
are not logged. In the packaged Windows transport, private request details are
sent to curl through stdin rather than command-line arguments.

ScreenScraper receives the ROM filename, console ID, size, CRC32 and SHA-1 for
identification. Other cover sources receive the game name and console. ROM bytes
and local paths are never uploaded.

Each cached image has a `.png.json` sidecar with provider, public source page,
image hash, download date and media style. Authenticated media addresses are
discarded. Conversion reports identify real 3D sources, original source dimensions
and the largest icon size. All caches stay local; source ROM/cover directories can be
read-only. None of these downloads or private settings belongs in a release.

## Verification

Unit tests use authored image fixtures and simulated API replies to check exact
console/title matching, media filters, private transport, encrypted storage,
provider failures, offline caches and the 3D icon resource pipeline. The GUI
initialization check covers the four service panels in English and French.

On 7 October 2026, public downloads of Super Mario Land, Tetris and Lazlos' Leap
were validated, and Factory Panic's existing Game Gear download was read
successfully. The live Game Boy catalogue contained 1,647 box-art entries.
An isolated packaged-converter test then generated Alex Kidd in Miracle World
(Master System), Factory Panic (Game Gear), Super Mario Land (Game Boy) and
Super Mario Bros. (NES), each with a newly downloaded Libretro front cover and
an initially generated three-quarter box icon. That synthetic-box behavior was
subsequently removed: the same front artwork now stays flat. The test used empty local artwork and learning
folders, local ROM copies and no Batocera access. All nine embedded icon sizes
matched their compiled ICO resources in each EXE. Final coverage probes recorded
zero interpreter cycles and the respective CPU reference checks passed on their
tested scenarios; visual gameplay and physical latency were not measured.
Authenticated APIs still require user-supplied credentials for a live account
test; fixture checks are not a claim of live authenticated validation.

On 8 October 2026, seven Mega Drive exports with missing art received real
front covers from the public collection. A live download with GitHub deliberately
unavailable also succeeded through the thumbnail server. Synthetic fixtures
cover title-screen/snapshot fallback, offline reuse, later cover replacement,
exact regional article matching and rejection of similarly named sequels.
Existing game code is retained when replacing only icon resources locally.

Later that day, a fresh-client lookup with no local artwork, download cache or
API account found the SNES front covers for A Link to the Past and Super Metroid
in the public Libretro collection (512 × 357 pixels each). The two icon-only
updates retained identical native `.text`, cartridge data, identity, notices and
Windows metadata, with all nine ICO sizes verified. Automatic online priority,
manual selection, local fallback and cache reuse are covered by fixtures.

Seven older Mega Drive three-quarter icons were also replaced with public front
covers, preserving their regional editions and shooting tags. All nine icon
sizes and unchanged native code/cartridge/metadata resources were checked;
the other 39 game exports were untouched. Front-mode fixtures also reject a
known 3D cache after a failed refresh, including metadata written by the older
policy, and reject a provider returning a 3D image for a front request.

Persistent-cache fixtures exercise all six consoles with authored ROM/image data:
regeneration after ROM rename with network and directory browsing blocked, relative
paths after moving the cache, image corruption recovery, legacy SMS migration and
face/3D reuse. No commercial ROM or cover is included in these fixtures.

```powershell
python -X utf8 -m unittest discover -s tests
python -X utf8 tools/gui_smoke.py
```
