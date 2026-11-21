#!/usr/bin/env python3
"""Maakt het zondag-plaatje (1600x900): "Hoe staat het er in de Tweede Divisie voor?"

Het is het onderste deel van de promotie-infographic: de plekken 1 t/m 18 met daaronder de plek en de punten van
Jong Sparta, Jong Almere City, de referentieclub (zie hieronder) en de nummer 17. Leest data.json (zoals
scrape.py die bewaart).

De referentieclub is de 8e club zonder Jong-team (de nummer 8, of de nummer 9 als een Jong-team al in de top 8
staat): Feyenoord heeft genoeg aan één Jong-team in het rechterrijtje, dus beide Jong-teams moeten in het
linkerrijtje eindigen om Feyenoord tegen te houden. Zie scrape.jong_referentie.

Het weekend is goed (afstand van het laagst geplaatste Jong-team tot het linkerrijtje toegenomen), neutraal
(gelijk gebleven) of slecht (afgenomen) voor Feyenoord. De vorige afstand komt uit "historie" in data.json.

Schrijft naast docs/zondag.png ook docs/zondag.txt (Bluesky-tekst), docs/zondag.alt.txt (begin van de alt-tekst)
en docs/zondag.status ("JJJJ-MM-DD ja" of "nee": de workflow plaatst alleen bij "ja").

Gebruik:  python zondag.py                       -> alleen als een Jong-team dit weekend gespeeld heeft
          python zondag.py --forceer             -> altijd maken (om te testen)
          python zondag.py --vanaf 2026-11-22    -> alsof het die datum is
"""
import argparse
import datetime as dt
import json
import statistics
from pathlib import Path

from PIL import Image, ImageDraw

from plaatje import ROOT, W, H, INK, MUTE, LINE, RED, REDD, TINT, TEAMS, WEEKDAYS, MONTHS, font, kort
from scrape import jong_status
from uitslagen import recente_uitslag

PLEKKEN = 18
GRIJS = "#F1E8E9"


def punten(n):
    return f"{n} punt" if n == 1 else f"{n} punten"


def passend(d, tekst, maxbreedte, start, minimum=20, bold=False):
    """Het grootste lettertype (vanaf start) waarmee de tekst nog in maxbreedte past."""
    for size in range(start, minimum - 1, -1):
        f = font(size, bold)
        if d.textlength(tekst, font=f) <= maxbreedte:
            return f
    return font(minimum, bold)


def jong_namen():
    return [n for s, n, _ in TEAMS if s == "td"]


def rij(td, pos):
    return next((r for r in td if r["pos"] == pos), None)


def callouts(td, status):
    """{plek: (soort, club, punten)} voor de referentie, de Jong-teams en de nummer 17."""
    out = {}
    if status:
        out[status["ref_pos"]] = ("ref", status["referentie"], status["ref_pt"])
    for r in td:
        if r["team"] in jong_namen():
            out[r["pos"]] = ("jong", r["team"], r["pt"])
    r17 = rij(td, 17)
    if r17 and 17 not in out:
        out[17] = ("zeventien", r17["team"], r17["pt"])
    return dict(sorted(out.items()))


def vorige_gap(data, ronde):
    """Afstand van het laagste Jong-team aan het eind van de vorige speelronde, of None."""
    vorige = [e for k, e in data.get("historie", {}).items() if int(k) < ronde]
    return max(vorige, key=lambda e: e["ronde"])["gap"] if vorige else None


def oordeel(gap, eerder):
    """(woord, ontwikkeling) voor de Bluesky-tekst; None als er geen vorige afstand is."""
    if eerder is None or gap is None:
        return None
    if gap > eerder:
        return "goed", "toegenomen"
    if gap < eerder:
        return "slecht", "afgenomen"
    return "neutraal", "hetzelfde gebleven"


def zin(td, status):
    """Korte zin onder de titel."""
    if not status:
        return "Plek en punten van de Jong-teams in de Tweede Divisie"
    naam = kort(status["team"])
    if status["pos"] <= 9:
        return "Beide Jong-teams staan in het linkerrijtje"
    if status["gap"] <= 0:
        return f"{naam}, het laagste Jong-team, staat gelijk met het linkerrijtje"
    return f"{naam}, het laagste Jong-team, staat {punten(status['gap'])} van het linkerrijtje"


def pijl(d, van, naar, kleur, breed=4):
    (x0, y0), (x1, y1) = van, naar
    d.line((x0, y0, x1, y1), fill=kleur, width=breed)
    lengte = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 or 1
    ux, uy = (x1 - x0) / lengte, (y1 - y0) / lengte
    px, py = -uy, ux
    k = 18
    d.polygon([(x1, y1), (x1 - ux * k + px * 9, y1 - uy * k + py * 9), (x1 - ux * k - px * 9, y1 - uy * k - py * 9)],
              fill=kleur)


def maak(data, today):
    td = data["td"]["table"]
    status = jong_status(td)
    calls = callouts(td, status)
    ronde = statistics.median_low([r["gs"] for r in td]) if td else 0

    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)

    # kop
    d.rectangle((0, 0, W, 150), fill=RED)
    d.rectangle((0, 150, W, 158), fill=REDD)
    titel = "Hoe staat het er in de Tweede Divisie voor?"
    d.text((56, 56), titel, font=passend(d, titel, W - 112, 58, bold=True), fill="#FFFFFF", anchor="lm")
    korte_zin = zin(td, status)
    d.text((56, 114), korte_zin, font=passend(d, korte_zin, W - 112, 32), fill="#FFE5E7", anchor="lm")

    # kaart
    d.rounded_rectangle((40, 190, W - 40, 850), radius=22, fill="#FFFFFF", outline=LINE, width=3)
    x0, breedte = 80, W - 160
    cel = breedte / PLEKKEN
    d.text((x0, 244), "Linkerrijtje: plek 1 t/m 9", font=font(26), fill=MUTE, anchor="lm")
    d.text((x0 + cel * 9, 244), "Rechterrijtje: plek 10 t/m 16", font=font(26), fill=REDD, anchor="lm")
    d.text((x0 + breedte, 244), "17 en 18", font=font(26), fill=REDD, anchor="rm")

    ys, yh = 276, 84
    for plek in range(1, PLEKKEN + 1):
        a = x0 + (plek - 1) * cel
        if plek <= 9:
            vul, tekst = GRIJS, MUTE
        elif plek <= 16:
            vul, tekst = TINT, REDD
        else:
            vul, tekst = RED, "#FFFFFF"
        d.rectangle((a + 1, ys, a + cel - 1, ys + yh), fill=vul)
        if plek in calls:
            rand = {"ref": MUTE, "jong": INK, "zeventien": INK}[calls[plek][0]]
            d.rectangle((a + 2, ys + 1, a + cel - 2, ys + yh - 1), outline=rand, width=6)
        d.text((a + cel / 2, ys + yh / 2), str(plek), font=font(34, plek in calls), fill=INK if plek in calls and plek <= 16 else tekst,
               anchor="mm")

    # callouts met pijlen
    n = len(calls)
    bw, gap = 330, 40
    start = x0 + (breedte - (n * bw + (n - 1) * gap)) / 2
    yb, bh = 470, 104
    for i, (plek, (soort, club, pt)) in enumerate(calls.items()):
        bx = start + i * (bw + gap)
        if soort == "jong":
            vul, rand, kleur_naam, kleur_sub = INK, INK, "#FFFFFF", "#E8DADC"
        elif soort == "ref":
            vul, rand, kleur_naam, kleur_sub = "#FFFFFF", INK, INK, MUTE
        else:
            vul, rand, kleur_naam, kleur_sub = "#FFFFFF", RED, RED, MUTE
        d.rounded_rectangle((bx, yb, bx + bw, yb + bh), radius=22, fill=vul, outline=rand, width=4)
        naam = kort(club)
        d.text((bx + bw / 2, yb + 38), naam, font=passend(d, naam, bw - 30, 36, bold=True), fill=kleur_naam, anchor="mm")
        sub = f"{plek}e plek \u00b7 {punten(pt)}"
        d.text((bx + bw / 2, yb + 78), sub, font=passend(d, sub, bw - 30, 28), fill=kleur_sub, anchor="mm")
        doel = (x0 + (plek - 0.5) * cel, ys + yh + 8)
        pijl(d, (bx + bw / 2, yb), doel, INK if soort != "zeventien" else RED)

    # uitleg
    yu = 620
    d.rounded_rectangle((x0, yu, x0 + 700, yu + 104), radius=22, fill=TINT)
    d.text((x0 + 30, yu + 34), "Plek 10 t/m 16", font=font(32, True), fill=REDD, anchor="lm")
    d.text((x0 + 30, yu + 76), "play-off over twee wedstrijden", font=font(30, True), fill=REDD, anchor="lm")
    d.rounded_rectangle((x0 + 740, yu, x0 + breedte, yu + 104), radius=22, fill=RED)
    d.text((x0 + 770, yu + 34), "Plek 17 of 18", font=font(32, True), fill="#FFFFFF", anchor="lm")
    d.text((x0 + 770, yu + 76), "algeheel kampioen promoveert automatisch", font=font(30, True), fill="#FFFFFF", anchor="lm")

    voet = (f"Stand Tweede Divisie na {ronde} wedstrijden, bron vi.nl, {today.day} {MONTHS[today.month - 1]} {today.year}. "
            f"Plek 9 is de laatste plek van het linkerrijtje.")
    d.text((x0, 790), voet, font=passend(d, voet, breedte, 24), fill=MUTE, anchor="lm")
    return img, status, calls, ronde


def teksten(data, status, calls, ronde):
    gap = status["gap"] if status else None
    verdict = oordeel(gap, vorige_gap(data, ronde))
    if verdict:
        woord, ontw = verdict
        eerder = vorige_gap(data, ronde)
        hoofd = (f"Het was een {woord} weekend! De afstand van het laagst geplaatste Jong-team tot het linkerrijtje is "
                 f"namelijk {ontw} (van {punten(max(eerder, 0))} naar {punten(max(gap, 0))}).")
    else:
        hoofd = "Zo staat het er in de Tweede Divisie voor."
    tweet = hoofd + "\n\n#Feyenoord #TweedeDivisie"
    delen = [f"{club} ({plek}e plek, {punten(pt)})" for plek, (_, club, pt) in calls.items()]
    alt = ("Plaatje met de plekken 1 t/m 18 van de Tweede Divisie en de plek en punten van "
           + ", ".join(delen) + ". ")
    return tweet, alt


def heeft_gespeeld(data, today):
    return any(recente_uitslag(data["td"]["matches"].get(n), today) for n in jong_namen())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data.json"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "zondag.png"))
    ap.add_argument("--vanaf", help="datum JJJJ-MM-DD (standaard vandaag)")
    ap.add_argument("--forceer", action="store_true", help="ook maken als er dit weekend niet gespeeld is (test)")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.vanaf) if a.vanaf else dt.date.today()
    data = json.loads(Path(a.data).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    status_pad = out.with_name("zondag.status")

    if not (a.forceer or heeft_gespeeld(data, today)):
        status_pad.write_text(f"{today.isoformat()} nee\n", encoding="utf-8")
        print("Geen Jong-team heeft dit weekend gespeeld: geen plaatje gemaakt (met --forceer wel).")
    else:
        img, status, calls, ronde = maak(data, today)
        tweet, alt = teksten(data, status, calls, ronde)
        img.save(out, optimize=True)
        out.with_name("zondag.txt").write_text(tweet, encoding="utf-8")
        out.with_name("zondag.alt.txt").write_text(alt, encoding="utf-8")
        status_pad.write_text(f"{today.isoformat()} ja\n", encoding="utf-8")
        print("Klaar:", out)
        print(tweet)
