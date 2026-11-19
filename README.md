# Feyenoord O21 en Jong-teams: automatisch dashboard

Een Python-script (`scrape.py`) haalt standen en programma's op (feyenoord.com voor de O21, vi.nl voor de
Tweede Divisie), bewaart ze in `data.json` en bouwt een rood-witte pagina (`docs/index.html`). GitHub zet die
gratis online via GitHub Pages. De pagina heeft vier tabbladen: Overzicht, O21, Tweede Divisie en Historie
(het verloop van de afstand van het laagste Jong-team tot het linkerrijtje).

Daarnaast maken twee extra scripts elke week een plaatje voor social media:

- `plaatje.py` maakt het **programma-plaatje** (vrijdag) en de bijbehorende tekst.
- `uitslagen.py` maakt het **uitslagen-plaatje** (zaterdagavond), inclusief de afstand van de Jong-teams tot het linkerrijtje.
- `bluesky.py` plaatst zo'n plaatje met tekst op Bluesky (optioneel).

## Wat staat waar

| Bestand | Wat het doet |
|---|---|
| `scrape.py` | Haalt standen en programma's op, werkt `data.json` bij en bouwt `docs/index.html` |
| `template.html` | De opmaak van de pagina |
| `data.json` | De laatst opgehaalde gegevens (wordt door het script bijgewerkt) |
| `plaatje.py` | Maakt `docs/programma.png` en `docs/tweet.txt` |
| `uitslagen.py` | Maakt `docs/uitslagen.png` en `docs/uitslagen.txt` |
| `bluesky.py` | Plaatst een plaatje en tekst op Bluesky |
| `requirements.txt` | De Python-pakketten (requests, beautifulsoup4, Pillow) |
| `.github/workflows/update.yml` | Ververst het dashboard |
| `.github/workflows/programma.yml` | Maakt het programma-plaatje en plaatst het |
| `.github/workflows/uitslagen.yml` | Maakt het uitslagen-plaatje en plaatst het |
| `docs/` | De map die GitHub Pages online zet (bevat ook de plaatjes) |

## Wanneer draait wat

Alle tijden zijn Amsterdamse tijd. In de workflows staan ze in UTC, met twee `cron`-regels per tijdstip (één voor
zomertijd, één voor wintertijd).

| Workflow | Wanneer | Wat |
|---|---|---|
| Dashboard bijwerken | Elke dag 18:00, zaterdag ook 20:00, dinsdag ook 13:00 | Ververst de pagina |
| Programma-plaatje maken | Vrijdag 17:00 | Ververst de standen, maakt het plaatje en plaatst het op Bluesky |
| Uitslagen-plaatje maken | Zaterdag 20:30 | Ververst de standen, maakt het plaatje en plaatst het op Bluesky |

De twee plaatjes-workflows controleren eerst hoe laat het in Amsterdam is, zodat er maar één keer per week een
plaatje wordt gemaakt, ook al staan er twee `cron`-regels. Alle drie de workflows delen één wachtrij
(`concurrency`), zodat ze elkaars wijzigingen niet in de weg zitten.

## Stappenplan

### 1. GitHub-account en repository
1. Maak een gratis account op github.com (of log in).
2. Klik rechtsboven op **+** > **New repository**. Naam: `o21-dashboard`. Kies **Public** (nodig voor gratis GitHub Pages). Klik **Create repository**.

### 2. Bestanden uploaden
1. Pak de zip uit op je computer.
2. Klik in je lege repository op **uploading an existing file**.
3. Sleep de **inhoud** van de map erin: `scrape.py`, `plaatje.py`, `uitslagen.py`, `bluesky.py`, `template.html`,
   `data.json`, `requirements.txt`, `README.md` en de mappen `docs` en `.github`.
   - De map `.github` begint met een punt en is op Mac/Windows soms verborgen. Toon verborgen bestanden, of maak de
     bestanden via **Add file > Create new file** met de namen `.github/workflows/update.yml`,
     `.github/workflows/programma.yml` en `.github/workflows/uitslagen.yml` en plak de inhoud.
4. Klik **Commit changes**.

### 3. GitHub Pages aanzetten
1. Ga naar **Settings > Pages**.
2. Bij *Build and deployment*: Source = **Deploy from a branch**, Branch = **main**, map = **/docs**. Klik **Save**.
3. Na een minuut of twee staat bovenaan je link: `https://JOUWNAAM.github.io/o21-dashboard/`. Dit is de link voor je vriend.

### 4. Rechten voor de automatische updates
1. Ga naar **Settings > Actions > General**.
2. Onderaan bij *Workflow permissions*: kies **Read and write permissions**. Klik **Save**.

### 5. Eerste keer testen
1. Ga naar het tabblad **Actions**, kies **Dashboard bijwerken** en klik **Run workflow**.
2. Wacht tot het bolletje groen is (ongeveer een minuut) en ververs je pagina-link.
3. Groen en de pagina klopt: klaar. Vanaf nu ververst het dashboard zichzelf.
4. Test de plaatjes op dezelfde manier met **Programma-plaatje maken** en **Uitslagen-plaatje maken**. Bij handmatig
   starten wordt de tijdcontrole overgeslagen, en het plaatje wordt alleen op Bluesky gezet als je het vinkje
   **plaatsen** aanzet. Het plaatje zelf staat daarna in de map `docs` (`programma.png` of `uitslagen.png`).

### 6. Bluesky koppelen (optioneel)
Zonder deze stap werkt het dashboard gewoon, alleen de automatische plaatsing op Bluesky mislukt.
1. Maak op Bluesky een **app-wachtwoord** aan (Instellingen > Privacy en beveiliging > App-wachtwoorden). Gebruik dus niet je gewone wachtwoord.
2. Ga in GitHub naar **Settings > Secrets and variables > Actions** en maak twee *repository secrets*:
   - `BLUESKY_HANDLE`: bijvoorbeeld `jouwnaam.bsky.social`
   - `BLUESKY_APP_PASSWORD`: het app-wachtwoord
3. Het script plaatst dezelfde tekst niet twee keer binnen 20 uur, dus een tweede run plaatst niets dubbel.

## Handmatig starten

Via **Actions**, de workflow kiezen en **Run workflow**:
- **Dashboard bijwerken** heeft de optie **kampioen**. Zet die aan als Feyenoord O21 najaarskampioen is, maar de
  bron dat nog niet laat zien. De titel wordt dan vastgelegd in `data.json` en de feestbanner verschijnt. Zonder die
  optie herkent het script de titel zelf zodra die wiskundig zeker is.
- **Programma-plaatje maken** en **Uitslagen-plaatje maken** hebben de optie **plaatsen** om het plaatje ook op Bluesky te zetten.

## Lokaal testen (Python 3.10+)

```
pip install -r requirements.txt
python scrape.py --debug                    # toont per team wat er gevonden is en bewaart de ruwe pagina's in debug/
python plaatje.py --vanaf 2026-11-20        # programma-plaatje, alsof het die datum is
python uitslagen.py --vanaf 2026-11-21      # uitslagen-plaatje, alsof het die datum is
python bluesky.py --droog                   # alleen tonen wat er geplaatst zou worden
```

Voor mooiere letters in de plaatjes kun je een map `fonts` toevoegen met `Barlow-Regular.ttf` en `Barlow-Bold.ttf`.
Zonder die map gebruikt het script een standaardlettertype.

## Als er iets misgaat
- Rood kruisje bij Actions: klik de run open, dan de naam van de job, en kopieer de foutmelding.
- Je ziet nog de oude cijfers: het script bewaart bij een mislukte run de vorige gegevens en toont een rode melding op de pagina.
- Een van de uitleesstappen faalt na een wijziging op feyenoord.com of vi.nl: draai lokaal `python scrape.py --debug`
  en plak de uitvoer in je chat met Claude. Dan pas ik het uitlezen aan.
- Het uitslagen-plaatje toont "uitslag volgt": de bron had de uitslag nog niet. Start de workflow later opnieuw
  met **Run workflow**.

## Aanpassen
- Andere teams, webadressen of namen: bovenaan `scrape.py` in `SECTIONS`.
- Ander seizoen: `SEASON_START_YEAR` in `scrape.py` (en de webadressen in `SECTIONS`).
- Aantal wedstrijden in de O21-najaarscompetitie: `O21_TOTAL_GAMES` in `scrape.py`. Standaard wordt dat berekend als
  twee keer het aantal tegenstanders. Dit bepaalt wanneer Feyenoord wiskundig najaarskampioen is.
- Hoe lang de feestbanner blijft staan: `FEEST_DAGEN` in `scrape.py` (daarna blijft alleen een kleine badge over).
- Kortere clubnamen in de tabellen en plaatjes: `SHORT_NAMES` in `scrape.py`.
- Andere tijden: de regels onder `cron` in de workflows. Die staan in UTC (in de zomer 2 uur eerder dan NL-tijd, in de winter 1 uur).
- Opmaak van de pagina: `template.html`. Opmaak van de plaatjes: `plaatje.py` en `uitslagen.py`.

## Goed om te weten
- GitHub kan geplande taken na lange inactiviteit uitzetten. Zie je geen updates meer, ga dan naar Actions en klik **Enable**.
- GitHub start geplande taken soms met enige vertraging. De plaatjes-workflows gaan alleen door als het in Amsterdam
  17:xx (programma) of 20:xx (uitslagen) is. Is een run meer dan een uur te laat, dan wordt hij overgeslagen. Start
  hem dan handmatig.
- Haal niet vaker op dan een paar keer per dag, en bekijk de gebruiksvoorwaarden van de bronsites.
- Bij de Jong-teams is een verlies gunstig voor Feyenoord. In de uitslagen is groen daarom gunstig voor Feyenoord,
  rood ongunstig en geel gelijkspel.
- Bluesky kort tekst af op 300 tekens.
