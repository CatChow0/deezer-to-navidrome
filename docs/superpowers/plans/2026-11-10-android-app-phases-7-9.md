# App Android : reprise des phases 7 à 9

## Contexte

Les phases 7 à 9 de l'app ont été faites par un autre modèle (beam:cloud), commits `61a3f51` à `a17bf70` sur `feature/android-app`, rien de poussé. Tu trouves l'UI/UX mauvaise, incomplète ou buguée. La revue du code (ci-dessous) le confirme. Ce qui reste fiable, c'est la phase 6 (`30bceb7`) : connexion, profils, Activité, mises à jour, thème et composants.

**Tes décisions :**
- on revient à la phase 6, puis on refait les phases 7 à 9 de zéro ;
- le Jenkinsfile repousse seulement depuis `main` ;
- pas de notifications de fin de tâche ;
- la version 1.18.1 reste.

Les règles ne changent pas :
- je ne commite que sur ta demande ;
- le push git et l'image DEV viennent une fois les phases 8 et 9 finies, et seulement avec ton accord ;
- rien n'est écrit sur `S:` ;
- ni la clé, ni un jeton, ni un ARL dans le dépôt, les logs ou l'app.

## La revue : ce qui cassait

| Problème | Effet |
|---|---|
| Corps de requête en `Map<String, Any?>` | Retrofit ne sait pas les sérialiser : **chaque action** échoue (scan, match, automatisation, comptes d'une playlist, mute, follow, sauvegarde des réglages). |
| `track_id` est un nombre côté serveur, une `String` dans l'app | L'écran des titres d'une playlist Deezer échoue : « not what this app expects ». |
| `gain` est décimal chez Deezer, un `Int` dans l'app | Les extraits échouent. Le repli sur `link` (une page web) est passé à ExoPlayer, et le lecteur est libéré puis réutilisé. |
| Pochettes en chemin relatif, sans jeton pour Coil | Aucune pochette de playlist, de Made for you ou de Navidrome ne s'affiche. |
| « Also in Navidrome » lit `title` alors que le serveur envoie `name` | Lignes vides, pas de détail en lecture seule. |
| Changer de profil | L'écran en cours garde les données de l'ancien profil. |
| Colonnes non défilables, 3 `LazyColumn` empilées, 5 boutons sur une ligne | Stats, Made for you et le détail d'une playlist sont coupés sur un téléphone. |
| Barre du bas à 7 onglets au lieu des 5 du design | Icônes fausses, « Activity » toujours sélectionné, pile de retour qui grossit. |
| Réglages | Clés brutes, boutons « Cycle », 4 qui devient 4.0, et **Reset data, y compris « all », sans confirmation**. |
| Recherche de Stats | Une requête par touche, réponses dans le désordre. |
| Tâches lancées | Message « Scan started: <id> » au lieu d'un lien vers la tâche. Les nouveaux écrans ne déclenchent jamais la bannière « serveur injoignable ». |
| Style | Boutons et cartes Material bruts, au lieu des cartes de verre, puces, bannières et squelettes de la phase 6. |
| Tests | Uniquement des ViewModels sur faux API, sans MockWebServer : aucun des bugs ci-dessus n'était détectable. |
| README | Annonce un mode hors ligne qui n'existe pas. R8 activé mais jamais construit. |
| Bump en 1.18.1 | `tests/test_new_and_help.py` échoue (RELEASES[0] vaut 1.18.0). Les badges du README sont restés en 1.18.0. |

**Manquant par rapport au design :**
- **Phase 7 :** Share depuis Deezer et Spotify, téléchargement depuis la recherche, pages album et artiste, filtres, « Find on Deezer », état dans Navidrome, réglages de Made for you, tri et recherche.
- **Phase 8 :** graphiques, pages artiste, album et titre, récaps en stories, mute et refresh des sorties, Settings presque entiers.
- **Phase 9 :** hors ligne, baseline profile, vérification d'accessibilité.

## Étape 0 : revenir à la phase 6

1. Garder l'ancien travail en référence locale : branche `archive/beam-7-9` sur `efacd0a`, jamais poussée.
2. Lancer `git revert --no-commit` sur `1a2eed1` (Jenkins) et sur `61a3f51..a17bf70`. Ensuite, vérifier que `git diff 30bceb7 -- android Jenkinsfile docs` est vide.
3. Finir la 1.18.1 :
   - entrée dans `core/patch_notes.py` ;
   - `templates/notes/1.18.1.html` (brouillon, complété en fin de phase 9) ;
   - badges dans `README.md` et `DOCKERHUB_README.md`.
4. Lancer la suite Python (`DATA_DIR` temporaire) et `./gradlew testDebugUnitTest`. Commit sur ta demande.

## Fondations, au début de la phase 7

Elles corrigent la cause des bugs, une fois pour toutes les phases.

- **Navigation :**
  - les 5 onglets du design : Dashboard, Made for you, Stats, Releases, More ;
  - un graphe par onglet, avec `saveState` et `restoreState` ;
  - les sous-écrans ont une barre avec retour et titre ;
  - l'Activité est dans More, plus une icône dans la barre du haut avec le nombre de tâches en cours ;
  - les icônes sont des vector drawables Material Symbols (Apache 2.0), sans `material-icons-extended`.
- **Données :**
  - corps de requête en classes `@Serializable` uniquement ;
  - un sérialiseur `FlexibleId` (nombre ou texte vers `String`) pour les identifiants numériques du serveur ;
  - chaque endpoint ajouté a un test MockWebServer : méthode, chemin, corps JSON envoyé, et décodage d'une fixture écrite d'après le code du serveur, dans `app/src/test/resources/api/`.
- **Profil :** `AppGraph.profile` est un `StateFlow`. Chaque ViewModel d'écran recharge sur `collectLatest` du profil.
- **Images :**
  - Coil 3 avec `coil-network-okhttp` sur `graph.client`, pour que le jeton et le profil suivent ;
  - un `ImageLoader` singleton dans `D2nApplication` ;
  - `MediaUrls.resolve(base, path)` pour les chemins `/api/v1/…`.
- **Erreurs et tâches :**
  - un état `Loadable` (chargement, prêt, échec) et un `ScreenState` qui affiche squelette, erreur avec Retry, vide ou contenu ;
  - `Unreachable` appelle `reachability.reportFailure()` ;
  - une action qui lance une tâche affiche un snackbar global « Scan started · View », qui ouvre `TaskRoute` ;
  - les actions sont désactivées hors ligne (`LocalOnline`).
- **Audio :**
  - un seul `PreviewPlayer` (Media3 ExoPlayer avec `datasource-okhttp`) tenu au niveau de `MainScaffold` ;
  - un mini-lecteur au-dessus de la barre du bas ;
  - pause en arrière-plan.
- **Composants :** on réutilise GlassCard, D2nButton, Chip, Banner, Skeleton, D2nTextField, Aurora et Brand. On ajoute :
  - `ScreenScaffold` (titre, retour, pull-to-refresh, LazyColumn), `SectionHeader`, `Cover` (placeholder) ;
  - `TrackRow`, `EmptyState`, `ConfirmDialog` (danger), `ActionSheet` (bottom sheet), `SegmentedTabs`, `StatTile`, `SearchField` (action IME), `MiniPlayer`.
- **Bibliothèques :** les dernières stables de Coil 3 et Media3, au moins 2 semaines d'ancienneté, épinglées dans `libs.versions.toml`.

## Phase 7 : les fonctions principales

- **Dashboard :**
  - un champ de recherche qui ouvre Search ;
  - les playlists du profil en cartes : pochette, titre (et nom Deezer si renommée), source, puces matched/missing/unchecked, comptes ;
  - « Add » ouvre une feuille : lien, ou « Import CSV » par le sélecteur de fichiers. Share (`ACTION_SEND` dans le manifeste) l'ouvre pré-remplie avec un lien Deezer ou Spotify ;
  - « Also in Navidrome » en lecture seule, avec son détail (`/navidrome/playlists/{account}/{id}`) et la mention « Made in Navidrome: change it there » ;
  - une carte Library (`/library/stats`, Refresh).
- **Search :**
  - onglets Tracks, Albums, Artists ;
  - puces « In library » et « 3/12 owned » (`/library/check`) ;
  - une feuille par titre : Preview, Download (`/downloads`), Open in Deezer ;
  - pages Album (Download album) et Artiste.
- **Détail d'une playlist :**
  - en-tête avec ses comptes ;
  - Scan (quick ou full, en tâche) et Download missing ;
  - menu : Publish again, Where in Navidrome (`/playlists/{id}/navidrome`), Settings (comptes, automatisation avec intervalles, télécharger après le scan) ;
  - filtres All, Matched, Missing, Unchecked, Downloaded, et un filtre texte ;
  - une feuille par titre : Preview, Mark missing, Back to automatic, Choose a library file (`/library/search`, mode `file`), Find on Deezer (`/source-match`) ;
  - Delete, avec une confirmation qui explique le retrait du profil.
- **Made for you :**
  - mode Off, Daily Mix ou Daily Mix+, un interrupteur Discover, Generate (tâche) ;
  - le dernier passage, la bannière quand les téléchargements sont bloqués, la jauge des limites disque ;
  - limites et règles d'essai dans une feuille, avec les mêmes choix que `made-for-you.js` ;
  - les listes On trial, To review et Trash avec compteurs, recherche, tri et filtre par source ;
  - swipe Keep à droite et Remove à gauche, avec fond coloré et retour haptique ;
  - Keep all, Remove all et Empty trash, avec confirmation ;
  - une section Deezer mixes : suivre un mix (`/deezer/mixes/follow`) et ajouter une playlist Deezer.

## Phase 8 : le reste

- **Stats :**
  - l'état vide ou d'import (`/stats/status`) ;
  - Week, Month, Year et All, avec précédent et suivant ;
  - des tuiles : écoutes, durée, artistes, albums, titres, couverture ;
  - des graphiques Canvas : barres des genres, heatmap 7×24 ; et le jour le plus chargé, la plus longue série ;
  - les tops avec pochettes, qui mènent aux pages artiste, album et titre (`/stats/{kind}/{id}`) ;
  - les écoutes paginées, avec une recherche à délai de 300 ms où la dernière requête gagne ;
  - History mène aux récaps en stories plein écran :
    - pager auto, barres de progression, tap gauche et droite, appui long pour pause, glisser vers le bas pour fermer ;
    - l'audio du top titre par `/stats/audio`.
- **Releases :**
  - le compte Deezer du profil, la dernière mise à jour, Refresh (tâche), et l'état « non connecté » qui renvoie aux Settings ;
  - filtres All, Albums, Singles & EPs, Hide featured, et regroupement par date ;
  - une feuille par sortie : Open in Deezer, Download album, Mute artist ;
  - les artistes masqués (pour les démasquer) et les artistes suivis.
- **Settings (More → Settings), avec les sections du web :**
  - **Music and downloads :**
    - dossiers (`scan_dirs`) et chemins Navidrome (`host_to_navidrome_roots`) ;
    - le dossier de téléchargement ;
    - Performance et Release feed, en menus avec les `choices` du serveur.
  - **Accounts :**
    - comptes Navidrome et Deezer : ajouter, modifier, tester, par défaut, téléchargement, supprimer avec confirmation. Mot de passe et ARL en champs d'écriture seule, jamais affichés ;
    - Listening stats : import, jeton ListenBrainz ;
    - Sign-in : mot de passe, jeton d'API affiché une fois avec copie, webhook (définir, tester, retirer), appareils avec ce téléphone marqué, et révocation ;
    - Android app.
  - **Maintenance :**
    - Library index (Refresh, Rebuild), Fix metadata et Undo, Repair downloads ;
    - Duplicates : scan, rapport, choix, apply avec confirmation ;
    - Reset data : chaque effacement a sa confirmation, et « Everything » demande de taper RESET.
- **New et Help :**
  - HTML rendu en `AnnotatedString` (titres, listes à puces, gras, liens, code), sans WebView ;
  - un point « unseen » sur More et sur New, marqué vu à l'ouverture.

## Phase 9 : finitions

- **Hors ligne :**
  - un GET en échec réseau est relu du cache (intercepteur, `FORCE_CACHE`) ;
  - la bannière dit « Can't reach the server — showing saved data » ;
  - les actions sont désactivées, avec Retry.
  - **Serveur :** `Vary: X-Navidrome-Account` sur les réponses cachables de `/api/v1`, avec un test Python, pour qu'un profil ne voie jamais les données d'un autre.
- **Accessibilité :**
  - libellés TalkBack, pochettes décoratives, titres en `heading()`, cibles de 48 dp ;
  - captures à une échelle de police de 1,3 et de 2,0 pour chaque écran.
- **Performance :**
  - R8 avec des règles minimales : celles des bibliothèques, plus kotlinx.serialization ;
  - vérifié par un vrai build release signé sur le PC (`build-apk.ps1`), installé sur l'émulateur et testé ;
  - un baseline profile : plugin `androidx.baselineprofile` et un module `:baselineprofile` (parcours UiAutomator). Il est généré sur l'AVD API 31 et le fichier est versionné, donc le build Docker ne change pas.
- **Documentation :**
  - `android/README.md` : écrans, ce que fait vraiment le hors ligne, procédure de release, sauvegarde et restauration de la clé ;
  - le README principal : section de l'app et règle du reverse proxy ;
  - la page d'aide de l'app ;
  - les notes 1.18.1.

## Fichiers principaux

- **App :**
  - `android/app/src/main/java/io/github/catchow0/d2n/` : `AppGraph.kt`, `data/D2nApi.kt`, `data/ApiModels.kt`, `data/HttpClient.kt` (cache hors ligne) ;
  - `ui/main/MainScaffold.kt` (onglets, snackbar, mini-lecteur) ;
  - `ui/components/*`, et de nouveaux paquets `ui/dashboard`, `ui/search`, `ui/playlists`, `ui/madeforyou`, `ui/stats`, `ui/releases`, `ui/settings`, `ui/content`, `audio/`.
- **Build et tests :**
  - `android/app/build.gradle.kts`, `android/gradle/libs.versions.toml`, `AndroidManifest.xml` (Share) ;
  - `app/src/test/.../data/*Test.kt` et `app/src/test/resources/api/*.json`.
- **Serveur :** `routes/api_v1/__init__.py` (Vary), `tests/test_api_v1_*.py`, `core/patch_notes.py`, `templates/notes/1.18.1.html`.
- **Plan dans le dépôt :** `docs/superpowers/plans/2026-11-10-android-app-phases-7-9.md`, comme pour la phase 6.

## Vérification, à la fin de chaque phase

1. `./gradlew testDebugUnitTest` : ViewModels, plus MockWebServer pour chaque endpoint et chaque corps envoyé.
2. La suite Python complète, avec `DATA_DIR` temporaire et rien sur `S:`.
3. L'émulateur (`Pixel_6`, API 31, et `Pixel_6_2`, API 28) contre un serveur jetable :
   - l'image Docker de la branche, servie par gunicorn sur `127.0.0.1:8097`, avec des données temporaires ;
   - plus un Navidrome Docker à 2 utilisateurs ;
   - chaque écran en capture, à la largeur du téléphone, puis en grande police ;
   - le changement de profil ;
   - un parcours de chaque action.
4. Un rapport en français : ce qui marche, ce qui n'a pas pu être testé.
5. Le commit, sur ta demande.

**Limite :** je n'ai pas ton ARL. Les sorties et les mix Deezer sont vérifiés par fixtures et MockWebServer, puis chez toi sur l'image DEV.

## Hors champ

Les notifications, le lecteur complet de la bibliothèque, les mises en page tablette et toute modification du comportement du serveur, en dehors de `Vary` et des endpoints qui manqueraient (ajoutés avec tests et entrée openapi).
