"""Small offline English/French catalog. Stable IDs never depend on GUI text."""
import re

LANGUAGES = ('en', 'fr')
STRINGS = {
    'tagline': ('Less emulation. No FPGA. As native as possible.', 'Moins d’émulation. Sans FPGA. Le plus natif possible.'),
    'library': ('GAME LIBRARY', 'BIBLIOTHÈQUE'),
    'language': ('Language', 'Langue'),
    'add_roms': ('Add ROMs…', 'Ajouter des ROMs…'),
    'add_folder': ('Add folder…', 'Ajouter un dossier…'),
    'remove': ('Remove', 'Retirer'),
    'clear': ('Clear list', 'Vider la liste'),
    'game': ('Game', 'Jeu'),
    'console': ('Console', 'Console'),
    'video_timing': ('Video', 'Vidéo'),
    'video_guess': ('{standard} · guess', '{standard} · proposé'),
    'video_selected': ('{standard} · set', '{standard} · choisi'),
    'cover': ('Box art', 'Cover'),
    'conversion': ('Conversion', 'Conversion'),
    'choose_cover': ('Choose box art…', 'Choisir une cover…'),
    'auto_cover': ('Automatic box art', 'Cover automatique'),
    'play': ('Play game', 'Lancer le jeu'),
    'memory': ('Game memory', 'Mémoire des jeux'),
    'output': ('Games folder', 'Dossier des jeux'),
    'browse': ('Browse…', 'Choisir…'),
    'icon': ('Box art as game icon', 'Cover comme icône'),
    'icon_tags': ('Automatic tags', 'Tags automatiques'),
    'online': ('Download missing box art', 'Télécharger les covers manquantes'),
    'extended': ('Extended native coverage · Master System', 'Couverture native étendue · Master System'),
    'passes': ('Maximum passes', 'Passes maximum'),
    'frames': ('Frames per test', 'Images par test'),
    'sequential': ('One game at a time · shared datas folder', 'Un jeu à la fois · dossier datas commun'),
    'start': ('Convert / regenerate', 'Convertir / régénérer'),
    'stop': ('Stop after this game', 'Arrêter après ce jeu'),
    'open_folder': ('Open folder', 'Ouvrir le dossier'),
    'footer': ('Fallback use stays visible in every game. Master System supported today.', 'Le secours reste signalé dans chaque jeu. Master System prise en charge actuellement.'),
    'ready': ('Add ROMs, then convert your batch.', 'Ajoute tes ROMs, puis convertis ton lot.'),
    'shared': ('All games share datas/Retro-Recomp.ini in their executable folder.', 'Tous les jeux partagent datas/Retro-Recomp.ini dans leur dossier d’exécutables.'),
    'waiting': ('Waiting', 'En attente'),
    'invalid': ('Invalid ROM', 'ROM invalide'),
    'created': ('Ready', 'Créé'),
    'pending_install': ('Ready · waiting for game to close', 'Prêt · en attente de fermeture du jeu'),
    'error': ('Error', 'Erreur'),
    'duplicate': ('Duplicate skipped', 'Doublon ignoré'),
    'converting': ('Converting…', 'Conversion…'),
    'auto': ('Auto', 'Auto'),
    'chosen': ('Selected', 'Choisie'),
    'size': ('{value} KB', '{value} Ko'),
    'fallback': ('Fallback: {percent:g}% of tested cycles · {comparison}', 'Secours : {percent:g} % des cycles testés · {comparison}'),
    'vdp_equal': ('VDP comparison matches', 'comparaison VDP identique'),
    'vdp_different': ('VDP differences to investigate', 'écarts VDP à examiner'),
    'pick_roms': ('Add Master System ROMs', 'Ajouter des ROMs Master System'),
    'pick_folder': ('Add ROMs from this folder and its subfolders', 'Ajouter les ROMs de ce dossier et de ses sous-dossiers'),
    'pick_output': ('Shared folder for game executables', 'Dossier commun aux exécutables des jeux'),
    'one_cover': ('Select one game to choose its box art.', 'Sélectionne un seul jeu pour choisir sa cover.'),
    'pick_cover': ('Box art for the selected game', 'Cover du jeu sélectionné'),
    'images': ('Images', 'Images'),
    'need_rom': ('Add at least one ROM to the list.', 'Ajoute au moins une ROM à la liste.'),
    'invalid_limits': ('Choose 1–10 passes and 1–10000 frames per test.', 'Choisis 1 à 10 passes et 1 à 10000 images par test.'),
    'need_output': ('Choose the games folder.', 'Choisis le dossier des jeux.'),
    'starting': ('Converting {count} ROMs…', 'Conversion de {count} ROMs…'),
    'stopping': ('Stop requested: finishing the current game.', 'Arrêt demandé : le jeu en cours termine sa conversion.'),
    'fatal': ('The batch was interrupted: {error}', 'Le lot a été interrompu : {error}'),
    'summary': ('{succeeded} ready · {failed} errors · {duplicates} duplicates · {pending} remaining', '{succeeded} créé(s) · {failed} erreur(s) · {duplicates} doublon(s) · {pending} restant(s)'),
    'memory_intro': ('Each ROM keeps its discoveries for future conversions.', 'Chaque ROM conserve ses découvertes pour les prochaines conversions.'),
    'identity': ('ROM identity', 'Identité ROM'),
    'observations': ('Observations', 'Observations'),
    'open_memory': ('Open datas/library', 'Ouvrir datas/library'),
    'wait_close': ('Use “Stop after this game”, then wait for the current conversion to finish.', 'Utilise « Arrêter après ce jeu », puis attends la fin de la conversion en cours.'),
    'tip_add_roms': ('Add one or several .sms cartridges. Your original ROMs are preserved.', 'Ajoute une ou plusieurs cartouches .sms. Tes ROMs originales sont préservées.'),
    'tip_add_folder': ('Scan a folder and its subfolders for .sms ROMs. Paths already in the list are skipped.', 'Recherche les ROMs .sms dans un dossier et ses sous-dossiers. Les chemins déjà présents sont ignorés.'),
    'tip_remove': ('Remove selected rows from this batch. Files on disk are preserved.', 'Retire les lignes sélectionnées du lot. Les fichiers sur disque sont conservés.'),
    'tip_clear': ('Empty this queue. ROMs, game executables and their datas are preserved.', 'Vide cette liste. Les ROMs, exécutables et leur dossier datas sont conservés.'),
    'tip_choose_cover': ('Choose an image for the selected game’s Windows icon. The whole cover keeps its proportions.', 'Choisis l’image de l’icône Windows du jeu sélectionné. La boîte entière garde ses proportions.'),
    'tip_auto_cover': ('Use matching local box art first, then an online search if downloads are enabled.', 'Utilise d’abord une cover locale correspondante, puis une recherche en ligne si le téléchargement est activé.'),
    'tip_play': ('Launch the selected converted game. Double-click its row to play. F2 configures both players; H opens help.', 'Lance le jeu converti sélectionné. Tu peux aussi double-cliquer sur sa ligne. F2 configure les deux joueurs ; H ouvre l’aide.'),
    'tip_memory': ('View discoveries recorded for each ROM. Re-conversion can compile learned paths and RAM variants.', 'Consulte les découvertes enregistrées pour chaque ROM. Une reconversion peut compiler les chemins et variantes RAM appris.'),
    'tip_output': ('All executables go here. Shared controls, logs, memory and reports stay inside datas.', 'Tous les exécutables vont ici. Commandes communes, journaux, mémoire et rapports restent dans datas.'),
    'tip_icon': ('Embed the box art as the game’s Windows icon. No external image is needed to play.', 'Intègre la cover comme icône Windows du jeu. Aucune image externe n’est nécessaire pour jouer.'),
    'tip_icon_tags': ('Add a small translucent red target badge to the bottom-left of known Light Phaser game icons. Original box art is preserved. Applies when box art icons are enabled.', 'Ajoute un petit tag de visée rouge légèrement transparent en bas à gauche des icônes des jeux Light Phaser connus. Les covers originales sont préservées. S’applique lorsque les icônes de cover sont activées.'),
    'tip_online': ('Download missing art from Libretro and cache it in datas/BoxArt. Only the game title is sent; the ROM stays local.', 'Télécharge les covers absentes depuis Libretro et les conserve dans datas/BoxArt. Seul le titre est transmis ; la ROM reste locale.'),
    'tip_extended': ('Enabled by default for the Sega mapper. Compiles every ROM position, bank boundaries and repeated prefixes, plus RAM variants learned during conversion tests with exact byte checks. Conversion validates both test scenarios against the reference CPU before replacing a game. Unknown RAM variants remain counted fallback. Gameplay does not write learning files. This does not certify every level, console hardware or physical latency.', 'Activée par défaut pour le mapper Sega. Compile chaque position ROM, les frontières de banques et les préfixes répétés, ainsi que les variantes RAM apprises pendant les tests de conversion avec vérification exacte des octets. La conversion compare les deux parcours au CPU de référence avant de remplacer un jeu. Les variantes RAM inconnues restent du secours compté. Le gameplay ne crée aucun fichier d’apprentissage. Cela ne certifie pas tous les niveaux, le matériel console ni la latence physique.'),
    'tip_passes': ('Maximum compile → test → learn cycles. Stops early at zero fallback on the tested scenarios or when no new variants are found. These tests do not explore every level.', 'Maximum de cycles compilation → test → apprentissage. Arrêt anticipé à zéro secours sur les scénarios testés ou sans nouvelles variantes. Ces tests n’explorent pas tous les niveaux.'),
    'tip_frames': ('Length of each automated scenario, in video frames. More frames test a longer run and increase conversion time. This does not change game speed.', 'Durée de chaque scénario automatique, en images vidéo. Plus d’images teste un parcours plus long et prolonge la conversion. Cela ne change pas la vitesse du jeu.'),
    'tip_start': ('Convert or regenerate every ROM in the queue using its latest discoveries. Replace existing games automatically; preserve controls and game memory. An open game is updated when it closes. Failed builds preserve the previous game.', 'Convertit ou régénère chaque ROM de la liste avec ses dernières découvertes. Remplace automatiquement les jeux existants et préserve les commandes et la mémoire. Un jeu ouvert est mis à jour à sa fermeture. Un échec de compilation préserve l’ancien jeu.'),
    'tip_stop': ('Finish the current game, then stop before the next ROM. Its compilation is allowed to finish.', 'Termine le jeu en cours, puis s’arrête avant la ROM suivante. Sa compilation va jusqu’au bout.'),
    'tip_open_folder': ('Open the games folder in Windows Explorer.', 'Ouvre le dossier des jeux dans l’Explorateur Windows.'),
    'tip_language': ('Switch English / French immediately. Saved for the converter and this games folder. In a game, F7 switches language.', 'Passe immédiatement entre anglais et français. Choix enregistré pour le convertisseur et ce dossier de jeux. Dans un jeu, F7 change la langue.'),
    'tip_table': ('Select a game to see its result. Use Ctrl/Shift for several rows; double-click a ready game to launch it.', 'Sélectionne un jeu pour consulter son résultat. Ctrl/Maj sélectionne plusieurs lignes ; double-clique sur un jeu créé pour le lancer.'),
    'tip_video_timing': ('Auto keeps a saved per-ROM profile, or guesses from the ROM filename. A region label is not proof of console timing. Select PAL or NTSC for this ROM to override it on regeneration; the choice is saved in its compilation profile. Other consoles will define their own timing options.', 'Auto conserve le profil mémorisé de cette ROM ou propose un rythme selon son nom. Une étiquette de région ne prouve pas le rythme de la console. Choisis PAL ou NTSC pour cette ROM lors de la régénération ; le choix sera mémorisé dans son profil. Les autres consoles auront leurs propres options.'),
}


def tr(key: str, language: str = 'en', **values) -> str:
    return STRINGS[key][language == 'fr'].format(**values)


def extended_default(preferences: dict) -> bool:
    # Apply the user's new default once to old preferences; later explicit
    # choices (including opting out) remain persistent.
    return preferences.get('backend') == 'banked' if preferences.get('coverage_default_revision') == 2 else True


LOG_TRANSLATIONS = {
    'Choisis une ROM Master System au format .sms.': 'Choose a Master System ROM in .sms format.',
    'Taille de ROM non prise en charge (8 Ko à 4 Mo, multiple de 8 Ko).': 'Unsupported ROM size (8 KB to 4 MB, multiple of 8 KB).',
    'Même ROM déjà présente dans le lot.': 'The same ROM is already present in this batch.',
    'La ROM a changé depuis son ajout au lot ; ajoute-la à nouveau.': 'The ROM changed since it was added; add it again.',
    'La couverture native étendue prend en charge le mapper Sega uniquement.': 'Extended coverage supports the Sega mapper only.',
    'Le profil ne correspond pas au CRC32 de cette ROM.': 'The profile does not match this ROM CRC32.',
    'Le profil ne correspond pas au SHA256 de cette ROM.': 'The profile does not match this ROM SHA256.',
    'Profil mémorisé incompatible avec cette ROM ; choisis un profil explicite.': 'Saved profile incompatible with this ROM; choose an explicit profile.',
    'Cover locale absente : recherche sur Libretro…': 'No local box art: searching Libretro…',
    'Profil de compilation reconnu dans la bibliothèque.': 'Compilation profile found in the library.',
    'Vérification du mode strict…': 'Checking strict mode…',
    'Comparaison avec le processeur de référence…': 'Comparing with the reference CPU…',
    'Seuil atteint : aucun cycle de secours sur les deux parcours testés.': 'Threshold reached: zero fallback cycles on both tested scenarios.',
    'Arrêt : aucune nouvelle variante native observée.': 'Stopped: no new native variants found.',
    'Arrêt : budget de passes atteint.': 'Stopped: pass budget reached.',
}
LOG_PATTERNS = [
    (r'^ROM : (.*), (\d+) Ko, CRC32 (.*)$', r'ROM: \1, \2 KB, CRC32 \3'),
    (r'^Icône : (.*)$', r'Icon: \1'),
    (r'^Cover locale inutilisable : (.*)$', r'Local box art unusable: \1'),
    (r'^Icône de cover indisponible : (.*). La conversion continue.$', r'Box art icon unavailable: \1. Conversion continues.'),
    (r"^Tags de l'icône : (.*)$", r'Icon tags: \1'),
    (r"^Tag d'icône indisponible : (.*). La cover reste utilisée.$", r'Icon tag unavailable: \1. Box art is still used.'),
    (r'^Boucle arrêtée \((.*)\) : du secours reste présent sur les parcours testés.$', r'Loop stopped (\1): fallback remains on the tested scenarios.'),
    (r'^Exécutable créé : (.*)$', r'Executable created: \1'),
    (r'^Nouvelle version prête ; remplacement à la fermeture du jeu : (.*)$', r'New version ready; installation when the game closes: \1'),
    (r'^Mémoire du jeu : (\d+) entrées ROM vérifiées, (\d+) observations RAM ; (\d+) importées des anciennes parties.$', r'Game memory: \1 verified ROM entries, \2 RAM observations; \3 imported from previous runs.'),
    (r'^Passe (.*) : couverture native ROM et variantes RAM…$', r'Pass \1: native ROM coverage and RAM variants…'),
    (r'^Passe (.*) : traduction Z80 et compilation native…$', r'Pass \1: Z80 translation and native compilation…'),
    (r'^(.*) positions ROM traduites ; (.*) corps natifs partagés.$', r'\1 ROM positions translated; \2 shared native bodies.'),
    (r'^Vérification (.*) : (.*) images…$', r'Testing \1: \2 frames…'),
    (r'^(.*) : (.*) % natif, (.*) % interprété.$', r'\1: \2% native, \3% interpreted.'),
    (r'^(.*) nouvelles variantes observées : compilation et nouveau contrôle.$', r'\1 new variants observed: compiling and checking again.'),
    (r'^(.*) nouvelles entrées repérées : recompilation à la passe suivante.$', r'\1 new entries found: recompiling on the next pass.'),
    (r'^Comparaison CPU/VDP de référence : identique.$', r'Reference CPU/VDP comparison: matching.'),
    (r'^Comparaison CPU/VDP de référence : divergence à examiner.$', r'Reference CPU/VDP comparison: differences to investigate.'),
]


def log_text(text: str, language: str = 'en') -> str:
    if language == 'fr':
        return text
    if text in LOG_TRANSLATIONS:
        return LOG_TRANSLATIONS[text]
    for pattern, replacement in LOG_PATTERNS:
        if re.match(pattern, text):
            return re.sub(pattern, replacement, text)
    return text
