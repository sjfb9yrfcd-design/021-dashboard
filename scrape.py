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
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
DATA = ROOT / "data.json"
OUT = ROOT / "docs" / "index.html"
TEMPLATE = ROOT / "template.html"
DEBUG = "--debug" in sys.argv

# ---------------------------------------------------------------- instellingen
SEASON_START_YEAR = 2026  # seizoen 2026-2027 (voor datums zonder jaartal)

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


JONG_LOWER_THAN = 9  # een Jong-team moet lager staan dan deze plek (dus 10e of lager)
TEXT_UP = "himmelhoch jauchzend"
TEXT_DOWN = "zum Tode betrübt"


def mood_html(data):
    """Feyenoord O21 eerste en minstens een Jong-team lager dan plek 9: blij. Anders: bedroefd."""
    first = any(r["team"] == "Feyenoord O21" and r["pos"] == 1 for r in data["o21"]["table"])
    jong_low = any(r["team"] in SECTIONS["td"]["highlight"] and r["pos"] > JONG_LOWER_THAN
                   for r in data["td"]["table"])
    if first and jong_low:
        return f'<div class="banner up">{esc(TEXT_UP)}</div>'
    return f'<div class="banner down">{esc(TEXT_DOWN)}</div>'


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
            .replace("{{MOOD}}", mood_html(data))
            .replace("{{O21_TABLE}}", table_html(o["table"], SECTIONS["o21"]["highlight"], "me", " O21"))
            .replace("{{O21_MATCHES}}", match_block(o["matches"]["Feyenoord O21"], "Feyenoord O21"))
            .replace("{{TD_TABLE}}", table_html(d["table"], SECTIONS["td"]["highlight"], "jong"))
            .replace("{{TD_CARDS}}", cards))


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
    data, warnings = dict(old), []
    for key in SECTIONS:
        try:
            data[key] = scrape_section(key, today)
            print(f"{key}: OK ({len(data[key]['table'])} teams)")
        except Exception as e:
            print(f"FOUT bij {key}: {e}")
            if key in old:
                warnings.append(f"Kon '{key}' niet verversen; oude gegevens worden getoond.")
            else:
                sys.exit(f"Geen gegevens voor '{key}' en geen eerdere versie. Draai: python scrape.py --debug")
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(build_html(data, warnings), encoding="utf-8")
    print(f"Geschreven: {OUT}")


if __name__ == "__main__":
    main()
