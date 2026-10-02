# Feyenoord O21 en Jong-teams: automatisch dashboard

Een Python-script haalt standen en programma's op, bouwt een rood-witte pagina (`docs/index.html`) en
GitHub zet die gratis online via GitHub Pages. Een planning (`.github/workflows/update.yml`) draait het script
elke dag om ca. 07:00 en in het weekend 's middags en 's avonds.

## Stappenplan

### 1. GitHub-account en repository
1. Maak een gratis account op github.com (of log in).
2. Klik rechtsboven op **+** > **New repository**. Naam: `o21-dashboard`. Kies **Public** (nodig voor gratis GitHub Pages). Klik **Create repository**.

### 2. Bestanden uploaden
1. Pak de zip uit op je computer.
2. Klik in je lege repository op **uploading an existing file**.
3. Sleep de **inhoud** van de map erin: `scrape.py`, `template.html`, `data.json`, `requirements.txt`, `README.md` en de mappen `docs` en `.github`.
   - De map `.github` begint met een punt en is op Mac/Windows soms verborgen. Toon verborgen bestanden, of maak het bestand via **Add file > Create new file** met de naam `.github/workflows/update.yml` en plak de inhoud.
4. Klik **Commit changes**.

### 3. GitHub Pages aanzetten
1. Ga naar **Settings > Pages**.
2. Bij *Build and deployment*: Source = **Deploy from a branch**, Branch = **main**, map = **/docs**. Klik **Save**.
3. Na een minuut of twee staat bovenaan je link: `https://JOUWNAAM.github.io/o21-dashboard/`. Dit is de link voor je vriend.

### 4. Rechten voor de automatische update
1. Ga naar **Settings > Actions > General**.
2. Onderaan bij *Workflow permissions*: kies **Read and write permissions**. Klik **Save**.

### 5. Eerste keer testen
1. Ga naar het tabblad **Actions**, kies **Dashboard bijwerken** en klik **Run workflow**.
2. Wacht tot het bolletje groen is (ongeveer een minuut) en ververs je pagina-link.
3. Groen en de pagina klopt: klaar. Vanaf nu ververst het dashboard zichzelf.

## Als er iets misgaat
De pagina's van feyenoord.com en vi.nl heb ik niet live kunnen testen, dus het uitlezen kan de eerste keer
mislukken. Zo ga je te werk:
- Rood kruisje bij Actions: klik de run open, dan **update**, en kopieer de foutmelding.
- Je ziet nog de oude cijfers: het script bewaart bij een mislukte run de vorige gegevens en toont een rode melding op de pagina.
- Op je eigen computer (Python 3.10+): `pip install -r requirements.txt` en daarna `python scrape.py --debug`. Dat toont per team wat het script gevonden heeft en bewaart de ruwe pagina's in de map `debug/`.
- Plak de foutmelding of de debug-uitvoer in je chat met Claude. Dan pas ik het uitlezen aan.

## Aanpassen
- Andere teams of seizoen: bovenaan `scrape.py` in `SECTIONS` (de webadressen en de namen).
- Andere tijden: in `.github/workflows/update.yml` de regels onder `cron`. Tijden staan in UTC (in de zomer 2 uur eerder dan NL-tijd, in de winter 1 uur).
- Opmaak: `template.html`.

## Goed om te weten
- GitHub kan geplande taken na lange inactiviteit uitzetten. Zie je geen updates meer, ga dan naar Actions en klik **Enable**.
- Haal niet vaker op dan een paar keer per dag, en bekijk de gebruiksvoorwaarden van de bronsites.
- De Almere-clubpagina (`vi.nl/clubs/jong-almere-city/wedstrijden`) is een aanname van de webadres. Klopt die niet, dan toont de pagina "Niet gevonden" bij dat team; pas dan het adres aan in `SECTIONS`.
