#!/usr/bin/env python3
"""Plaatst docs/programma.png met de tekst uit docs/tweet.txt op Bluesky.

Vereist twee omgevingsvariabelen (in GitHub: repository secrets):
  BLUESKY_HANDLE        bijvoorbeeld jouwnaam.bsky.social
  BLUESKY_APP_PASSWORD  een app-wachtwoord (niet je gewone wachtwoord)

Gebruik:  python bluesky.py            -> plaatsen
          python bluesky.py --droog    -> alleen tonen wat er geplaatst zou worden
"""
import argparse
import datetime as dt
import io
import os
import re
import sys
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).parent
PDS = os.environ.get("BLUESKY_PDS", "https://bsky.social").rstrip("/")
MAX_BLOB = 950_000  # Bluesky accepteert afbeeldingen tot ongeveer 1 MB
MAX_TEKENS = 300


def afbeelding(pad):
    """Geeft (bytes, mime). PNG als die klein genoeg is, anders een JPEG die wel past."""
    raw = Path(pad).read_bytes()
    if len(raw) <= MAX_BLOB:
        return raw, "image/png"
    img = Image.open(pad).convert("RGB")
    for q in (92, 88, 84, 80, 75, 70):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True)
        if buf.tell() <= MAX_BLOB:
            return buf.getvalue(), "image/jpeg"
    sys.exit("De afbeelding past ook als JPEG niet binnen de limiet van Bluesky.")


def hashtag_facets(tekst):
    """Maakt hashtags klikbaar (Bluesky rekent met byte-posities in UTF-8)."""
    out = []
    for m in re.finditer(r"(?<!\w)#(\w+)", tekst):
        out.append({"index": {"byteStart": len(tekst[:m.start()].encode()), "byteEnd": len(tekst[:m.end()].encode())},
                    "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}]})
    return out


def alt_tekst(tekst):
    regels = [r for r in tekst.splitlines() if r.strip() and not r.startswith("#") and not r.endswith(":")]
    return "Plaatje met het programma van Feyenoord O21 en de Jong-teams, met de plaats van beide teams in de competitie. " + "; ".join(regels)


def hoofdtekst(pad):
    tekst = Path(pad).read_text(encoding="utf-8").strip()
    if len(tekst) > MAX_TEKENS:
        tekst = tekst[:MAX_TEKENS - 1].rstrip() + "\u2026"
    return tekst


def al_geplaatst(auth, did, tekst):
    """Voorkomt dubbel plaatsen bij een tweede run: is dezelfde tekst de afgelopen 20 uur al geplaatst?"""
    try:
        r = requests.get(f"{PDS}/xrpc/app.bsky.feed.getAuthorFeed", params={"actor": did, "limit": 10},
                         headers=auth, timeout=30)
        r.raise_for_status()
        nu = dt.datetime.now(dt.timezone.utc)
        for item in r.json().get("feed", []):
            rec = item["post"]["record"]
            if rec.get("text") == tekst:
                ts = dt.datetime.fromisoformat(rec["createdAt"].replace("Z", "+00:00"))
                if nu - ts < dt.timedelta(hours=20):
                    return True
    except Exception as e:  # de controle is een extraatje: bij een fout gewoon doorgaan
        print("Kon niet controleren of er al geplaatst is:", e)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plaatje", default=str(ROOT / "docs" / "programma.png"))
    ap.add_argument("--tekst", default=str(ROOT / "docs" / "tweet.txt"))
    ap.add_argument("--droog", action="store_true", help="niets plaatsen, alleen tonen")
    a = ap.parse_args()

    tekst = hoofdtekst(a.tekst)
    data, mime = afbeelding(a.plaatje)
    alt = alt_tekst(tekst)
    if a.droog:
        print(f"--- tekst ({len(tekst)} tekens) ---\n{tekst}\n--- alt-tekst ---\n{alt}\n--- afbeelding: {len(data)} bytes, {mime}")
        print("--- hashtags:", [f["features"][0]["tag"] for f in hashtag_facets(tekst)])
        return

    handle, ww = os.environ.get("BLUESKY_HANDLE"), os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not ww:
        sys.exit("BLUESKY_HANDLE en BLUESKY_APP_PASSWORD ontbreken (maak ze aan als repository secrets).")

    r = requests.post(f"{PDS}/xrpc/com.atproto.server.createSession",
                      json={"identifier": handle, "password": ww}, timeout=30)
    r.raise_for_status()
    s = r.json()
    auth = {"Authorization": f"Bearer {s['accessJwt']}"}

    if al_geplaatst(auth, s["did"], tekst):
        print("Dit plaatje is al geplaatst, overslaan.")
        return

    r = requests.post(f"{PDS}/xrpc/com.atproto.repo.uploadBlob", data=data,
                      headers={**auth, "Content-Type": mime}, timeout=60)
    r.raise_for_status()
    blob = r.json()["blob"]

    img = Image.open(io.BytesIO(data))
    record = {"$type": "app.bsky.feed.post", "text": tekst, "langs": ["nl"],
              "createdAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
              "facets": hashtag_facets(tekst),
              "embed": {"$type": "app.bsky.embed.images",
                        "images": [{"alt": alt, "image": blob, "aspectRatio": {"width": img.width, "height": img.height}}]}}
    r = requests.post(f"{PDS}/xrpc/com.atproto.repo.createRecord",
                      json={"repo": s["did"], "collection": "app.bsky.feed.post", "record": record},
                      headers=auth, timeout=30)
    r.raise_for_status()
    print("Geplaatst:", r.json().get("uri"))


if __name__ == "__main__":
    main()
