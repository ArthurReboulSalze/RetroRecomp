# Provenance du runtime X68000 sans GPL

Phase 0 de [X68000_GPL_FREE_PLAN.md](../../docs/history/x68000/X68000_GPL_FREE_PLAN.md), du
21 octobre 2026. La version lisible par machine est
[`provenance.json`](provenance.json) ; à partir de la phase 1, le build la
lira pour refuser tout fichier interdit. Analyse technique, pas avis juridique.

## Décision principale : base machine `74ddbb3` (hissorii, 2014)

Le plan prévoyait `ec047a3` (mai 2020). L'attribution ligne par ligne montre
qu'il vaut mieux partir du **dernier état hissorii**, `74ddbb3` (12 août 2014).
C'est exactement le HEAD actuel de
[hissorii/px68k](https://github.com/hissorii/px68k), le dépôt de l'issue 15.

Entre 2014 et mai 2020, les contributeurs libretro ont très peu touché à la
machine. Différence normalisée entre `74ddbb3` et `ec047a3` :

| Zone | Jetons changés / total | Nature |
| --- | ---: | --- |
| `fmgen/` (OPM utile) | 0 / 13 581 | identique |
| `x68k/` (24 fichiers gardés) | environ 810 / 64 000 | plomberie CPU C68K/Cyclone, journaux, RAM 12 Mio, mode de transparence graphique, détection de changement de cadence |
| `x11/windraw.c` → `libretro/windraw.c` | 4 459 / 7 572 | adaptation libretro de la sortie vidéo |
| `x11/keyboard.c` → `libretro/keyboard.c` | 1 355 / 3 158 | entrées libretro |
| `m68000/m68000.c` | 1 150 / 1 652 | plomberie CPU |

Repartir de `74ddbb3` élimine donc **toutes** les contributions libretro, avant
comme après 2020, pour un coût fonctionnel connu et faible (voir la section
« À refaire »). Les seuls ayants droit restants sont Kenjo, NONAKA, cisc,
Masaru OKI et hissorii.

## Fichiers gardés (copies de build générées, sources amont intactes)

| Origine (`74ddbb3`) | Fichiers | Conditions |
| --- | --- | --- |
| `x68k/` | adpcm, bg, crtc, dmac, fdc, fdd, disk_d88, disk_dim, disk_xdf, gvram, ioc, irqh, mem_wrap, mfp, midi, palette, pia, rtc, sasi, scc, scsi, sram, sysport, tvram (+ en-têtes) | Notice de Kenjo `doc/kero_src.txt` : réutilisation libre hors commerce. Adaptation NONAKA (xkeropi), puis hissorii. |
| `fmgen/` | fmg_wrap, fmgen, fmtimer, opm (+ en-têtes) ; opna et psg à confirmer en phase 1 | Conditions de cisc dans `readme.txt` |
| `x11/` | windraw.c (composition des lignes), keyboard.c (file clavier, interruption MFP), mouse.c (paquets souris SCC) | BSD 2 clauses, NONAKA |
| `win32api/` | dosio.c, fake.c, peace.c, seulement si les fichiers machine les appellent | BSD 4 clauses NONAKA (mention publicitaire), BSD 3 clauses OKI |

Le CPU vient de Geolith `2dc88e3` (`src/m68k`) : notices MIT de Karl Stenerud,
y compris `m68kfpu.c`, et notice BSD pour `m68kmmu.h`. Les doutes de l'audit sur
la copie Musashi de PX68k ne s'appliquent donc pas. Le code natif généré reste
notre travail sur `m68k-recomp-core` (PolyForm Noncommercial, avec la
permission de mstan).

## État de la phase 1 (21 octobre 2026)

| Fichier | Statut | Écrit à partir de |
| --- | --- | --- |
| `libretro_api.c` | écrit, MIT | [X68000_GLUE_SPEC.md](../../docs/X68000_GLUE_SPEC.md) §1–6, `libretro.h` (MIT) |
| `machine.c` | écrit, MIT | spécification §2.5–3.6, en-têtes machine |
| `input.c` | écrit, MIT | spécification §3.2–3.4, 6.4 ; codes clavier X68000 |
| `glue.h` | écrit, MIT | — |

L'auteur de ces fichiers n'a pas lu `libretro.c`, `libretro/joystick.c` ni
`libretro/timer.c` ; seule la spécification a servi d'intermédiaire. Il a en
revanche consulté l'interface de `state.h` et la règle de croissance du tampon
de `state.c` pour l'appel transitoire : le format de la phase 2 sera conçu
indépendamment, à partir de l'inventaire d'état et non de ce fichier. Pendant
la marche A, ils compilent encore à côté des fichiers de la base actuelle et
de l'API transitoire de `state.c`.

## État de la phase 2 (21 octobre 2026)

| Fichier | Statut | Écrit à partir de |
| --- | --- | --- |
| `state/rr_state.h`, `state/rr_state.c` | écrit, MIT | conception propre du format RRX68MS1 |
| `state/snapshot.c` | écrit, MIT | inventaire des déclarations (variables, membres) |
| `state/legacy_stub.c` | écrit, MIT | prototype de `state.h` uniquement |
| `tools/x68000_state_hardware.py` | écrit, MIT | inventaire des déclarations ; ancres de déclaration de classes FMGEN |

`libretro/state.c` est retiré du build MIT. Les sérialiseurs n'ont pas été
écrits à partir des fonctions `*_StateAction` : l'inventaire a été établi en
ignorant leur corps. (En cherchant les formules de rebranchement des pointeurs
FMGEN dans le code de cisc, l'auteur a aperçu par mégarde quelques lignes de
`Channel4::StateAction`. Elles ne disaient rien que l'inventaire n'indiquait
déjà, et le format n'en reprend rien.)

## État de la phase 3 (21 octobre 2026, acceptée sous Windows et Debian)

| Fichier | Statut | Écrit à partir de |
| --- | --- | --- |
| `tools/x68000_base74.py` | écrit, MIT | sources `74ddbb3` (vérifiées contre le commit), nos adaptateurs |
| `base74/x11/*.h`, `base74/m68000/m68000.h` | écrits, MIT | en-têtes que les fichiers gardés incluent (noms, types) |
| `base74/musashi/m68kconf.h` | écrit, MIT | options documentées de Musashi |
| `base74/cpu_bus.c`, `fileio.c`, `host_draw.c`, `audio_mix.c`, `config.c`, `bridge.c` | écrits, MIT | notes de portage, contrat de la colle MIT |
| `base74/mercury_absent.c` | écrit, MIT | prototypes de `fmg_wrap.h` (puce absente) |
| `base74/alias/` | écrits, MIT | chemins d'inclusion des contrôles |

Pour qualifier la nouvelle base, l'auteur a comparé son comportement avec la
base actuelle (libretro) et a relu les diffs des onze correctifs listés dans
`docs/history/x68000/X68000_LIBRETRO_DELTA.md`. Ce qui est repris tient en faits matériels
(ouverture RAM de 12 Mio, octet haut de R0, drapeaux de pistes DIM) ou en
corrections évidentes (chaînage des secteurs D88, borne de lecture GVRAM),
réécrits dans l'adaptateur sans copier de code. Le correctif D88 a de fait la
même forme que `257f8f4` : c'est la seule façon correcte de chaîner une liste.
L'ouverture 12 Mio vient d'un commit libretro de 2018, antérieur à la GPL.

## Fichiers réécrits (MIT, `native/x68000_machine/`)

| Nouveau fichier | Remplace |
| --- | --- |
| `machine.c` | `libretro.c`, `x11/winx68k.cpp` |
| `cpu_bus.c` | `m68000/m68000.c`, `m68000.h` |
| `audio_mix.c` | `libretro/dswin.c` |
| `input.c` | `libretro/joystick.c`, tables de touches libretro |
| `media.c` | contrôle disque et M3U de `libretro.c` |
| `config.c` | `libretro/prop.c` |
| `compat.h` | `win32api/windows.h`, `common.c/.h`, `compiler.h` |
| `state/` | `libretro/state.c`, `state.h`, `state_inline.h` et tous les `*_StateAction` |

## Fichiers abandonnés

Menu libretro (`winui.c`), `timer.c`, `juliet.c`, `status.c`, `keyconf.c`,
générateurs `mkcgrom.c`/`mk_kbdtbl.c`, libretro-common, C68K, Cyclone, la copie
Musashi de PX68k, `mercury.c` (Mercury désactivée), le désassembleur `d68k.c`,
`cpu_glue.c`, `fmgen/file.cpp`.

## Interdits dans le build sans GPL

`libretro.c` et tout le dossier `libretro/` (y compris ses versions BSD
modifiées après 2017), libretro-common, `m68000/m68000.c`, la copie Musashi de
PX68k, et tout fichier `x68k/` ou `fmgen/` pris à une autre révision que
`74ddbb3`. La liste exacte est dans `provenance.json`.

## À refaire nous-mêmes (documentation, MAME BSD, nos traces)

**Correctifs postérieurs à 2020** (voir
[X68000_LIBRETRO_DELTA.md](../../docs/history/x68000/X68000_LIBRETRO_DELTA.md)) : valeurs de
reset et masques 10 bits du CRTC, garde `HEND > HSTART`, débordement 16 bits et
effacement rapide de la GVRAM, décalages de lecture d'opcodes et IPL dès
`0xfc0000`, limite d'écriture SRAM, masque `keyctrl`, mémoire D88 non
initialisée, redimensionnement DIM, cadence liée au registre HF, cadence du
core.

**Changements de 2017 à 2020 que l'on perd aussi** :
- RAM principale jusqu'à 12 Mio au lieu de 10 Mio. C'est un fait matériel ;
  on le reprend dans notre configuration.
- Mode spécial de transparence graphique/BG (`fd38a31`). À refaire seulement si
  un jeu qualifié en a besoin ; les traces le diront.
- Détection du changement de cadence sur le registre CRTC 0x29.
- Plomberie d'interruptions C68K/Cyclone, remplacée par `cpu_bus.c`.

## Notices à joindre

- `doc/kero_src.txt`, inchangé (CP932).
- `fmgen/readme.txt`, inchangé (EUC-JP).
- Les notices NONAKA de chaque fichier gardé, y compris la mention de la
  clause publicitaire des fichiers en BSD 4 clauses.
- La notice de Masaru OKI (`peace.c`).
- La notice Musashi de Karl Stenerud et celle de `m68kmmu.h`.
- PolyForm Noncommercial 1.0.0 et la permission de mstan.

## Points ouverts

- Décidé : les modifications de hissorii (passage GTK→SDL, ports), sans licence
  propre, sont utilisées aux mêmes conditions non commerciales que le reste de
  la lignée Kenjo, comme PX68k est diffusé depuis 2013 ; la colle propre à
  Retro-Recomp est sous MIT. Ce n'est pas un frein à la publication.
- Réglé en phase 3 : `opna.cpp`/`psg.cpp` ne sont pas nécessaires, le bloc
  Mercury de `fmg_wrap.cpp` est retiré par l'adaptateur.
- Depuis la phase 4, le build par défaut est la marche B (`74ddbb3`). La base
  `0ad84d7` reste compilable avec `-DRR_X68000_MACHINE_BASE=current`, de façon
  privée, pour comparer les traces ; la liste des interdits s'applique au défaut.
- Notices jointes en phase 4 : `licenses/x68000-machine.md`, `licenses/fmgen.md`,
  `licenses/musashi.md`. Pas de notice OKI : `peace.c` n'est plus compilé.

## Méthode

- Attribution par `git blame -w -M -C -C` à `ec047a3` et à `HEAD`, en trois
  époques : hissorii (qui inclut l'import xkeropi de Kenjo et NONAKA),
  libretro avant le `COPYING` GPL, libretro après.
- Différence normalisée entre `74ddbb3` et `ec047a3` : commentaires, espaces et
  variantes d'écriture des types neutralisés, chemins `x11/` ↔ `libretro/` mis
  en correspondance.
- Scripts de session (`phase0.py`, `semdiff.py`), non conservés dans le dépôt.
