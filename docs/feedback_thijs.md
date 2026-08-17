# Feedback van Thijs — Garmin Data AI Coach project

Thijs heeft de toolkit uitgeprobeerd met eigen data (niet de NOAA-demo) voor een persoonlijk
project. Onderstaand zijn bevindingen verwerkt: eerst het origineel bericht, dan wat er direct
is opgelost, dan wat nog moet worden uitgezocht.

**Status:** 12 van de 16 punten opgelost (#2, 3, 4, 6, 7, 9, 10, 11, 12, 13, 14, 15, en de
sql-editor bug ook gefixt in `CatalogPanel.js` waar Thijs 'm niet meldde maar dezelfde bug zat).
#10, 11, 12, 13, 15 waren stuk voor stuk breaking changes aan `build_fact`/`build_dimension` en
zijn daarom gebundeld in één sessie opgepakt, zoals [`docs/releasing.md`](releasing.md) al
aanraadde. Voor #1 is het plan vastgesteld maar de uitvoering (tag/branch pushen) volgt nog.
4 punten staan verder nog open, zie "Uit te zoeken" hieronder.

---

## Origineel bericht

> Hi Eef,
>
> Zoals beloofd ben ik aan de slag gegaan met datavloot als de motor in mijn "Garmin Data AI
> Coach" projectje. Het hele data verwerkingsstuk werkt nu, het AI stuk blijkt wat lastiger
> maar gaat uiteindelijk ook wel lukken.
>
> Wat dingen die mij opvielen bij het bouwen:
>
> 1. Ik krijg een grote warning bij dbt deps:
>    ```
>    12:27:58  Running with dbt=1.11.12
>    12:28:03  WARNING: The git package "https://gitlab.com/datavloot/datavloot-toolkit.git"
>      is pinned to the "main" branch.
>      This can introduce breaking changes into your project without warning!
>    ```
> 2. Als ik meteen na aanmaken nieuw project "dbt parse" doe dan krijg ik dit:
>    ```
>    Parsing Error
>    The schema file at models\business\dimensions\_dim_configs.yml is invalid because the
>    value of 'models' is not a list
>    ```
>    Dat komt natuurlijk door dat die yaml bestanden al niet uit gecommentarieerde code bestaan.
> 3. De voorbeeld dlt configuratie in assets.py werkt niet bij mij. Lijkt erop dat je
>    'credentials' niet zo mee kan geven aan een pipeline (regel 51). Volgens mij moet dat
>    zoiets zijn:
>    ```
>    Destination=duckdb(
>        Credentials=str(`DBT_PROJECT_DIR`),
>    )
>    ```
> 4. Alle links op pypi werken niet. Lijken relatieve links te zijn op Gitlab?
> 5. Als ik "datavloot start" doe krijg ik telkens deze waarschuwing in mijn terminal:
>    `warnings.warn(f"Error loading repository location {location_name}")`
> 6. De "instruction" file wordt niet opgepikt. Je kan het wel in een losse dir zetten maar dan
>    moet je dat wel zo configureren in je workspace. En als je hem kopieert moet het
>    data.instructions ipv data-instructions zijn om opgepikt te worden.
> 7. Copilot heeft de instructie uiteindelijk wel beschikbaar gehad en dat zie je ook aan de
>    code. De macro's worden netjes gebruikt en de yaml configs ingevuld. Wel zie ik dat er veel
>    (business) logica in de staging laag terecht is gekomen. Wellicht goed om nog aan te geven
>    wat voor type logica je waar zou verwachten.
> 8. Ik weet niet zo goed wat ik moet vinden van duckdb. Volgens mij is het (nog) niet echt
>    geschikt om meerdere, concurrent verbindingen mee te hebben (Concurrency – DuckDB). En
>    tijdens het werk heb je heel vaak meerdere verbinding openstaan. Dbt die schrijft, crows
>    nest dat een sql editor open heeft, copilot die je iets laat uitvoeren, een vs code
>    extensie die je open hebt omdat je de inhoud van een tabel wilt zien, dbt extensie die
>    hetzelfde doet. Ik ben continu connecties aan het openen en weer sluiten wat nogal
>    frustrerend werkt. Las wel iets dat ducklake dit probleem niet heeft, weet niet wat dat
>    inhoudt en wat de gevolgen daarvan zijn. Ook las ik dat dit probleem in een nieuwe versie
>    later dit jaar wel opgelost lijkt te worden maar voor nu werkt het niet fijn. Krijg ook
>    telkens foutmeldingen tijdens DLT loads omdat ik dan crows nest nog heb draaien op de
>    achtergrond oid.
> 9. De sql editor in crows nest gaat niet echt lekker om met lange en brede tabellen. De
>    horizontale scrollbar zit namelijk onderaan de tabel en de kolomtitels bewegen niet mee.
>    Dus als ik een tabel heb met meer dan 20 regels en meer dan pakweg 15 kolommen moet je naar
>    beneden scrollen om naar rechts te kunnen gaan, maar dan zie je de kolomtitels niet meer.
> 10. Ik wil mijn dim_time op seconden hebben want dat is nogal relevant voor wanneer een
>     "ronde" bij het hardlopen start. Maar dat kan ik niet configureren. Ik zou hier de nieuwe
>     aanpak die wij besproken hebben over macros overwegen. En/of voor date de publieke
>     dim_date package eens bekijken.
> 11. Qua fact macro: waarom moet ik de kolommen nog een keer opgeven onder meta? Die heb ik
>     daarboven toch al staan? En waarom moet ik de key van de dim opgeven, die ligt toch al
>     vast bij de dim zelf?
> 12. Persoonlijk vind ik de naamgeving van de attributen onder dimensions niet erg duidelijk.
>     Welke van de twee nu "fk" heet en welke "dim_fk" (dim_pk had ik wel gesnapt); dat ga ik
>     nooit onthouden en dus altijd moeten blijven opzoeken. Ook key zegt mij niet of dit nu aan
>     de fact of dim kant zit.
> 13. Kan ik ook een relatie maken met een dim obv meerdere kolommen?
> 14. Ik zou de "generate_surrogate_keys" macro dispatchen. Dan geef je mensen de vrijheid om
>     een andere invulling te geven. Persoonlijk houd ik niet van hashes, iig niet voor mijn
>     date dimensie.
> 15. Wellicht overwegen om ook een "dataset" of "obt" (one big table) macro toe te voegen.
>     Willen mensen toch hebben. Ik nu ook voor mijn mcp laag (hoewel ik dat als views boven op
>     de fact/dims doe).
> 16. Elementary doet irritant bij mij (geeft telkens database errors) en ik heb het ook
>     helemaal niet nodig. Ik kan de package uitzetten via mijn dbt_project maar er staat een
>     hard coded "on-run-end" in de optimist package die dan faalt. Waar is die voor? Ik zou
>     denken dat dat standaard aanstaat. Als die een doel heeft dan zou ik die conditioneel
>     maken obv of de package aan of uitstaat.
>
> Nou, dat was hem voor nu. Over een paar dagen op vakantie en ik neem de laptop niet mee dus
> ligt nu ff stil. Later, als de AI laag klaar is ga ik ook nog proberen alles op docker te
> draaien. Misschien wel met Sqllite want duckdb in deze vorm zie ik niet zitten (en voegt ook
> niet veel toe met mijn data volumes) maar dat kijk ik nog wel ff. Je weet me te vinden als je
> nog vragen hebt.
>
> Succes, Thijs

---

## Laaghangend fruit — opgelost

### #2 — `dbt parse` faalt meteen na `datavloot new`
`_dim_configs.yml` en `_fct_configs.yml` in het scaffold-template hadden een `models:` key
zonder items (alles eronder was commentaar), waardoor dbt het als `null` i.p.v. een lijst las.

- **Fix:** `models:` → `models: []` in
  [`_dim_configs.yml`](../datavloot_platform/templates/scaffold/models/business/dimensions/_dim_configs.yml)
  en
  [`_fct_configs.yml`](../datavloot_platform/templates/scaffold/models/business/facts/_fct_configs.yml).
- **Demo:** geen actie nodig — de demo's eigen `_dim_configs.yml`/`_fct_configs.yml` hebben al
  echte entries (dim_vessel, dim_port, fct_port_event, …), dus `models:` is daar al een
  geldige lijst.

### #3 — dlt-voorbeeld in `assets.py` werkt niet
Het commentaar-voorbeeld gaf `destination="duckdb"` met `credentials=` als los kwarg mee — dat
werkt niet met de huidige dlt-API.

- **Fix:** voorbeeld in
  [`assets.py`](../datavloot_platform/templates/scaffold/project_platform/assets.py) aangepast
  naar `destination=duckdb_destination(credentials=str(DB_PATH))`, gelijk aan het werkende
  patroon in de demo.
- **Demo:** geen actie nodig — de demo's eigen
  [`assets.py`](../datavloot_platform/templates/demo/noaa_platform/assets.py) gebruikte dit
  patroon al correct; dat was juist de referentie voor de fix.

### #4 — Alle links op PyPI kapot
`pyproject.toml` gebruikt `README.md` als PyPI long_description. Relatieve markdown-links
werken op GitLab (relatief aan de repo-root) maar breken op PyPI.

- **Fix:** 5 relatieve links in [`README.md`](../README.md) omgezet naar absolute
  `https://gitlab.com/datavloot/datavloot-toolkit/-/blob/main/...` URLs.
- **Bonus:** tijdens het fixen viel op dat de `packages.yml`-snippet in `README.md` naar
  `gitlab.com/datavloot/optimist-toolkit.git` verwees — een andere/oude repo-naam dan de
  huidige `datavloot-toolkit` (bevestigd via `git remote -v`). Ook gecorrigeerd, en meteen
  meegenomen op alle overige plekken in de repo — zie "Bonus vondst" onderaan.
- **Demo:** geen actie nodig — de demo heeft geen eigen PyPI-package, dus geen relatieve-link-
  op-PyPI probleem.

### #9 — SQL editor gaat niet lekker om met lange/brede tabellen
De resultatentabel zat in één `overflow-x-auto` div zonder hoogtelimiet: bij veel rijen moest je
naar beneden scrollen (kolomtitels raak je dan kwijt) voordat je opzij kon scrollen.

- **Fix:** in
  [`QueryPanel.js`](../datavloot_platform/crowsnest/frontend/components/QueryPanel.js) de
  tabel-wrapper naar `overflow-auto max-h-[500px]` gezet en `<thead>` sticky (`sticky top-0
  z-10`) gemaakt, zodat je binnen één scroll-container zowel verticaal als horizontaal kunt
  scrollen met de kolomtitels altijd zichtbaar.
- **Extra:** exact dezelfde bug zat in de "Sample data"-tabel van
  [`CatalogPanel.js`](../datavloot_platform/crowsnest/frontend/components/CatalogPanel.js)
  (tabel-preview bij het browsen door de catalogus) — dezelfde fix daar ook toegepast, al had
  Thijs dat specifieke component niet genoemd.
- **Verificatie:** `npm run build` in `datavloot_platform/crowsnest/frontend` draait schoon
  (compileert, genereert de static export). Niet handmatig in de browser getest — dat zou ik
  nog willen doen voordat dit als volledig afgerond geldt.
- **Demo:** geen actie nodig — Crows Nest is één gedeelde frontend-app, niet per project
  (scaffold/demo) getemplate.

### #14 — `generate_surrogate_key` macro dispatchen
De macro was een gewone macro, niet overschrijfbaar zonder de package te forken.

- **Fix:** omgezet naar het standaard dbt dispatch-patroon in
  [`generate_surrogate_key.sql`](../dbt/optimist/macros/business/generate_surrogate_key.sql):
  `generate_surrogate_key()` roept nu `adapter.dispatch('generate_surrogate_key', 'optimist')`
  aan, met de bestaande hash-implementatie als `default__generate_surrogate_key`. Projecten
  kunnen nu hun eigen `optimist__generate_surrogate_key` macro definiëren om de strategie te
  overschrijven (bv. geen hash voor een date-dimensie, zoals Thijs wilde).
- **Demo:** geen actie nodig. `dbt/optimist/` is de enige bron die in git zit — de
  `dbt_packages/optimist/` map die je soms onder `templates/demo/` ziet staan is een
  gitignored, lokaal `dbt deps`-artefact (niet getrackt, niet onderdeel van wat `datavloot
  demo` kopieert — `cli.py` sluit `dbt_packages` expliciet uit). Elk project, inclusief de
  demo, haalt het package altijd vers op via `dbt deps` uit `dbt/optimist/`, dus deze fix komt
  daar vanzelf in terecht.
- **Vervolg (bij #10-13/15 opgepakt):** `dim_date` en `dim_time` zelf gebruiken nu ook geen hash
  meer — hun surrogate key is een plain integer (`date_key` YYYYMMDD, `time_key` seconden sinds
  middernacht), gegenereerd door de nieuwe
  [`generate_date_key`](../dbt/optimist/macros/business/generate_date_key.sql) macro. Die is ook
  los bruikbaar voor een fact die zijn eigen date-key kolom wil (gegarandeerd gelijk aan
  `dim_date.date_key`). Zie #10 hieronder voor de volledige context.

### #6 — Instruction file wordt niet opgepikt door Copilot
Bleek na uitzoeken kleiner dan gedacht. `README.md:133` documenteert al expliciet het
bedoelde, tool-onafhankelijke mechanisme: *"Hand it to your AI assistant at the start of a
session so it knows the toolkit's conventions."* `data-instructions.md` is bewust generiek
geschreven ("AI agents (e.g. Claude)"), niet Copilot-specifiek — het is een gewoon
markdown-bestand dat je handmatig als context meegeeft, dus dat werkt sowieso ongeacht Copilot,
Claude Code, of iets anders. Wat Thijs probeerde was Copilot's *passieve* auto-discovery
(automatisch oppikken zonder het zelf te noemen) aan de praat te krijgen — dat is een aparte,
editor-specifieke feature met eigen naamgevings-/locatie-eisen, los van het geadviseerde pad.

Het echte gat: die instructie stond alleen diep in de README (regel 133), niet in wat je direct
na het scaffolden te zien krijgt.

- **Fix:** de "Next steps"-output van `datavloot new` en `datavloot demo` in
  [`cli.py`](../datavloot_platform/cli.py#L64-L92) zegt nu expliciet "Hand data-instructions.md
  to your AI assistant at the start of a session" in plaats van het vage "See
  data-instructions.md" (dat er bij `cmd_demo` voorheen zelfs helemaal niet stond).
- **Bewust niet gedaan:** geen Copilot-specifieke `*.instructions.md`-bestandsnaam of
  `.github/instructions/`-locatie toegevoegd — dat blijft een aparte, editor-specifieke
  toevoeging bovenop een mechanisme dat al werkt, en is niet opgepakt.
- **Demo:** meegenomen — `cli.py` is gedeelde code, de fix werkt voor `cmd_new` én `cmd_demo`
  tegelijk.

### #7 — Business logica lekt naar de staging laag
Geen bug, maar een documentatiegat: nergens stond expliciet welk type logica in staging vs.
business hoort.

- **Fix:** richtlijn toegevoegd aan [`docs/source-layer.md`](source-layer.md) en
  [`docs/business-layer.md`](business-layer.md). Bewust als *guideline, geen harde regel*
  geformuleerd — de toolkit wordt door verschillende teams met verschillende manieren van
  werken gebruikt, dus niets hiervan wordt afgedwongen. Kern van het advies: houd de structuur
  van een source-model zo dicht mogelijk bij de bron (één source-model per bronbestand), zodat
  je 'm altijd kan terugvergelijken met het bronsysteem. Concreet: geen joins en geen
  aggregaties in source-modellen — hernoemen/casten/dedupliceren binnen één tabel en
  audit-kolommen zijn wel prima. Joins en aggregaties horen in de business layer, waar dat nu
  ook expliciet terugverwijst naar de source layer.
- **Demo-impact:** geen — generieke documentatie, niet project-specifiek.

---

## Major release — opgelost (#10, #11, #12, #13, #15)

Deze vijf waren stuk voor stuk breaking changes aan `build_fact`/`build_dimension` of de
ingebouwde `dim_date`/`dim_time` — precies de categorie die
[`docs/releasing.md`](releasing.md) aanraadde te bundelen in één bewuste major release
(`optimist-v1.0.0`, nog niet getagd) in plaats van los te schepen. Volledige plan, inclusief
twee tussentijdse correcties (geen dimensie-op-dimensie joins, demo krijgt geen dataset), staat
in de plan-geschiedenis van deze sessie; hier de samenvatting per punt.

**Kernontwerp achter #11 en #12 samen:** een dimensie's surrogate key heet voortaan altijd
`<entity>_key` — de modelnaam met een voorloop-`dim_` eraf (`dim_vessel` → `vessel_key`). Een
fact die naar die dim joint, krijgt die kolom standaard onder diezelfde naam binnen. Zie
"How dimension keys are named" in [`docs/business-layer.md`](business-layer.md).

### #10 — `dim_time`/`dim_date` niet configureerbaar (seconden i.p.v. minuten)
- **Fix:** `dim_date`/`dim_time` zijn omgezet van package-modellen naar macros —
  [`build_dim_date`](../dbt/optimist/macros/business/build_dim_date.sql) en
  [`build_dim_time`](../dbt/optimist/macros/business/build_dim_time.sql). Elk project heeft nu
  zijn eigen `dim_date.sql`/`dim_time.sql` die de macro aanroepen, dus geen package-fork meer
  nodig om te configureren. `dim_time`'s grain (`minute`/`second`) wordt bepaald door de
  `dim_time_grain` var (default `minute`, exact hetzelfde patroon als de bestaande
  `dim_date_start`/`dim_date_end` vars). Beide dims gebruiken nu ook een plain integer key i.p.v.
  een hash (zie #14's vervolg hierboven) — `dim/optimist/models/business/` (de oude
  package-modellen) is verwijderd.
- **Demo-impact:** `templates/demo/models/business/dimensions/dim_date.sql` en `dim_time.sql`
  toegevoegd (roepen de macro's aan, `dim_time` op minute-grain — ongewijzigd gedrag). Demo's
  `_dim_configs.yml` heeft nu expliciete entries voor beide (voorheen "provided by the toolkit,
  no entry needed"). `fct_port_event`'s `dimensions`-relaties naar `dim_date`/`dim_time` zijn
  aangepast (zie #11).

### #11 — Fact macro: kolommen en dim-key dubbel opgeven
Twee losse vragen, twee losse oplossingen:

1. **`columns` dubbel t.o.v. de docs-yaml** — bewust **niet** automatisch afgeleid van de
   gedocumenteerde kolommen: dat zou stilletjes kolommen laten verdwijnen zodra de documentatie
   een keer niet compleet is, en dat risico weegt zwaarder dan het typewerk dat het bespaart.
   In plaats daarvan verduidelijkt in `docs/business-layer.md`: `meta.columns` is optioneel en
   selecteert al standaard alles; je hoeft de lijst dus meestal niet te herhalen.
2. **`key: dim_vessel_key` dubbel t.o.v. de dim's eigen config** — wél als code opgelost: de
   default voor `key` in een `dimensions`-relatie is nu `optimist.dim_key_name(dim)`, exact
   dezelfde afleiding als de dim's eigen default surrogate-key-naam. In de meeste gevallen hoef
   je `key`/`alias` dus helemaal niet meer op te geven.
- **Demo-impact:** `fct_port_event`'s `dimensions`-config in
  `templates/demo/models/business/facts/_fct_configs.yml` mist nu overal de `key:`-regel; de
  bestaande `alias: event_date_key`/`event_time_key` bleven staan (nodig omdat `dim_date`/
  `dim_time` elk maar één keer in deze fact voorkomen, maar wel een beschrijvender naam
  verdienen dan het kale `date_key`/`time_key`).

### #12 — Naamgeving `fk` / `dim_fk` / `key` onduidelijk
- **Fix:** **niet** de YAML-attribuutnamen zelf hernoemd (`fk`/`dim_fk`/`key` blijven ongewijzigd
  — dat was niet expliciet gevraagd en had extra, ongevraagde API-churn betekend). In plaats
  daarvan is de onderliggende conventie gefixt: zie "Kernontwerp" hierboven. Dat lost de
  praktische pijn op (welke kolomnaam hoort waar) zonder de config-taal zelf te veranderen.
- **Demo-impact:** alle key-kolommen in de demo herbenoemd volgens de nieuwe conventie:
  `dim_vessel_key` → `vessel_key`, `dim_port_key` → `port_key`, `dim_sea_state_key` →
  `sea_state_key`, in zowel `_dim_configs.yml` (per dim) als `_fct_configs.yml`/
  `demo/README.md`'s voorbeeldquery (`fct_port_event` FK-kolommen en `data_tests.relationships`).

### #13 — Relatie met een dim op basis van meerdere kolommen
- **Fix:** `fk`, `dim_fk`, en `fk_cast` in `build_fact.sql`'s `dimensions`-relaties accepteren nu
  ook een lijst i.p.v. een losse kolomnaam, voor een dim met een samengestelde natuurlijke sleutel
  (bv. een vessel die pas uniek is per `[name, type]` — dat kon via `build_dimension`'s
  `surrogate_key.columns` altijd al, alleen kon een fact er niet op joinen). Compiler-error als
  `fk`/`dim_fk`-lijsten niet dezelfde lengte hebben. Als bonus, in dezelfde code-aanraking: een
  compiler-error als twee dimension-relaties per ongeluk op dezelfde outputkolom uitkomen
  (voorheen zwegen ze en kreeg je een verwarrende dubbele-kolom SQL-fout).
- **Demo-impact:** geen — de demo heeft momenteel geen composite-key joins nodig. Wel
  gedocumenteerd met een voorbeeld in `docs/business-layer.md`.

### #15 — "Dataset"/OBT (one big table) macro
- **Fix:** nieuwe [`build_dataset`](../dbt/optimist/macros/business/build_dataset.sql) macro.
  Bewust **niet dimensionaal** — geen surrogate key, geen dim-joins — na jouw verduidelijking dat
  het een platte tabel met expliciet aangegeven kolommen moet zijn, die je zelf al hebt
  voorbereid (typisch via een `source_cte` die je eigen joins doet, zoals je nu al met views
  doet). `columns` is verplicht (in tegenstelling tot `build_fact`/`build_dimension`, waar het
  optioneel is) — een dataset is bedoeld als bewust gecureerde output, geen "select alles".
- **Demo-impact:** bewust géén voorbeeld toegevoegd aan de demo — jouw expliciete voorkeur. De
  macro is wel volledig gedocumenteerd en beschikbaar; alleen `templates/scaffold/` kreeg de
  lege `models/business/datasets/_dataset_configs.yml`-placeholder (consistent met hoe
  `_dim_configs.yml`/`_fct_configs.yml` daar ook leeg beginnen).

---

## Uit te zoeken

Voor elk punt: wat Thijs meldt, wat er nodig is om het uit te zoeken, en of/hoe dit doorgetrokken
moet worden naar de demo.

### #1 — `dbt deps` waarschuwing (git package gepind op `main`)
Verwacht gedrag zolang er geen getagde releases zijn — `revision: main` staat er bewust met een
`# pin to a tag or commit SHA` comment.

- **Plan van aanpak:** vastgesteld, uitgeschreven in [`docs/releasing.md`](releasing.md) —
  SemVer per `dbt/optimist`, immutable release-tags (`optimist-vX.Y.Z`) plus een meebewegende
  major-branch (`optimist-0.x`, straks `optimist-1.x`, …) die per patch/minor release
  fast-forward wordt. Consumers pinnen op `revision: optimist-0.x` (volgt automatisch 0.1, 0.2,
  0.3, …) of op een exacte tag; de stap naar `optimist-1.x` bij een breaking release is altijd
  een bewuste, handmatige wijziging in hun eigen `packages.yml`. `dbt/optimist/dbt_project.yml`
  is alvast gecorrigeerd van het stale `version: '1.0.0'` naar `'0.1.0'` om als startpunt te
  dienen.
- **Nog niet gedaan:** de eerste tag/branch (`optimist-v0.1.0` / `optimist-0.x`) daadwerkelijk
  aanmaken en pushen, en `revision:` in de scaffold/demo `packages.yml` daarop wijzen. Dat raakt
  gedeelde remote-state en hoort vanaf `main` te gebeuren, niet vanaf deze feature-branch — zie
  "First release" in `docs/releasing.md`.
- **Demo-impact:** [`templates/demo/packages.yml`](../datavloot_platform/templates/demo/packages.yml)
  heeft exact dezelfde `revision: main` pin — wordt tegelijk met de scaffold-versie op
  `optimist-0.x` gezet zodra de eerste release wordt gecut.

### #5 — `datavloot start` geeft steeds "Error loading repository location" warning
`cmd_start` in [`cli.py`](../datavloot_platform/cli.py#L121-L153) start `dagster dev` als
subprocess en wacht op `/health`. De warning komt uit Dagster zelf, wat wijst op een exception
die bij het laden van de code location wordt opgevangen.

- **Plan van aanpak:** reproduceren met een vers scaffold-project, `dagster dev --log-level
  debug` gebruiken om te zien of het een race condition is (dagster reload voordat `dbt
  parse`/manifest klaar is) of een structurele fout in `definitions.py`.
- **Demo-impact:** geen aparte actie — `cli.py` is gedeelde code, een fix hier werkt automatisch
  voor scaffold én demo projecten.

### #8 — DuckDB concurrency / DuckLake
Grootste architecturale punt. DuckLake-ondersteuning bestaat al opt-in in
[`db.py`](../datavloot_platform/crowsnest/db.py#L18-L32) (via
`CROWSNEST_DUCKLAKE_CATALOG_PATH`) maar is geen default en niet doorgetrokken naar dlt/dbt
profiles.

- **Plan van aanpak:** uitzoeken wat nodig is om DuckLake end-to-end (dlt destination + dbt
  profile + Crows Nest) te laten werken, kosten/baten afwegen tegen wachten op DuckDB's eigen
  concurrency-verbetering later dit jaar, en de bestaande retry-logica (3x met 0.15s backoff)
  evalueren als tussenoplossing.
- **Demo-impact:** als er voor DuckLake als (optionele) default wordt gekozen, moet de demo als
  referentievoorbeeld dienen: `templates/demo/noaa_platform/assets.py` (dlt destination) en
  `dbt/optimist` se `profiles.yml`/demo `profiles.yml` zouden dan ook een DuckLake-variant
  moeten tonen.

### #16 — Elementary `on-run-end` faalt ook als package is uitgezet
**Let op — nog niet gereproduceerd.** De hook staat in
[`dbt/optimist/dbt_project.yml:30-31`](../dbt/optimist/dbt_project.yml#L30-L31) — dat is het
root project van de **toolkit zelf**, niet van het scaffold- of demo-template. Zowel
[`templates/scaffold/dbt_project.yml`](../datavloot_platform/templates/scaffold/dbt_project.yml)
als
[`templates/demo/dbt_project.yml`](../datavloot_platform/templates/demo/dbt_project.yml)
bevatten géén `on-run-end` hook. Per dbt-semantiek draaien hooks uit een *geïnstalleerd package*
normaal niet mee in het project dat het package installeert.

- **Plan van aanpak:** eerst reproduceren — draait deze hook echt mee in een gescaffold project,
  en zo ja hoe? (Mogelijk relevant: werkt Thijs rechtstreeks tegen `dbt/optimist` i.p.v. tegen
  een gescaffold project, of gebruikt hij een oudere/andere versie van het package?) Pas na
  reproductie een conditionele guard bouwen (bv. op basis van of elementary daadwerkelijk
  geïnstalleerd/enabled is).
- **Demo-impact:** zelfde vraag geldt voor de demo — eerst reproduceren of de demo dit probleem
  ook heeft voordat er iets aan wordt gebouwd.

---

## Bonus vondst — inconsistente repo-naam in templates (opgelost)

Niet door Thijs gemeld, maar tegengekomen tijdens het fixen van #4. De huidige git remote is
`https://gitlab.com/datavloot/datavloot-toolkit.git`, maar meerdere bestanden verwezen nog naar
oudere namen (`gitlab.com/datavloot/optimist-toolkit` en zelfs `gitlab.com/mycelium4483613/
optimist-toolkit`, vermoedelijk over van een eerdere rename). Inmiddels overal doorgetrokken
naar `gitlab.com/datavloot/datavloot-toolkit`:

- `README.md` (onderdeel van #4)
- `datavloot_platform/templates/scaffold/packages.yml`
- `datavloot_platform/templates/scaffold/data-instructions.md`
- `datavloot_platform/templates/demo/packages.yml`
- `datavloot_platform/templates/demo/package-lock.yml`
- `datavloot_platform/templates/demo/data-instructions.md`
- `datavloot_platform/templates/demo/README.md`
- `datavloot_platform/templates/demo/conversation.md`
- `docs/getting-started.md`

De display-tekst "optimist-toolkit" (de productnaam, zoals in `[optimist-toolkit](...)`-
linkteksten) is bewust ongemoeid gelaten — alleen de URL's/repo-slugs zijn gecorrigeerd. Het
bijbehorende `docs/backlog.md`-item dat dit als openstaande taak beschreef, is verwijderd.

Aanvullend gefixt: `datavloot_platform/templates/demo/README.md` verwees ook naar een niet-
bestaand `optimist demo`-commando (de CLI heet `datavloot`) en installeerde via
`pip install git+https://...` in plaats van de sinds kort beschikbare PyPI-route. Beide
gecorrigeerd naar `pip install datavloot[optimist]` + `datavloot demo`, gelijk aan de
instructies in root-`README.md`.
