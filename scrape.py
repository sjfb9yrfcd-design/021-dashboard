#!/usr/bin/env python3
"""Haalt standen en programma's op en bouwt docs/index.html.

Gebruik:
    python scrape.py            normaal draaien
    python scrape.py --debug    ook de ruwe pagina's opslaan in debug/ en tonen wat er gevonden is
"""
import datetime as dt
import html as H
import json
import re
import statistics
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
DATA = ROOT / "data.json"
OUT = ROOT / "docs" / "index.html"
TEMPLATE = ROOT / "template.html"
DEBUG = "--debug" in sys.argv
KAMPIOEN_HANDMATIG = "--kampioen" in sys.argv  # handmatig doorgeven dat Feyenoord najaarskampioen is

# ---------------------------------------------------------------- instellingen
SEASON_START_YEAR = 2026  # seizoen 2026-2027 (voor datums zonder jaartal)
# Aantal wedstrijden per team in de O21-najaarscompetitie. None = automatisch: thuis en uit tegen
# elke tegenstander, dus 2 x (aantal teams - 1). Vul een getal in als het aantal anders is.
O21_TOTAL_GAMES = None
# Zoveel dagen na het behalen van de najaarstitel blijven banner en confetti staan; daarna alleen een subtiele badge.
FEEST_DAGEN = 14

SECTIONS = {
    "o21": {
        "stand_url": "https://www.feyenoord.com/nl/academy/teams/feyenoord-o21",
        "focus": {
            "Feyenoord O21": ["https://www.feyenoord.com/nl/academy/teams/feyenoord-o21"],
        },
        "highlight": ["Feyenoord O21"],
    },
    "td": {
        "stand_url": "https://www.vi.nl/competities/tweede-divisie/2026-2027/stand",
        "focus": {
            "Jong Sparta": [
                "https://www.vi.nl/clubs/jong-sparta/wedstrijden",
            ],
            "Jong Almere City": [
                "https://www.vi.nl/clubs/jong-almere-city/wedstrijden",
            ],
        },
        "highlight": ["Jong Sparta", "Jong Almere City"],
    },
}

# Alleen voor de tabellen: lange namen korter weergeven (links de naam op de site, rechts de korte naam)
SHORT_NAMES = {
    "FC Twente / Heracles O21": "Twente/Heracles O21",
    "FC Twente / Heracles Academie": "Twente/Heracles",
    "Volendam (amateurs)": "Volendam (am.)",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; o21-dashboard/1.0; persoonlijk project)"}
MONTHS = {"jan": 1, "feb": 2, "mrt": 3, "maa": 3, "apr": 4, "mei": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12}
WEEKDAYS = ["ma", "di", "wo", "do", "vr", "za", "zo"]
MONTHS_NL = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]

RE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
RE_DMY = re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})")
RE_DM_NAME = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?(?:\s+(\d{4}))?")
RE_TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
RE_SCORE = re.compile(r"(?<!\d)(\d{1,2})\s*[-\u2013:]\s*(\d{1,2})(?!\d)")


# ---------------------------------------------------------------- ophalen
def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    if DEBUG:
        d = ROOT / "debug"
        d.mkdir(exist_ok=True)
        name = re.sub(r"[^a-z0-9]+", "_", url.lower())[-80:] + ".html"
        (d / name).write_text(r.text, encoding="utf-8")
    return BeautifulSoup(r.text, "html.parser")


# ---------------------------------------------------------------- stand
def to_int(s):
    s = s.strip().replace("\u2212", "-").replace("+", "")
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def layouts(nums, need_goals):
    """Alle indelingen (kolompositie van gespeeld, w/g/v, punten, doelpunten) die rekenkundig kloppen.

    Controle: gewonnen + gelijk + verloren = gespeeld, punten = 3 x gewonnen + gelijk,
    en doelpunten voor - tegen = doelsaldo.
    """
    n, out = len(nums), []
    for gi in range(n):
        for i in range(n - 2):
            if gi in (i, i + 1, i + 2) or nums[i] + nums[i + 1] + nums[i + 2] != nums[gi]:
                continue
            p = 3 * nums[i] + nums[i + 1]
            for j in range(n):
                if nums[j] != p or j in (gi, i, i + 1, i + 2):
                    continue
                used = {gi, i, i + 1, i + 2, j}
                if not need_goals:
                    out.append((gi, i, j, None, None))
                    continue
                for x in range(n - 1):
                    y = x + 1
                    if x in used or y in used:
                        continue
                    if any(c not in used | {x, y} and nums[c] == nums[x] - nums[y] for c in range(n)):
                        out.append((gi, i, j, x, y))
    return out


def parse_standings(soup):
    """Zoekt de eerste tabel met rijen als: positie, team, cijfers..., punten.

    De kolomvolgorde hoeft niet bekend te zijn: per tabel wordt de indeling gekozen die voor de meeste
    rijen rekenkundig klopt.
    """
    from collections import Counter
    for table in soup.find_all("table"):
        raw = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 5 or to_int(cells[0]) is None:
                continue
            team_idx = next((i for i, c in enumerate(cells[1:], 1)
                             if re.search(r"[A-Za-z]{2}", c)), None)
            if team_idx is None:
                continue
            rest = cells[team_idx + 1:]
            goals = next((c for c in rest if re.fullmatch(r"\d+\s*[-:]\s*\d+", c)), None)
            nums = [to_int(c) for c in rest if to_int(c) is not None]
            if len(nums) < 3:
                continue
            raw.append((to_int(cells[0]), cells[team_idx], nums, goals, cells))
        if len(raw) < 4:
            continue
        # Sommige sites zetten een afkorting achter de clubnaam ("Jong Sparta SP2"): die halen we weg
        codes = [t.split()[-1] for _, t, _, _, _ in raw if len(t.split()) > 1]
        if (len(codes) >= 0.8 * len(raw) and len(set(codes)) > 2
                and all(re.fullmatch(r"[A-Z0-9]{2,4}", c) for c in codes)):
            raw = [(p, t.rsplit(" ", 1)[0] if len(t.split()) > 1 else t, n, g, c) for p, t, n, g, c in raw]
        votes = Counter()
        for _, _, nums, goals, _ in raw:
            for lay in set(layouts(nums, goals is None)):
                votes[lay] += 1
        best = votes.most_common(1)[0][0] if votes else None
        if best and votes[best] < 0.6 * len(raw):  # te weinig rijen sluiten aan: terugvallen op de eenvoudige indeling
            best = None
        rows = []
        for pos, team, nums, goals, cells in raw:
            if best and len(nums) > max(i for i in best if i is not None):
                gi, i, j, x, y = best
                gs, pt = nums[gi], nums[j]
                dv, dt_ = ([int(v) for v in re.split(r"\s*[-:]\s*", goals)] if goals else [nums[x], nums[y]])
            else:  # terugval als er geen sluitende indeling is
                gs, pt = nums[0], nums[-1]
                if goals:
                    dv, dt_ = [int(v) for v in re.split(r"\s*[-:]\s*", goals)]
                elif len(nums) >= 4:
                    dv, dt_ = nums[-4], nums[-3]
                else:
                    continue
            if DEBUG and len(rows) < 3:
                print("   stand rij:", cells, "->", gs, dv, dt_, pt)
            rows.append({"pos": pos, "team": team, "gs": gs,
                         "dv": dv, "dt": dt_, "ds": dv - dt_, "pt": pt})
        return rows
    raise ValueError("geen standtabel gevonden")


# ---------------------------------------------------------------- wedstrijden
def parse_date(text):
    m = RE_ISO.search(text)
    if m:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    m = RE_DMY.search(text)
    if m:
        return dt.date(int(m[3]), int(m[2]), int(m[1]))
    for m in RE_DM_NAME.finditer(text):
        mon = MONTHS.get(m[2][:3].lower())
        if mon:
            year = int(m[3]) if m[3] else (SEASON_START_YEAR if mon >= 7 else SEASON_START_YEAR + 1)
            try:
                return dt.date(year, mon, int(m[1]))
            except ValueError:
                pass
    return None


def find_teams(text, names):
    """Teams in volgorde van voorkomen; langste namen eerst, zodat 'Volendam (amateurs)' wint van 'Volendam'."""
    low, taken, found = text.lower(), [], []
    for name in sorted(names, key=len, reverse=True):
        start = 0
        while True:
            i = low.find(name.lower(), start)
            if i < 0:
                break
            span = (i, i + len(name))
            if not any(span[0] < b and a < span[1] for a, b in taken):
                taken.append(span)
                found.append((i, name))
            start = i + 1
    return list(dict.fromkeys(n for _, n in sorted(found)))


def parse_matches(soup, names, focus):
    seen, out = set(), []
    for el in soup.find_all(["tr", "li", "article", "div", "a"]):
        text = el.get_text(" ", strip=True)
        if not text or len(text) > 300:
            continue
        teams = find_teams(text, names)
        if len(teams) != 2 or focus not in teams:
            continue
        date = None
        t = el.find("time")
        if t is not None and t.get("datetime"):
            date = parse_date(t["datetime"])
        date = date or parse_date(text)
        if date is None:  # datum staat soms in een kop boven de wedstrijd
            prev = el.find_previous(string=lambda s: s and parse_date(s))
            date = parse_date(prev) if prev else None
        if date is None:
            continue
        clean = RE_ISO.sub(" ", RE_DMY.sub(" ", text))
        tm = RE_TIME.search(clean)
        clean2 = RE_TIME.sub(" ", clean)
        clean2 = RE_DM_NAME.sub(lambda m: " " if MONTHS.get(m[2][:3].lower()) else m[0], clean2)
        sc = RE_SCORE.search(clean2)
        score = f"{sc[1]}-{sc[2]}" if sc else None
        if score is None and date <= dt.date.today():
            # sommige sites zetten de twee cijfers los van elkaar, zonder streepje
            rest = clean2
            for t_ in teams:
                rest = re.sub(re.escape(t_), " ", rest, flags=re.I)
            nums = re.findall(r"(?<![\w'])(\d{1,2})(?![\w'])", rest)
            if len(nums) == 2:
                score = f"{nums[0]}-{nums[1]}"
        key = (date, teams[0], teams[1])
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": date.isoformat(), "time": f"{int(tm[1]):02d}:{tm[2]}" if tm else "",
                    "home": teams[0], "away": teams[1],
                    "score": score})
        if DEBUG:
            print("   gevonden rij:", repr(text[:200]))
    return out


def pick(matches, today):
    played = [m for m in matches if m["score"] and m["date"] <= today]
    upcoming = [m for m in matches if not m["score"] and m["date"] >= today]
    last = max(played, key=lambda m: m["date"]) if played else None
    nxt = sorted(upcoming, key=lambda m: (m["date"], m["time"]))[:2]
    return {"last": last, "next": nxt}


# ---------------------------------------------------------------- bouwen
def esc(s):
    return H.escape(str(s))


def fmt_date(iso, time=""):
    d = dt.date.fromisoformat(iso)
    s = f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS_NL[d.month - 1]}"
    return esc(s) + (f"<br>{esc(time)}" if time else "")


def team_html(name, focus):
    return f"<b>{esc(name)}</b>" if name == focus else esc(name)


def match_row(m, focus, invert=False):
    cls, label = "n", ""
    if m["score"]:
        a, b = [int(x) for x in m["score"].split("-")]
        mine, theirs = (a, b) if m["home"] == focus else (b, a)
        cls = "w" if mine > theirs else "l" if mine < theirs else "g"
        if invert:  # bij de Jong-teams is een verlies gunstig voor Feyenoord
            cls = {"w": "l", "l": "w"}.get(cls, cls)
        label = m["score"]
    else:
        label = "thuis" if m["home"] == focus else "uit"
    return (f'<div class="m"><div class="d">{fmt_date(m["date"], "" if m["score"] else m["time"])}</div>'
            f'<div class="t">{team_html(m["home"], focus)} - {team_html(m["away"], focus)}</div>'
            f'<div class="s {cls}">{esc(label)}</div></div>')


def match_block(info, focus, invert=False):
    h = '<div class="lab">Vorige uitslag</div>'
    h += match_row(info["last"], focus, invert) if info.get("last") else '<div class="d">Niet gevonden</div>'
    h += '<div class="lab">Volgende wedstrijden</div>'
    h += "".join(match_row(m, focus, invert) for m in info.get("next", [])) or '<div class="d">Niet gevonden</div>'
    return h


def table_html(rows, highlight, cls, strip=""):
    head = ("<thead><tr><th>#</th><th>Team</th><th title='Gespeeld'>GS</th><th>DV</th>"
            "<th>DT</th><th>DS</th><th>Pt</th></tr></thead>")
    body = ""
    for r in rows:
        row_cls = f' class="{cls}"' if any(h.lower() == r["team"].lower() for h in highlight) else ""
        ds = f'{r["ds"]:+d}' if r["ds"] else "0"
        shown = SHORT_NAMES.get(r["team"], r["team"])
        if strip and shown.endswith(strip):
            shown = shown[: -len(strip)]
        body += (f'<tr{row_cls}><td>{r["pos"]}</td><td title="{esc(r["team"])}">{esc(shown)}</td><td>{r["gs"]}</td>'
                 f'<td>{r["dv"]}</td><td>{r["dt"]}</td><td>{ds}</td><td class="pt">{r["pt"]}</td></tr>')
    return f"<table>{head}<tbody>{body}</tbody></table>"


def punten(n):
    return f"{n} punt" if n == 1 else f"{n} punten"


def is_najaarskampioen(table, total_games=None):
    """True als Feyenoord O21 wiskundig niet meer te achterhalen is in de najaarscompetitie.

    Alle concurrenten kunnen met hun resterende wedstrijden maximaal (punten + 3 x resterend) halen;
    Feyenoord moet daar strikt boven staan (bij gelijk aantal punten telt het nog niet als zeker).
    """
    fey = next((r for r in table if r["team"] == "Feyenoord O21"), None)
    others = [r for r in table if r["team"] != "Feyenoord O21"]
    if not fey or not others:
        return False
    total = total_games or O21_TOTAL_GAMES or 2 * (len(table) - 1)
    best_rival = max(r["pt"] + 3 * max(total - r["gs"], 0) for r in others)
    return fey["pt"] > best_rival


def markeer_kampioen(data, today, handmatig=False):
    """Legt vast (in data.json) sinds wanneer Feyenoord najaarskampioen is. Wordt nooit meer overschreven.

    handmatig=True (via `python scrape.py --kampioen`) legt de titel vast, ook als de bron nog niet bijgewerkt is."""
    if "najaarskampioen" in data:
        return
    if handmatig:
        data["najaarskampioen"] = {"sinds": today, "handmatig": True}
    elif is_najaarskampioen(data["o21"]["table"]):
        data["najaarskampioen"] = {"sinds": today}


def kampioen_dagen(data, today=None):
    """None = niet kampioen; anders het aantal dagen sinds de titel (0 = vandaag)."""
    sinds = data.get("najaarskampioen", {}).get("sinds")
    if not sinds:  # nog niet vastgelegd, maar wel zeker volgens de huidige tabel
        return 0 if is_najaarskampioen(data["o21"]["table"]) else None
    today = today or dt.date.today()
    return max((today - dt.date.fromisoformat(sinds)).days, 0)


def jong_referentie(td):
    """De club waarop het laagst geklasseerde Jong-team moet inlopen: de 8e club zonder Jong-team.

    Feyenoord heeft genoeg aan \u00e9\u00e9n Jong-team in het rechterrijtje. Dat lukt alleen niet als allebei de Jong-teams
    in het linkerrijtje (plek 1 t/m 9) eindigen; er blijven dan 7 plekken over voor de overige clubs. Zolang er nog
    geen Jong-team in de top 8 staat is dit dus de nummer 8; staat er al \u00e9\u00e9n in de top 8, dan is het de nummer 9."""
    namen = SECTIONS["td"]["highlight"]
    jong = [r for r in td if r["team"] in namen]
    rest = sorted((r for r in td if r["team"] not in namen), key=lambda r: r["pos"])
    index = 9 - len(jong)
    return rest[index] if jong and len(rest) > index else None


def jong_status(td):
    """Laagst geklasseerde Jong-team en zijn afstand (in punten) tot de referentie (zie jong_referentie)."""
    jong = [r for r in td if r["team"] in SECTIONS["td"]["highlight"]]
    ref = jong_referentie(td)
    if not jong or not ref:
        return None
    low = max(jong, key=lambda r: r["pos"])
    return {"team": low["team"], "pos": low["pos"], "pt": low["pt"], "gap": ref["pt"] - low["pt"],
            "referentie": ref["team"], "ref_pos": ref["pos"], "ref_pt": ref["pt"]}


def update_historie(data, today):
    """Bewaart per speelronde de positie van het laagste Jong-team en de afstand tot het linkerrijtje.

    De speelronde is het mediane aantal gespeelde wedstrijden in de Tweede Divisie. Binnen dezelfde ronde
    wordt de laatste stand bewaard, zodat de waarde aan het eind van de ronde blijft staan."""
    td = data["td"]["table"]
    status = jong_status(td)
    if not td or not status:
        return
    ronde = statistics.median_low([r["gs"] for r in td])
    data.setdefault("historie", {})[str(ronde)] = dict(status, ronde=ronde, datum=today)


def verloop_svg(hist):
    W, H, P = 300, 96, 16
    ys = [e["gap"] for e in hist]
    lo, hi = min(ys), max(ys)
    span = max(hi - lo, 1)
    n = len(hist)
    pts = [(P + (W - 2 * P) * i / (n - 1), P + (H - 2 * P - 8) * (1 - (e["gap"] - lo) / span))
           for i, e in enumerate(hist)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    toon = set(range(n)) if n <= 12 else {0, n - 1, ys.index(lo), ys.index(hi)}
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="var(--red)"><title>Ronde {e["ronde"]}: '
        f'{e["gap"]} punten</title></circle>'
        + (f'<text x="{x:.1f}" y="{y - 7:.1f}" text-anchor="middle" font-size="10" fill="var(--ink)">{e["gap"]}</text>'
           if i in toon else "")
        for i, ((x, y), e) in enumerate(zip(pts, hist)))
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Punten tot het linkerrijtje per speelronde" '
            f'style="width:100%;max-width:520px;height:auto;margin-top:12px">'
            f'<polyline points="{poly}" fill="none" stroke="var(--red)" stroke-width="2"/>{dots}'
            f'<text x="{P}" y="{H - 2}" font-size="10" fill="var(--mute)">ronde {hist[0]["ronde"]}</text>'
            f'<text x="{W - P}" y="{H - 2}" text-anchor="end" font-size="10" fill="var(--mute)">'
            f'ronde {hist[-1]["ronde"]}</text></svg>')


def jong_afstand_tekst(td, row):
    """Afstand van een Jong-team tot het linkerrijtje, als korte tekst (gerekend tot jong_referentie)."""
    ref = jong_referentie(td)
    nr10 = next((r for r in td if r["pos"] == 10), None)
    if row["pos"] > 9 and ref:
        gap = max(ref["pt"] - row["pt"], 0)
        naam = esc(SHORT_NAMES.get(ref["team"], ref["team"]))
        if gap == 0:
            return f"gelijk met het linkerrijtje (nr. {ref['pos']}: {naam})"
        return f"{punten(gap)} van het linkerrijtje (nr. {ref['pos']}: {naam})"
    if nr10:
        return f"in het linkerrijtje, {punten(max(row['pt'] - nr10['pt'], 0))} boven het rechterrijtje"
    return "in het linkerrijtje"


def volgende_regel(info, focus):
    """Eén regel met de eerstvolgende wedstrijd, voor op het overzicht."""
    nxt = (info or {}).get("next") or []
    if not nxt:
        return ""
    m = nxt[0]
    d = dt.date.fromisoformat(m["date"])
    wanneer = f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS_NL[d.month - 1]}" + (f" {m['time']}" if m.get("time") else "")
    thuis = m["home"] == focus
    tegen = (m["away"] if thuis else m["home"]).removesuffix(" O21")
    return f'<p class="nx">Volgende: {esc(wanneer)} \u00b7 {esc(tegen)} ({"thuis" if thuis else "uit"})</p>'


def overzicht_html(data):
    """Korte samenvatting voor het tabblad Overzicht: Feyenoord O21 en de twee Jong-teams."""
    o21, td = data["o21"]["table"], data["td"]["table"]
    kaarten = []

    fey = next((r for r in o21 if r["team"] == "Feyenoord O21"), None)
    if fey:
        pill = ' <span class="pill">\U0001F3C6 Najaarskampioen</span>' if kampioen_dagen(data) is not None else ""
        anderen = sorted((r for r in o21 if r is not fey), key=lambda r: r["pos"])
        if fey["pos"] == 1 and anderen:
            tweede = anderen[0]
            gap = f'{punten(fey["pt"] - tweede["pt"])} voor op nr. 2 ({esc(SHORT_NAMES.get(tweede["team"], tweede["team"]).removesuffix(" O21"))})'
        elif anderen:
            kop = min(o21, key=lambda r: r["pos"])
            gap = f'{punten(kop["pt"] - fey["pt"])} achter op nr. 1'
        else:
            gap = ""
        kaarten.append(
            f'<div class="card sum"><h3>Feyenoord O21{pill}</h3>'
            f'<div class="big">{fey["pos"]}e<small>najaarscompetitie</small></div>'
            f'<p class="kv">{punten(fey["pt"])} uit {fey["gs"]} wedstrijden</p>'
            + (f'<p class="gap">{gap}</p>' if gap else "")
            + volgende_regel(data["o21"]["matches"].get("Feyenoord O21"), "Feyenoord O21")
            + '<a class="more" href="#o21">Volledige stand \u2192</a></div>')

    jong = [r for r in td if r["team"] in SECTIONS["td"]["highlight"]]
    laagste = max(jong, key=lambda r: r["pos"])["team"] if jong else None
    for naam in SECTIONS["td"]["focus"]:
        row = next((r for r in td if r["team"] == naam), None)
        if not row:
            continue
        pill = ' <span class="pill">laagst geklasseerd</span>' if naam == laagste else ""
        kaarten.append(
            f'<div class="card sum"><h3>{esc(naam)}{pill}</h3>'
            f'<div class="big">{row["pos"]}e<small>Tweede Divisie</small></div>'
            f'<p class="kv">{punten(row["pt"])} uit {row["gs"]} wedstrijden</p>'
            f'<p class="gap">{jong_afstand_tekst(td, row)}</p>'
            + volgende_regel(data["td"]["matches"].get(naam), naam)
            + '<a class="more" href="#tweede-divisie">Volledige stand \u2192</a></div>')
    return '<div class="sums">' + "".join(kaarten) + "</div>"


def historie_html(data):
    hist = sorted(data.get("historie", {}).values(), key=lambda e: e["ronde"])
    if not hist:
        return ""
    rows, prev = [], None
    for e in hist:
        if prev is None:
            delta = "\u2013"
        else:
            d = e["gap"] - prev["gap"]
            delta = ("0" if d == 0 else f'<span class="up">+{d}</span>' if d > 0
                     else f'<span class="down">\u2212{-d}</span>')
        afstand = "links" if e["pos"] <= 9 else str(e["gap"])
        wie = f' title="Tot nr. {e["ref_pos"]}: {esc(e["referentie"])} ({e["ref_pt"]} pt)"' if e.get("referentie") else ""
        rows.append(f'<tr><td>{e["ronde"]}</td><td title="{esc(e["team"])}">{esc(e["team"])}</td>'
                    f'<td>{e["pos"]}</td><td>{e["pt"]}</td><td class="pt"{wie}>{afstand}</td><td>{delta}</td></tr>')
        prev = e
    tabel = ("<table><thead><tr><th>Ronde</th><th>Laagste Jong-team</th><th>Pos</th><th>Pt</th>"
             "<th title='Punten tot het linkerrijtje'>Afst.</th><th title='Verandering t.o.v. vorige ronde'>\u0394</th>"
             "</tr></thead><tbody>" + "".join(reversed(rows)) + "</tbody></table>")
    grafiek = verloop_svg(hist) if len(hist) >= 3 else ""
    uitleg = ('<p class="uitleg">Afst. = punten van het laagste Jong-team tot de 8e club zonder Jong-team (de nummer 8, '
              'of de nummer 9 als een Jong-team al in de top 8 staat), want beide Jong-teams moeten in het linkerrijtje '
              'eindigen om Feyenoord tegen te houden; &Delta; = verandering ten opzichte van de vorige ronde. Een grotere afstand (groen) is gunstig voor Feyenoord, een kleinere (rood) niet. '
              'Per speelronde wordt de laatst bekende stand bewaard.</p>')
    return ('<h2 class="j">Jong-teams: verloop per speelronde</h2><div class="grid"><div class="card scroll">'
            + tabel + grafiek + uitleg + '</div></div>')


def feest_html(data, today=None):
    """Feestelijke extra's (gouden banner, confetti, trofee bij de naam) zodra Feyenoord najaarskampioen is."""
    dagen = kampioen_dagen(data, today)
    if dagen is None:
        return ""
    if dagen >= FEEST_DAGEN:  # subtiel: alleen een kleine badge, geen confetti
        return '<div class="badge">\U0001F3C6 Najaarskampioen O21</div>'
    kleuren = ["#d4111c", "#f5c518", "#9e0c14", "#ffe27a", "var(--ink)"]
    stukjes = []
    for i in range(40):  # vaste waarden (geen random), zodat de pagina niet elke run verandert
        breed = 6 + (i % 4) * 3
        stukjes.append(
            f'<i style="left:{(i * 37) % 100}%;width:{breed}px;height:{breed + 4}px;'
            f'background:{kleuren[i % len(kleuren)]};animation-duration:{4 + (i % 5) * 0.7:.1f}s;'
            f'animation-delay:{(i % 10) * 0.35:.2f}s"></i>')
    return ('<div class="feest">\U0001F3C6 Feyenoord O21 is najaarskampioen!</div>'
            '<style>tr.me td:nth-child(2)::after{content:" \U0001F3C6"}</style>'
            '<div class="confetti" aria-hidden="true">' + "".join(stukjes) + '</div>')


def promotie_html(data):
    """Uitlegblok over promotie, met de actuele rangschikking van Feyenoord O21 en de Jong-teams."""
    o21 = data["o21"]["table"]
    td = data["td"]["table"]
    feyenoord = next((r for r in o21 if r["team"] == "Feyenoord O21"), None)
    pos_fey = f'op de <b>{feyenoord["pos"]}e</b> plek' if feyenoord else "<b>onbekend</b>"
    kampioen = ("<b>Feyenoord is niet meer te achterhalen in de najaarscompetitie en is dus "
                "najaarskampioen! Op naar de voorjaarscompetitie.</b> "
                if kampioen_dagen(data) is not None else "")

    jong = [r for r in td if r["team"] in SECTIONS["td"]["highlight"]]
    if jong:
        low = max(jong, key=lambda r: r["pos"])
        ref = jong_referentie(td)
        nr10 = next((r for r in td if r["pos"] == 10), None)
        if low["pos"] > 9 and ref:
            gap = max(ref["pt"] - low["pt"], 0)
            naam = esc(SHORT_NAMES.get(ref["team"], ref["team"]))
            afstand = (f'op gelijke stand met het linkerrijtje (nr. {ref["pos"]}: {naam})' if gap == 0
                       else f'op <b>{punten(gap)}</b> van het linkerrijtje (nr. {ref["pos"]}: {naam})')
        elif nr10:
            afstand = f'nog in het linkerrijtje, <b>{punten(low["pt"] - nr10["pt"])}</b> boven het rechterrijtje'
        else:
            afstand = "in het linkerrijtje"
        tweede = (f'Op dit moment is <b>{esc(low["team"])}</b> het laagst geklasseerde Jong-team in de '
                  f'Tweede Divisie, op de <b>{low["pos"]}e</b> plek, {afstand}. Omdat Feyenoord maar \u00e9\u00e9n Jong-team in het '
                  'rechterrijtje nodig heeft, telt de afstand tot de 8e club zonder Jong-team (de nummer 8, of de '
                  'nummer 9 als een Jong-team al in de top 8 staat).')
    else:
        tweede = "De positie van de Jong-teams is op dit moment niet bekend."

    return ('<div class="card info">'
            "<p>Om te kunnen promoveren moet er aan twee voorwaarden worden voldaan.</p>"
            "<p>Ten eerste moet Feyenoord algeheel kampioen worden van de O21-competitie. Deze competitie is "
            "gesplitst in een najaarscompetitie en een voorjaarscompetitie. In de najaarscompetitie staat "
            f"Feyenoord {pos_fey}. {kampioen}Als een club beide competities wint is zij automatisch algeheel kampioen. "
            "Anders volgt een beslissingswedstrijd.</p>"
            "<p>Ten tweede moet \u00e9\u00e9n van de twee Jong-ploegen in de Tweede Divisie minimaal in het "
            f"rechterrijtje eindigen. {tweede}</p>"
            "<p>Als dat zo is, dan volgt een play off over twee wedstrijden. Wat ook nog kan is dat een Jong "
            "team 17e of 18e eindigt. Indien dat het geval is hoeft de algeheel kampioen van de O21-competitie "
            "geen beslissingswedstrijd te spelen.</p></div>")


def build_html(data, warnings):
    t = TEMPLATE.read_text(encoding="utf-8")
    o, d = data["o21"], data["td"]
    cards = "".join(
        f'<div class="card"><h3>{esc(f)}</h3>{match_block(d["matches"].get(f, {}), f, invert=True)}</div>'
        for f in SECTIONS["td"]["focus"])
    warn = "".join(f'<div class="warn">{esc(w)}</div>' for w in warnings)
    now = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M")
    return (t.replace("{{UPDATED}}", esc(now))
            .replace("{{WARNINGS}}", warn)
            .replace("{{FEEST}}", feest_html(data))
            .replace("{{OVERZICHT}}", overzicht_html(data))
            .replace("{{PROMOTIE}}", promotie_html(data))
            .replace("{{O21_TABLE}}", table_html(o["table"], SECTIONS["o21"]["highlight"], "me", " O21"))
            .replace("{{O21_MATCHES}}", match_block(o["matches"]["Feyenoord O21"], "Feyenoord O21"))
            .replace("{{TD_TABLE}}", table_html(d["table"], SECTIONS["td"]["highlight"], "jong"))
            .replace("{{TD_CARDS}}", cards)
            .replace("{{HISTORIE}}", historie_html(data) or '<div class="card">Nog geen historie beschikbaar.</div>'))


# ---------------------------------------------------------------- hoofdprogramma
def scrape_section(key, today):
    cfg = SECTIONS[key]
    table = parse_standings(fetch(cfg["stand_url"]))
    names = [r["team"] for r in table]
    matches = {}
    for focus, urls in cfg["focus"].items():
        found = []
        for url in urls:
            try:
                found += parse_matches(fetch(url), names, focus)
            except Exception as e:  # een club-pagina mag falen zonder de rest te breken
                print(f"WAARSCHUWING {focus}: {url}: {e}")
        merged = {}
        for m in found:
            k = (m["date"], m["home"], m["away"])
            old = merged.get(k)
            if old is None or (m["score"] and not old["score"]) or (m["time"] and not old["time"] and not old["score"]):
                merged[k] = m
        found = list(merged.values())
        matches[focus] = pick(found, today)
        if DEBUG:
            print(f"\n{focus}: {len(found)} wedstrijden gevonden")
            for m in sorted(found, key=lambda m: m["date"]):
                print("  ", m)
    return {"table": table, "matches": matches}


def main():
    today = dt.date.today().isoformat()
    old = json.loads(DATA.read_text()) if DATA.exists() else {}
    data, warnings, fresh = dict(old), [], set()
    for key in SECTIONS:
        try:
            data[key] = scrape_section(key, today)
            fresh.add(key)
            print(f"{key}: OK ({len(data[key]['table'])} teams)")
        except Exception as e:
            print(f"FOUT bij {key}: {e}")
            if key in old:
                warnings.append(f"Kon '{key}' niet verversen; oude gegevens worden getoond.")
            else:
                sys.exit(f"Geen gegevens voor '{key}' en geen eerdere versie. Draai: python scrape.py --debug")
    markeer_kampioen(data, today, KAMPIOEN_HANDMATIG)
    if "td" in fresh:
        update_historie(data, today)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(build_html(data, warnings), encoding="utf-8")
    print(f"Geschreven: {OUT}")


if __name__ == "__main__":
    main()
