#!/usr/bin/env python3
"""Maakt een plaatje (1600x900) met het programma van Feyenoord O21 en de Jong-teams, inclusief de positie
van beide teams in hun competitie. Leest data.json (zoals scrape.py die bewaart).

Gebruik:  python plaatje.py                      -> docs/programma.png en docs/tweet.txt
          python plaatje.py --vanaf 2026-11-20   -> alsof het die datum is (handig om te testen)
"""
import argparse
import datetime as dt
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:  # korte clubnamen delen met scrape.py
    from scrape import SHORT_NAMES
except Exception:
    SHORT_NAMES = {}

ROOT = Path(__file__).parent
W, H = 1600, 900
INK, MUTE, LINE = "#1A1214", "#6B5559", "#EBD9DB"
RED, REDD, TINT = "#D4111C", "#9E0C14", "#FDE3E5"
WEEKDAYS = ["ma", "di", "wo", "do", "vr", "za", "zo"]
MONTHS = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]

# (sectie, club, label) in de volgorde waarin ze op het plaatje staan
TEAMS = [("o21", "Feyenoord O21", "O21 najaarscompetitie"),
         ("td", "Jong Sparta", "Tweede Divisie"),
         ("td", "Jong Almere City", "Tweede Divisie")]

FONT_DIRS = [ROOT / "fonts", Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/liberation"),
             Path("/usr/share/fonts/opentype/inter"), Path("/usr/share/fonts/truetype/google-fonts")]
FONT_FILES = {True: ["Barlow-Bold.ttf", "Inter-Bold.otf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Poppins-Bold.ttf"],
              False: ["Barlow-Regular.ttf", "Inter-Regular.otf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]}


def font(size, bold=False):
    for name in FONT_FILES[bold]:
        for d in FONT_DIRS:
            if (d / name).exists():
                return ImageFont.truetype(str(d / name), size)
    return ImageFont.load_default()


def kort(naam):
    naam = SHORT_NAMES.get(naam, naam)
    return naam.removesuffix(" O21")


def volgende(info, today):
    for m in (info or {}).get("next", []):
        if dt.date.fromisoformat(m["date"]) >= today:
            return m
    return None


def plek(table, naam):
    r = next((r for r in table if r["team"] == naam), None)
    return f'{r["pos"]}e' if r else ""


def badge(d, x, y, tekst, f, vol):
    """Tekent een afgerond label met de plaats; geeft de breedte terug."""
    if not tekst:
        return 0
    tw = d.textlength(tekst, font=f)
    w, h = tw + 34, 52
    d.rounded_rectangle((x, y, x + w, y + h), radius=26, fill=RED if vol else "#F1E8E9")
    d.text((x + w / 2, y + h / 2 + 1), tekst, font=f, fill="#FFFFFF" if vol else MUTE, anchor="mm")
    return w


def maak(data, today):
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    rijen = []
    for sectie, club, label in TEAMS:
        info = data[sectie]["matches"].get(club)
        rijen.append((sectie, club, label, volgende(info, today)))
    datums = sorted(dt.date.fromisoformat(m["date"]) for *_, m in rijen if m)

    # kop
    d.rectangle((0, 0, W, 150), fill=RED)
    d.rectangle((0, 150, W, 158), fill=REDD)
    if datums:
        a, b = datums[0], datums[-1]
        fmt = lambda x: f"{WEEKDAYS[x.weekday()]} {x.day} {MONTHS[x.month - 1]}"
        periode = fmt(a) if a == b else f"{fmt(a)} t/m {fmt(b)}"
    else:
        periode = "binnenkort"
    d.text((56, 52), "Het programma", font=font(60, True), fill="#FFFFFF", anchor="lm")
    d.text((56, 112), "Feyenoord O21 en de Jong-teams", font=font(32), fill="#FFE5E7", anchor="lm")
    d.text((W - 56, 82), periode, font=font(54, True), fill="#FFFFFF", anchor="rm")

    # rijen
    y0, hh, gap = 190, 198, 18
    for i, (sectie, club, label, m) in enumerate(rijen):
        y = y0 + i * (hh + gap)
        d.rounded_rectangle((40, y, W - 40, y + hh), radius=22, fill="#FFFFFF", outline=LINE, width=3)
        d.text((80, y + 38), label.upper(), font=font(24, True), fill=RED, anchor="lm")
        if not m:
            d.text((80, y + 120), "Geen wedstrijd gepland", font=font(40), fill=MUTE, anchor="lm")
            continue
        dd = dt.date.fromisoformat(m["date"])
        d.text((80, y + 100), f"{WEEKDAYS[dd.weekday()]} {dd.day} {MONTHS[dd.month - 1]}", font=font(52, True), fill=INK, anchor="lm")
        d.text((80, y + 156), m["time"] or "tijd volgt", font=font(40), fill=MUTE, anchor="lm")
        thuis = m["home"] == club
        tag = "THUIS" if thuis else "UIT"
        tw = d.textlength(tag, font=font(26, True)) + 40
        d.rounded_rectangle((W - 80 - tw, y + 34, W - 80, y + 80), radius=23, fill=TINT)
        d.text((W - 80 - tw / 2, y + 57), tag, font=font(26, True), fill=REDD, anchor="mm")
        table = data[sectie]["table"]
        for k, naam in enumerate((m["home"], m["away"])):
            eigen = naam == club
            yy = y + 44 + k * 62
            f = font(44, eigen)
            tekst = kort(naam)
            d.text((520, yy + 26), tekst, font=f, fill=INK if eigen else "#3A2D30", anchor="lm")
            badge(d, 520 + d.textlength(tekst, font=f) + 20, yy, plek(table, naam), font(30, True), eigen)
        d.line((470, y + 30, 470, y + hh - 30), fill=LINE, width=3)

    d.text((56, H - 22), "Het label achter een club is de huidige plaats in de competitie. Programma's kunnen verschuiven.",
           font=font(22), fill=MUTE, anchor="lm")
    return img, rijen


def tweet(rijen, data):
    regels = []
    for (sectie, club, label, m) in rijen:
        if not m:
            continue
        dd = dt.date.fromisoformat(m["date"])
        t = data[sectie]["table"]
        wedstrijd = " - ".join(f'{kort(n)} ({plek(t, n)})' if plek(t, n) else kort(n) for n in (m["home"], m["away"]))
        regels.append(f'{WEEKDAYS[dd.weekday()]} {dd.day} {MONTHS[dd.month - 1]} {m["time"]}: {wedstrijd}'.replace(": ", ": ", 1).strip())
    return "Het programma voor dit weekend:\n\n" + "\n".join(regels) + "\n\n#Feyenoord #Tweede Divisie".replace("#Tweede Divisie", "#TweedeDivisie")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data.json"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "programma.png"))
    ap.add_argument("--vanaf", help="datum JJJJ-MM-DD (standaard vandaag)")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.vanaf) if a.vanaf else dt.date.today()
    data = json.loads(Path(a.data).read_text(encoding="utf-8"))
    img, rijen = maak(data, today)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    out.with_name("tweet.txt").write_text(tweet(rijen, data), encoding="utf-8")
    print("Klaar:", out)
