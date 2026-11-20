#!/usr/bin/env python3
"""Zondag-plaatje (1600x960): stand van de Jong-teams ten opzichte van het linkerrijtje.

Leest data.json (door scrape.py ververst) en maakt, net als uitslagen.py met Pillow en de hulpjes uit plaatje.py:
  docs/zondag.png      het plaatje (het onderste deel van de promotie-infographic)
  docs/zondag.txt      de Bluesky-tekst
  docs/zondag.alt.txt  de alt-tekst voor het plaatje
  docs/zondag.status   "<datum> ja" of "<datum> nee": of er vandaag iets te plaatsen valt
  afstanden.json       de afstand per speelronde (naast data.json), om de volgende week mee te vergelijken

Gebruik:  python zondag.py
Testen:   python zondag.py --vandaag 2026-11-22 --forceer --uit /tmp/uit
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from plaatje import ROOT, W, INK, MUTE, LINE, RED, REDD, font

MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
           "augustus", "september", "oktober", "november", "december"]
AANTAL_PLEKKEN = 18      # Tweede Divisie
LAATSTE_LINKS = 9        # plek 1 t/m 9 = linkerrijtje
LAATSTE_PLAYOFF = 16     # plek 10 t/m 16 = play-off, 17 en 18 = automatisch
EERSTE_AUTOMATISCH = 17  # eerste plek met directe promotie
MAX_DAGEN_GELEDEN = 3    # laatste Jong-wedstrijd moet dit weekend zijn geweest
HOOGTE = 960             # iets hoger dan de andere plaatjes, voor de pijltjes naar de blokjes

ACHTERGROND, ROZE, GRIJS = "#FBF7F6", "#FDE3E5", "#F4EDED"


def punten(n):
    return f"{n} punt" if n == 1 else f"{n} punten"


def datum_nl(d):
    return f"{d.day} {MAANDEN[d.month - 1]} {d.year}"


# ---------------------------------------------------------------- data

def analyseer(data):
    td = data["td"]["table"]
    if len(td) != AANTAL_PLEKKEN:
        raise SystemExit(f"Verwacht {AANTAL_PLEKKEN} teams in de Tweede Divisie, gevonden: {len(td)}")
    jongnamen = list(data["td"]["matches"].keys())          # Jong Sparta, Jong Almere City
    per_pos = {r["pos"]: r for r in td}
    zeventiende = per_pos[EERSTE_AUTOMATISCH]
    jong = sorted((r for r in td if r["team"] in jongnamen), key=lambda r: r["pos"])
    laagste = jong[-1]                                      # laagst geplaatste Jong-team
    # Feyenoord heeft genoeg aan één Jong-team in het rechterrijtje. Dat gebeurt alleen niet als álle Jong-teams in
    # het linkerrijtje eindigen. Het laagste Jong-team moet dan boven de 8e club zonder Jong-team komen
    # (9 plekken min 2 Jong-teams = 7 plekken voor de rest). Staat een Jong-team in de top 8, dan is dat de nummer 9.
    zonder_jong = sorted((r for r in td if r["team"] not in jongnamen), key=lambda r: r["pos"])
    referentie = zonder_jong[LAATSTE_LINKS - len(jong)]
    laatste = [dt.date.fromisoformat(data["td"]["matches"][n]["last"]["date"])
               for n in jongnamen if data["td"]["matches"][n].get("last")]
    return {
        "referentie": referentie,
        "zeventiende": zeventiende,
        "jong": jong,
        "laagste": laagste,
        "gap": referentie["pt"] - laagste["pt"],
        "ronde": laagste["gs"],
        "laatste_datum": max(laatste) if laatste else None,
    }


def vorige_afstand(afstanden, ronde):
    eerder = [int(k) for k in afstanden if str(k).isdigit() and int(k) < ronde]
    return afstanden[str(max(eerder))]["afstand"] if eerder else None


def weekendtekst(gap, vorig_gap, laagste_pos):
    basis = "De afstand van het laagst geplaatste Jong-team tot het linkerrijtje"
    if vorig_gap is None:
        tekst = f"{basis} is nu {punten(gap)}."
    else:
        verschil = gap - vorig_gap
        if verschil > 0:        # verder van het linkerrijtje = goed voor Feyenoord
            oordeel, wat = "goed", f"toegenomen met {punten(verschil)}"
        elif verschil < 0:
            oordeel, wat = "slecht", f"afgenomen met {punten(-verschil)}"
        else:
            oordeel, wat = "neutraal", "hetzelfde gebleven"
        tekst = f"Het was een {oordeel} weekend! {basis} is namelijk {wat}."
    if laagste_pos <= LAATSTE_LINKS:
        tekst += " Let op: beide Jong-teams staan nu in het linkerrijtje."
    return tekst


def alttekst(a):
    delen = ["Plaatje met de stand van de Tweede Divisie, plek 1 tot en met 18. "]
    for r in a["jong"]:
        delen.append(f"{r['team']} staat {r['pos']}e met {punten(r['pt'])}. ")
    jongteams = [r["team"] for r in a["jong"]]
    ref = a["referentie"]
    delen.append(f"Referentie is {ref['team']} op plek {ref['pos']} met {punten(ref['pt'])}: beide Jong-teams moeten "
                 "in het linkerrijtje eindigen om Feyenoord O21 tegen te houden. ")
    if a["zeventiende"]["team"] not in jongteams:
        delen.append(f"Nummer 17 is {a['zeventiende']['team']} met {punten(a['zeventiende']['pt'])}. ")
    delen.append("Een Jong-team op plek 10 tot en met 16 betekent een play-off voor Feyenoord O21, "
                 "plek 17 of 18 betekent automatische promotie. ")
    return "".join(delen)


# ---------------------------------------------------------------- plaatje

def wrap(d, tekst, f, maxbreedte):
    regels, huidig = [], ""
    for woord in tekst.split():
        proef = f"{huidig} {woord}".strip()
        if not huidig or d.textlength(proef, font=f) <= maxbreedte:
            huidig = proef
        else:
            regels.append(huidig)
            huidig = woord
    if huidig:
        regels.append(huidig)
    return regels


def pijl(d, x1, y1, x2, y2, kleur, dikte=5, kop=24):
    d.line((x1, y1, x2, y2), fill=kleur, width=dikte)
    hoek = math.atan2(y2 - y1, x2 - x1)
    links = (x2 - kop * math.cos(hoek - 0.45), y2 - kop * math.sin(hoek - 0.45))
    rechts = (x2 - kop * math.cos(hoek + 0.45), y2 - kop * math.sin(hoek + 0.45))
    d.polygon([(x2, y2), links, rechts], fill=kleur)


def maak(a, vandaag):
    img = Image.new("RGB", (W, HOOGTE), ACHTERGROND)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, W - 40, HOOGTE - 40), radius=28, fill="#FFFFFF", outline=LINE, width=3)

    x0, breed = 96, W - 2 * 96
    d.text((x0, 100), "FEYENOORD O21 NAAR DE TWEEDE DIVISIE", font=font(24, True), fill=RED, anchor="lm")
    ftitel = font(50, True)
    titel = wrap(d, "Hoe staat het er in de Tweede Divisie voor?", ftitel, breed)
    for i, regel in enumerate(titel):                        # een regel komt iets lager, zodat het gelijk verdeeld blijft
        d.text((x0, 150 + (2 - len(titel)) * 29 + i * 58), regel, font=ftitel, fill=INK, anchor="lm")
    y_zin = 150 + (2 - len(titel)) * 29 + (len(titel) - 1) * 58 + 54
    d.text((x0, y_zin), "Eindigt een Jong-team op plek 10 of lager, dan kan Feyenoord O21 promoveren.",
           font=font(30), fill=MUTE, anchor="lm")

    # de balk met de plekken 1 t/m 18
    gat = 4
    cw = (breed - (AANTAL_PLEKKEN - 1) * gat) / AANTAL_PLEKKEN
    yb, hb = 330, 80
    jongposities = {r["pos"] for r in a["jong"]}
    referenties = {a["referentie"]["pos"]: MUTE, a["zeventiende"]["pos"]: "#FFFFFF"}   # ringkleur per referentieplek

    def celx(pos):
        return x0 + (pos - 1) * (cw + gat)

    flegenda = font(24, True)
    d.text((celx(1), 300), "Linkerrijtje: plek 1 t/m 9", font=flegenda, fill=MUTE, anchor="lm")
    d.text((celx(10), 300), "Rechterrijtje: 10 t/m 16", font=flegenda, fill=REDD, anchor="lm")
    d.text((celx(17), 300), "17 en 18", font=flegenda, fill=RED, anchor="lm")

    fcel = font(32)
    fcelb = font(32, True)
    for pos in range(1, AANTAL_PLEKKEN + 1):
        if pos <= LAATSTE_LINKS:
            bg, kleur = GRIJS, MUTE
        elif pos <= LAATSTE_PLAYOFF:
            bg, kleur = ROZE, REDD
        else:
            bg, kleur = RED, "#FFFFFF"
        x = celx(pos)
        vak = (round(x), yb, round(x + cw), yb + hb)
        if pos in (1, AANTAL_PLEKKEN):                       # afgeronde buitenhoeken
            d.rounded_rectangle(vak, radius=16, fill=bg)
            helft = (round(x + cw / 2), yb, round(x + cw), yb + hb) if pos == 1 else (round(x), yb, round(x + cw / 2), yb + hb)
            d.rectangle(helft, fill=bg)
        else:
            d.rectangle(vak, fill=bg)
        gemarkeerd = pos in jongposities or pos in referenties
        if pos in jongposities:
            d.rectangle((vak[0] + 3, yb + 3, vak[2] - 3, yb + hb - 3), outline=INK, width=6)
            kleur = INK if pos <= LAATSTE_PLAYOFF else "#FFFFFF"
        elif pos in referenties:
            d.rectangle((vak[0] + 3, yb + 3, vak[2] - 3, yb + hb - 3), outline=referenties[pos], width=6)
            kleur = INK if pos <= LAATSTE_PLAYOFF else "#FFFFFF"
        d.text((x + cw / 2, yb + hb / 2), str(pos), font=fcelb if gemarkeerd else fcel, fill=kleur, anchor="mm")

    # blokjes met pijltjes onder de balk
    items = [{"pos": r["pos"], "titel": r["team"], "sub": f"{r['pos']}e plek · {punten(r['pt'])}", "stijl": "jong"}
             for r in a["jong"]]
    for ref in (a["referentie"], a["zeventiende"]):         # referentieplek en nummer 17
        if ref["team"] not in [r["team"] for r in a["jong"]]:
            items.append({"pos": ref["pos"], "titel": ref["team"], "sub": f"{ref['pos']}e plek · {punten(ref['pt'])}", "stijl": "negen"})
    ft, fs = font(34, True), font(26)
    for it in items:
        it["mid"] = celx(it["pos"]) + cw / 2
        it["w"] = max(250, d.textlength(it["titel"], font=ft) + 48, d.textlength(it["sub"], font=fs) + 48)
    items.sort(key=lambda i: i["mid"])
    tussen, einde = 16, x0 - 16
    for it in items:
        it["x"] = max(it["mid"] - it["w"] / 2, einde + tussen)
        einde = it["x"] + it["w"]
    if einde > x0 + breed:                                   # te ver naar rechts: terugschuiven
        items[-1]["x"] -= einde - (x0 + breed)
        for i in range(len(items) - 2, -1, -1):
            items[i]["x"] = min(items[i]["x"], items[i + 1]["x"] - tussen - items[i]["w"])
    for it in items:
        it["x"] = max(it["x"], x0)
        ylab = 540
        anker = min(max(it["mid"], it["x"] + 30), it["x"] + it["w"] - 30)
        pijl(d, anker, ylab, it["mid"], yb + hb + 12, INK)
        box = (round(it["x"]), ylab, round(it["x"] + it["w"]), ylab + 104)
        if it["stijl"] == "jong":
            d.rounded_rectangle(box, radius=20, fill=INK)
            tkleur = "#FFFFFF"
        else:
            d.rounded_rectangle(box, radius=20, fill="#FFFFFF", outline=INK, width=4)
            tkleur = INK
        cx = (box[0] + box[2]) / 2
        d.text((cx, ylab + 36), it["titel"], font=ft, fill=tkleur, anchor="mm")
        d.text((cx, ylab + 76), it["sub"], font=fs, fill=tkleur, anchor="mm")

    # wat betekent het
    ybox, hbox, bw = 690, 110, (breed - 24) / 2
    fuitleg = font(30, True)
    for i, (bg, kleur, tekst) in enumerate([
            (ROZE, REDD, "Plek 10 t/m 16: play-off over twee wedstrijden"),
            (RED, "#FFFFFF", "Plek 17 of 18: algeheel kampioen promoveert automatisch")]):
        bx = x0 + i * (bw + 24)
        d.rounded_rectangle((round(bx), ybox, round(bx + bw), ybox + hbox), radius=20, fill=bg)
        regels = wrap(d, tekst, fuitleg, bw - 56)
        top = ybox + hbox / 2 - (len(regels) - 1) * 20
        for k, regel in enumerate(regels):
            d.text((bx + 28, top + k * 40), regel, font=fuitleg, fill=kleur, anchor="lm")

    ref = a["referentie"]
    voet = (f"Stand Tweede Divisie na {a['ronde']} wedstrijden, bron vi.nl, {datum_nl(vandaag)}. "
            f"Beide Jong-teams moeten in het linkerrijtje eindigen om Feyenoord O21 tegen te houden, "
            f"daarom telt de afstand tot de {ref['pos']}e plek ({ref['team']}).")
    fvoet = font(22)
    for i, regel in enumerate(wrap(d, voet, fvoet, breed)):
        d.text((x0, 840 + i * 30), regel, font=fvoet, fill=MUTE, anchor="lm")
    return img


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data.json"))
    ap.add_argument("--uit", default=str(ROOT / "docs"))
    ap.add_argument("--vandaag", help="JJJJ-MM-DD, alleen om te testen")
    ap.add_argument("--forceer", action="store_true", help="sla de controle 'is er dit weekend gespeeld' over")
    args = ap.parse_args()

    vandaag = dt.date.fromisoformat(args.vandaag) if args.vandaag else dt.datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    uit = Path(args.uit)
    uit.mkdir(parents=True, exist_ok=True)
    pad_data = Path(args.data)
    data = json.loads(pad_data.read_text(encoding="utf-8"))
    a = analyseer(data)

    dagen = (vandaag - a["laatste_datum"]).days if a["laatste_datum"] else 999
    if dagen > MAX_DAGEN_GELEDEN and not args.forceer:
        (uit / "zondag.status").write_text(f"{vandaag.isoformat()} nee\n", encoding="utf-8")
        print(f"Laatste Jong-wedstrijd was {dagen} dagen geleden: geen nieuw plaatje.")
        return

    pad_afst = pad_data.with_name("afstanden.json")         # eigen geschiedenis, los van data.json
    afstanden = json.loads(pad_afst.read_text(encoding="utf-8")) if pad_afst.exists() else {}
    tekst = weekendtekst(a["gap"], vorige_afstand(afstanden, a["ronde"]), a["laagste"]["pos"])

    img = maak(a, vandaag)
    img.save(uit / "zondag.png", optimize=True)
    (uit / "zondag.txt").write_text(tekst + "\n", encoding="utf-8")
    (uit / "zondag.alt.txt").write_text(alttekst(a) + "\n", encoding="utf-8")
    (uit / "zondag.status").write_text(f"{vandaag.isoformat()} ja\n", encoding="utf-8")

    ref = a["referentie"]
    afstanden[str(a["ronde"])] = {"afstand": a["gap"], "team": a["laagste"]["team"], "pos": a["laagste"]["pos"],
                                  "pt": a["laagste"]["pt"], "referentie": ref["team"], "ref_pos": ref["pos"],
                                  "ref_pt": ref["pt"], "datum": vandaag.isoformat()}
    pad_afst.write_text(json.dumps(afstanden, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    print(tekst)


if __name__ == "__main__":
    main()
