#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hafenliste Europa als Vektorkacheln (PMTiles): zweiter Schritt nach skript/hafenliste.py.

Eingang:  der Datenordner von hafenliste.py (haefen-europa.geojson, HERKUNFT.json).
Ausgang:  im selben Ordner
            haefen-europa.pmtiles  dieselben Punkte als Vektorkacheln, Ebene "haefen", Zoom 0 bis 10
            HERKUNFT.json          ergaenzt um den Block "pmtiles" (Datei, Byte, sha256, Werkzeug, Befehl)
            LIZENZ.txt             Lizenzhinweis DE/EN fuer beide Dateien

Werkzeug: tippecanoe (https://github.com/felt/tippecanoe), aufgerufen mit BEFEHL unten. Kein Ausduennen: jede
Zoomstufe traegt alle Punkte (-r1, keine Feature- und Groessengrenze). Raster -d14, bei Zoom 10 rund 2.4 m.
Ueber Zoom 10 vergroessert die Karte die Kacheln von Zoom 10. Das Merkmal `osm` faellt weg, die Karte liest es nicht.

Wiederholbar ist der Inhalt, nicht jedes Byte: tippecanoe ordnet die Merkmale innerhalb einer Kachel je Lauf
anders. Darum liegt die Kacheldatei selbst im Repo, und HERKUNFT.json nennt ihre sha256.

Aufruf: python3 -I skript/kacheln.py <datenordner>
"""
import hashlib
import json
import os
import subprocess
import sys

DATEI_GEOJSON = "haefen-europa.geojson"
DATEI_PMTILES = "haefen-europa.pmtiles"
EBENE = "haefen"
MERKMALE = ("kind", "name", "osm_sz", "sz_name", "platz")
ATTRIBUTION = "© OpenStreetMap contributors"
NAME = "Hafenliste Europa (Nautly)"
# Lizenz und Quelle in der Kacheldatei selbst (Metadaten "description"), wie license/attribution/source in der GeoJSON.
BESCHREIBUNG = "ODbL-1.0 https://opendatacommons.org/licenses/odbl/1-0/ · https://github.com/BodyP0P/nautly-hafenliste"

LIZENZ_TXT = """haefen-europa.geojson, haefen-europa.pmtiles -- Hafendaten / harbour data
========================================================================

DE
Diese Dateien enthalten Haefen, Marinas und Ankerplaetze an den Kuesten und
Seen Europas, abgeleitet aus OpenStreetMap. Die Daten wurden gefiltert, in
den Namen bereinigt und entdoppelt. haefen-europa.pmtiles enthaelt dieselben
Punkte als Vektorkacheln (PMTiles), so wie die App Nautly sie zeichnet.

Sie sind damit eine abgeleitete Datenbank im Sinne der Open Database License
(ODbL) 1.0 und stehen unter denselben Lizenzbedingungen.

  Lizenztext : https://opendatacommons.org/licenses/odbl/1-0/
  Quelle     : (c) OpenStreetMap-Mitwirkende
               https://www.openstreetmap.org/copyright
  Dateien, Skript und Abfragen: https://github.com/BodyP0P/nautly-hafenliste

  OSM-Stand, Commit und Pruefsummen: siehe HERKUNFT.json in diesem Ordner

  Die Daten sind unvollstaendig und ungeprueft und werden ohne Gewaehr
  bereitgestellt. Nicht zur Navigation verwenden.

EN
These files contain harbours, marinas and anchorages on the coasts and
lakes of Europe, derived from OpenStreetMap. The data has been filtered,
cleaned up in the names and de-duplicated. haefen-europa.pmtiles holds the
same points as vector tiles (PMTiles), as drawn by the Nautly app.

They are therefore a derivative database under the Open Database License
(ODbL) 1.0 and are made available under the same terms.

  Licence    : https://opendatacommons.org/licenses/odbl/1-0/
  Source     : (c) OpenStreetMap contributors
               https://www.openstreetmap.org/copyright
  Files, script and queries: https://github.com/BodyP0P/nautly-hafenliste

  OSM snapshot, commit and checksums: see HERKUNFT.json in this folder

  The data is incomplete and unverified and is provided as is.
  Do not use for navigation.
"""


def befehl(quelle, ziel):
    """Der tippecanoe-Aufruf, als Liste (ohne Shell)."""
    b = ["tippecanoe", "-q", "--force", "-o", ziel, "-l", EBENE, "-Z0", "-z10", "-d14", "-r1",
         "--no-feature-limit", "--no-tile-size-limit"]
    for m in MERKMALE:
        b += ["-y", m]
    return b + ["--attribution", ATTRIBUTION, "-n", NAME, "-N", BESCHREIBUNG, quelle]


def werkzeug_version():
    r = subprocess.run(["tippecanoe", "--version"], capture_output=True, text=True, check=True)
    return (r.stdout + r.stderr).strip()


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def ergaenze_herkunft(herkunft, pmtiles, version, skript_sha):
    """HERKUNFT um den Block "pmtiles" ergaenzen; alles andere bleibt, wie hafenliste.py es schrieb."""
    neu = dict(herkunft)
    neu["pmtiles"] = {
        "datei": DATEI_PMTILES,
        "byte": len(pmtiles),
        "sha256": sha256(pmtiles),
        "ausDatei": DATEI_GEOJSON,
        "ausSha256": herkunft["sha256"],
        "ebene": EBENE,
        "zoom": [0, 10],
        "merkmale": list(MERKMALE),
        "werkzeug": version,
        "befehl": " ".join(befehl(DATEI_GEOJSON, DATEI_PMTILES)),
        "skript": "skript/kacheln.py",
        "skriptSha256": skript_sha,
    }
    return neu


def herkunft_bytes(herkunft):
    return (json.dumps(herkunft, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def baue(ordner):
    quelle = os.path.join(ordner, DATEI_GEOJSON)
    with open(quelle, "rb") as f:
        geojson = f.read()
    with open(os.path.join(ordner, "HERKUNFT.json"), encoding="utf-8") as f:
        herkunft = json.load(f)
    if sha256(geojson) != herkunft["sha256"]:
        raise RuntimeError("haefen-europa.geojson passt nicht zu HERKUNFT.json")
    # tippecanoe waehlt das Ausgabeformat nach der Endung: Der Zwischenname muss auf .pmtiles enden.
    teil = os.path.join(ordner, "teil-" + DATEI_PMTILES)
    subprocess.run(befehl(quelle, teil), check=True)
    with open(teil, "rb") as f:
        pmtiles = f.read()
    with open(os.path.abspath(__file__), "rb") as f:
        skript_sha = sha256(f.read())
    neu = ergaenze_herkunft(herkunft, pmtiles, werkzeug_version(), skript_sha)
    os.replace(teil, os.path.join(ordner, DATEI_PMTILES))
    for name, inhalt in (("HERKUNFT.json", herkunft_bytes(neu)), ("LIZENZ.txt", LIZENZ_TXT.encode("utf-8"))):
        t = os.path.join(ordner, name + ".teil")
        with open(t, "wb") as f:
            f.write(inhalt)
        os.replace(t, os.path.join(ordner, name))
    return neu["pmtiles"]


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 64
    p = baue(argv[0])
    print("%s %d B, sha256 %s, %s" % (p["datei"], p["byte"], p["sha256"], p["werkzeug"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
