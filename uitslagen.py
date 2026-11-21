#!/usr/bin/env python3
"""Maakt een plaatje (1600x900) met de uitslagen van Feyenoord O21 en de Jong-teams, plus per Jong-team het
verschil in punten met de nummer 8 van de Tweede Divisie (de referentieclub, zie afstand()). Leest data.json (zoals scrape.py die bewaart).

Kleuren: groen = gunstig voor Feyenoord (winst van O21, verlies van een Jong-team), rood = ongunstig,
geel = gelijkspel.

De afstand wordt gerekend tot de 8e club zonder Jong-team (de nummer 8, of de nummer 9 als een Jong-team al in
de top 8 staat): Feyenoord heeft genoeg aan één Jong-team in het rechterrijtje, dus beide Jong-teams moeten in het
linkerrijtje eindigen om Feyenoord tegen te houden.

Gebruik:  python uitslagen.py                      -> docs/uitslagen.png en docs/uitslagen.txt
          python uitslagen.py --vanaf 2026-11-21   -> alsof het die datum is (handig om te testen)
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

from plaatje import (ROOT, W, H, INK, MUTE, LINE, RED, REDD, TEAMS, WEEKDAYS, MONTHS, font, kort)

GROEN, ROOD, GEEL = "#1E8A4C", "#D4111C", "#F2B705"
KLEUR = {"gunstig": GROEN, "ongunstig": ROOD, "gelijk": GEEL}


def recente_uitslag(info, today, dagen=2):
    """De laatste uitslag, maar alleen als die van de afgelopen dagen is (anders is de bron nog niet bijgewerkt)."""
    m = (info or {}).get("last")
    if not m or not m.get("score") or not re.search(r"\d+\s*[-\u2013:]\s*\d+", m["score"]):
        return None
    d = dt.date.fromisoformat(m["date"])
    return m if today - dt.timedelta(days=dagen) <= d <= today else None


def beoordeel(m, club, sectie):
    """Geeft (uitkomst, eigen doelpunten, tegendoelpunten); uitkomst is gunstig, ongunstig of gelijk voor Feyenoord."""
    h, a = (int(x) for x in re.findall(r"\d+", m["score"])[:2])
    ons, zij = (h, a) if m["home"] == club else (a, h)
    if ons == zij:
        return "gelijk", ons, zij
    gewonnen = ons > zij
    return ("gunstig" if gewonnen == (sectie == "o21") else "ongunstig"), ons, zij


def afstand(td, naam):
    """(positie, punten achter de referentie, referentieclub) van een Jong-team; punten is None in het linkerrijtje.

    De referentie is de 8e club zonder Jong-team: Feyenoord hoeft maar één Jong-team in het rechterrijtje te hebben,
    dus beide Jong-teams moeten in het linkerrijtje (plek 1 t/m 9) eindigen om Feyenoord tegen te houden. Staat er
    nog geen Jong-team in de top 8, dan is dat de nummer 8; staat er al één in de top 8, dan de nummer 9."""
    jong = {n for s, n, _ in TEAMS if s == "td"}
    row = next((r for r in td if r["team"] == naam), None)
    rest = sorted((r for r in td if r["team"] not in jong), key=lambda r: r["pos"])
    index = 9 - len(jong)
    if not row or len(rest) <= index:
        return None
    ref = rest[index]
    return row["pos"], (max(ref["pt"] - row["pt"], 0) if row["pos"] > 9 else None), ref


def punten(n):
    return f"{n} punt" if n == 1 else f"{n} punten"


def maak(data, today):
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    rijen = []
    for sectie, club, label in TEAMS:
        rijen.append((sectie, club, label, recente_uitslag(data[sectie]["matches"].get(club), today)))
    datums = [dt.date.fromisoformat(m["date"]) for *_, m in rijen if m]
    dag = max(datums) if datums else today

    d.rectangle((0, 0, W, 150), fill=RED)
    d.rectangle((0, 150, W, 158), fill=REDD)
    d.text((56, 52), "De uitslagen", font=font(60, True), fill="#FFFFFF", anchor="lm")
    d.text((56, 112), "Feyenoord O21 en de Jong-teams", font=font(32), fill="#FFE5E7", anchor="lm")
    d.text((W - 56, 82), f"{WEEKDAYS[dag.weekday()]} {dag.day} {MONTHS[dag.month - 1]}", font=font(54, True),
           fill="#FFFFFF", anchor="rm")

    y0, hh, gap = 180, 150, 14
    for i, (sectie, club, label, m) in enumerate(rijen):
        y = y0 + i * (hh + gap)
        d.rounded_rectangle((40, y, W - 40, y + hh), radius=22, fill="#FFFFFF", outline=LINE, width=3)
        d.text((80, y + 32), label.upper(), font=font(22, True), fill=RED, anchor="lm")
        if not m:
            d.text((80, y + 98), f"{kort(club)}: uitslag volgt", font=font(42), fill=MUTE, anchor="lm")
            continue
        uitkomst, ons, zij = beoordeel(m, club, sectie)
        x = 80
        for k, naam in enumerate((m["home"], m["away"])):
            f = font(46, naam == club)
            tekst = kort(naam) + ("  -  " if k == 0 else "")
            d.text((x, y + 78), tekst, font=f, fill=INK if naam == club else "#3A2D30", anchor="lm")
            x += d.textlength(tekst, font=f)
        woord = {"gunstig": "wint" if sectie == "o21" else "verliest", "ongunstig": "verliest" if sectie == "o21" else "wint"}
        onderschrift = "Gelijkspel" if uitkomst == "gelijk" else f"{kort(club)} {woord[uitkomst]}"
        d.text((80, y + 126), onderschrift, font=font(24), fill=MUTE, anchor="lm")
        kleur = KLEUR[uitkomst]
        d.rounded_rectangle((W - 80 - 230, y + 25, W - 80, y + 125), radius=26, fill=kleur)
        d.text((W - 80 - 115, y + 77), m["score"].replace(" ", ""), font=font(64, True),
               fill=INK if uitkomst == "gelijk" else "#FFFFFF", anchor="mm")

    # afstand tot het linkerrijtje
    yb = y0 + 3 * (hh + gap) + 6
    td = data["td"]["table"]
    jong = [n for s, n, _ in TEAMS if s == "td"]
    ref = next((r[2] for r in (afstand(td, n) for n in jong) if r), None)
    kop = (f"TWEEDE DIVISIE: VERSCHIL MET NUMMER {ref['pos']} ({kort(ref['team'])}, {punten(ref['pt'])})".upper()
           if ref else "TWEEDE DIVISIE")
    kopfont = next((font(z, True) for z in range(26, 17, -1) if d.textlength(kop, font=font(z, True)) <= W - 112),
                   font(18, True))
    d.text((56, yb + 14), kop, font=kopfont, fill=RED, anchor="lm")
    for j, naam in enumerate(jong):
        x0 = 40 + j * 780
        d.rounded_rectangle((x0, yb + 42, x0 + 740, yb + 170), radius=22, fill="#FDE3E5")
        d.text((x0 + 34, yb + 68), naam, font=font(30, True), fill=INK, anchor="lm")
        res = afstand(td, naam)
        if not res:
            continue
        pos, gap, ref = res
        if gap is None:
            d.text((x0 + 34, yb + 130), "in het linkerrijtje", font=font(42, True), fill=REDD, anchor="lm")
        elif gap == 0:
            d.text((x0 + 34, yb + 130), f"gelijk met nummer {ref['pos']}", font=font(42, True), fill=REDD, anchor="lm")
        else:
            f1 = font(68, True)
            d.text((x0 + 34, yb + 130), str(gap), font=f1, fill=RED, anchor="lm")
            d.text((x0 + 34 + d.textlength(str(gap), font=f1) + 18, yb + 134),
                   f"punt achter nummer {ref['pos']}" if gap == 1 else f"punten achter nummer {ref['pos']}",
                   font=font(34), fill=INK, anchor="lm")

    d.text((56, H - 20), "Groen = gunstig voor Feyenoord (winst van O21, verlies van een Jong-team). "
           "Rood = ongunstig. Geel = gelijkspel.", font=font(22), fill=MUTE, anchor="lm")
    return img, rijen, dag


def tekst(data, rijen, dag):
    regels = []
    for sectie, club, _, m in rijen:
        if m:
            regels.append(f'{kort(m["home"])} - {kort(m["away"])} {m["score"].replace(" ", "")}')
    td = data["td"]["table"]
    kop = f"De uitslagen van {WEEKDAYS[dag.weekday()]} {dag.day} {MONTHS[dag.month - 1]}:"

    def bouw(met_club):
        stand = []
        for _, naam, _ in (t for t in TEAMS if t[0] == "td"):
            res = afstand(td, naam)
            if res:
                pos, gap, ref = res
                if gap is None:
                    stand.append(f"{naam}: in het linkerrijtje")
                else:
                    zin = "gelijk met" if gap == 0 else f"{punten(gap)} achter"
                    stand.append(f"{naam}: {zin} nr. {ref['pos']}" + (f" ({kort(ref['team'])})" if met_club else ""))
        return kop + "\n\n" + "\n".join(regels) + "\n\n" + "\n".join(stand) + "\n\n#Feyenoord #TweedeDivisie"

    tekst_ = bouw(True)
    return tekst_ if len(tekst_) <= 300 else bouw(False)  # Bluesky staat maximaal 300 tekens toe


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data.json"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "uitslagen.png"))
    ap.add_argument("--vanaf", help="datum JJJJ-MM-DD (standaard vandaag)")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.vanaf) if a.vanaf else dt.date.today()
    data = json.loads(Path(a.data).read_text(encoding="utf-8"))
    img, rijen, dag = maak(data, today)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    out.with_name("uitslagen.txt").write_text(tekst(data, rijen, dag), encoding="utf-8")
    print("Klaar:", out)
