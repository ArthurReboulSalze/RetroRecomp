# Box art and 3D game icons

RetroRecomp uses the same icon pipeline for Master System, Game Gear, Game Boy
and NES, plus the development Mega Drive and SNES proofs. Select **Options → Box art** to configure online sources and the
real three-quarter 3D boxes with a flat front-cover fallback. Icons are embedded during conversion;
existing game executables need regeneration to receive a different icon.

## Source order

1. An explicitly selected image.
2. Matching local artwork in the console's BoxArt directory.
3. Previously validated downloads in the converter's `datas/BoxArt/<console>`.
4. Configured services: ScreenScraper, TheGamesDB, then IGDB.
5. The public Libretro `Named_Boxarts` library, which needs no API credentials.

Only box/front-cover media are selected. Screenshots, fan art, logos, cartridge
images, back covers and mixed-media compositions are excluded from API searches.
The console is checked in the service response as well as the request. Title
matching preserves sequel numbers: a similarly named sequel is not a cover
match. Ambiguous game identities or unidentified front-cover editions are
skipped rather than selecting the first search result.

Local images are read without changing them. Downloaded images are validated,
limited to 8 MiB and 16 million pixels, converted to PNG and cached locally.
Disabling **Download missing box art** prevents all cover network requests;
existing local images and downloads remain usable offline. Missing artwork or
network failures do not prevent a game conversion.

Adding or changing API settings allows flat downloaded covers to be checked
against the configured services again. An unsuccessful check keeps the existing
cover. Local artwork remains first priority. Downloads made with the previous
thumbnail policy are checked once against configured APIs for a higher-resolution
source; subsequent offline uses and current real 3D downloads need no request.

## Official service access

| Source | Access needed | Artwork used |
| --- | --- | --- |
| [ScreenScraper](https://www.screenscraper.fr/webapi2.php) | Developer ID and developer password; optional user name/password | Real 3D boxes first, then 2D fronts; region preference follows the ROM name |
| [TheGamesDB](https://api.thegamesdb.net/) | TheGamesDB API key | Front box art for the matching console and exact title |
| [IGDB](https://api-docs.igdb.com/#account-creation) | Twitch application Client ID and Client Secret | Platform-filtered front covers |
| [ArcadeItalia](https://adb.arcadeitalia.net/service_scraper.php) | Its documented MAME API is public; no key is required | Reference only for now: the current console profiles are outside this API's scope |
| [Libretro](https://github.com/libretro-thumbnails/libretro-thumbnails) | None | Console-specific front box art |

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

## Three-quarter box presentation

**Prefer real three-quarter boxes** is enabled by default. Real 3D images, including
their original spine and transparency, are used directly. The ScreenScraper
connector prefers that media type and prefers PNG among equivalent editions.

When only a front cover exists, RetroRecomp uses it flat. No spine, perspective,
border or decoration is generated. Local artwork retains its existing silhouette.

Turn the option off to prefer front covers in service searches. All icons preserve the full
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

```powershell
python -X utf8 -m unittest discover -s tests
python -X utf8 tools/gui_smoke.py
```
