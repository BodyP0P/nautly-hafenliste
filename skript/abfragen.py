#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Overpass-Abfragen fuer die Hafenliste Europa.

Liest rezept/gebiete.json, schreibt je Gebiet den Abfragetext nach rezept/<id>.query.txt und holt,
wenn ein Zielordner genannt ist, die Antwort von overpass-api.de.

Regeln fuer den Abruf (Rücksicht auf den oeffentlichen Server):
  - nur https://overpass-api.de/api/interpreter
  - zwischen zwei Abfragen mindestens 60 s Pause
  - bei HTTP 429, 502, 503, 504 oder einer Laufzeit-Bemerkung von Overpass: Pause verdoppeln
    (120, 240, 480 s); nach vier Fehlversuchen fuer dasselbe Gebiet bricht das Skript laut ab
  - hoechstens --max-abfragen Abfragen je Zielordner, Wiederholungen und fruehere Aufrufe
    (abruf.json) eingerechnet
  - vor jeder Abfrage fragt das Skript /api/status, ob ein Platz frei ist. Ist der Server voll,
    wartet es (Blick alle 90 s, hoechstens 40 min oder --warten-max) und schickt keine Abfrage. Ein Blick auf
    /api/status zaehlt nicht als Abfrage.
  - User-Agent ohne Personen- oder Geraetebezug
  - `out center tags`, ohne `meta`: Die Antwort traegt keine Bearbeiter, Versionen oder Zeitstempel
    der Objekte.

Eine Antwort, die schon vollstaendig im Zielordner liegt, wird nicht noch einmal geholt.

Aufrufe:
  python3 -I skript/abfragen.py texte                 # nur rezept/<id>.query.txt schreiben
  python3 -I skript/abfragen.py holen <zielordner> [--max-abfragen 15] [--warten-max 2400]

Nur Standardbibliothek. Laeuft mit Python 3.9 und neuer.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SERVER = "https://overpass-api.de/api/interpreter"
STATUS = "https://overpass-api.de/api/status"
STATUS_WARTEN_MAX_S = 2400
STATUS_TAKT_S = 90
USER_AGENT = "Nautly-Hafenliste/1.0 (+https://nautly.ch)"
PAUSE_S = 60
RUECKZUG_S = (120, 240, 480)
FEHLVERSUCHE_MAX = 4
TIMEOUT_OVERPASS_S = 300
HIER = os.path.dirname(os.path.abspath(__file__))
REZEPT = os.path.join(os.path.dirname(HIER), "rezept")

# Was eine Klasse bekommen kann (hafenliste.klasse), und nichts sonst.
FILTER = (
    '["leisure"="marina"]',
    '["harbour"]["harbour"!="no"]',
    '["seamark:type"~"^(harbour|anchorage|anchor_berth)$"]',
)
VERBOTENE_SCHLUESSEL = ("user", "uid", "version", "timestamp", "changeset")


def lade_gebiete(pfad=None):
    with open(pfad or os.path.join(REZEPT, "gebiete.json"), encoding="utf-8") as f:
        return json.load(f)["gebiete"]


def abfragetext(g):
    box = "%s,%s,%s,%s" % (g["s"], g["w"], g["n"], g["o"])
    zeilen = ["[out:json][timeout:%d];" % TIMEOUT_OVERPASS_S, "("]
    zeilen += ["nwr%s(%s);" % (f, box) for f in FILTER]
    zeilen += [");", "out center tags;", ""]
    return "\n".join(zeilen)


def schreibe_texte(gebiete, ordner=REZEPT):
    for g in gebiete:
        with open(os.path.join(ordner, g["id"] + ".query.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(abfragetext(g))


def pruefe_antwort(roh):
    """None, wenn die Antwort vollstaendig und ohne Personenbezug ist; sonst der Grund."""
    try:
        d = json.loads(roh.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        return "kein JSON (%s)" % e
    if "remark" in d:
        return "Overpass-Bemerkung: %s" % d["remark"][:200]
    if not (d.get("osm3s") or {}).get("timestamp_osm_base"):
        return "ohne timestamp_osm_base"
    if "elements" not in d:
        return "ohne elements"
    for e in d["elements"]:
        for k in VERBOTENE_SCHLUESSEL:
            if k in e:
                return "Element %s/%s traegt '%s'" % (e.get("type"), e.get("id"), k)
    return None


def platz_frei():
    """(frei, text) nach /api/status."""
    req = urllib.request.Request(STATUS, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return False, "HTTP %d" % e.code
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)
    zeilen = [z for z in text.splitlines() if "slots available now" in z or "Slot available after" in z]
    frei = any(z.split()[0].isdigit() and int(z.split()[0]) > 0 for z in zeilen if "slots available now" in z)
    return frei, " | ".join(zeilen) or text[:120]


def warte_auf_platz():
    gewartet = 0
    while True:
        frei, text = platz_frei()
        print("status %s: %s" % (_jetzt(), text), flush=True)
        if frei:
            return True
        if gewartet >= STATUS_WARTEN_MAX_S:
            return False
        p = STATUS_TAKT_S
        time.sleep(p)
        gewartet += p


def _jetzt():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def holen(gebiete, ziel, max_abfragen):
    os.makedirs(ziel, exist_ok=True)
    protokoll_pfad = os.path.join(ziel, "abruf.json")
    protokoll = []
    if os.path.exists(protokoll_pfad):
        with open(protokoll_pfad, encoding="utf-8") as f:
            protokoll = json.load(f)
    anfragen = len(protokoll)
    letzte = None
    for g in gebiete:
        ant_pfad = os.path.join(ziel, g["id"] + ".json")
        text = abfragetext(g)
        with open(os.path.join(ziel, g["id"] + ".query.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        if os.path.exists(ant_pfad):
            with open(ant_pfad, "rb") as f:
                if pruefe_antwort(f.read()) is None:
                    print("%s vorhanden, uebersprungen" % g["id"], flush=True)
                    continue
        fehl = 0
        while True:
            if anfragen >= max_abfragen:
                print("ABBRUCH: Deckel von %d Abfragen erreicht, %s fehlt" % (max_abfragen, g["id"]), flush=True)
                return 3
            if letzte is not None:
                pause = PAUSE_S if fehl == 0 else RUECKZUG_S[min(fehl, len(RUECKZUG_S)) - 1]
                rest = pause - (time.time() - letzte)
                if rest > 0:
                    print("Pause %.0f s vor %s" % (rest, g["id"]), flush=True)
                    time.sleep(rest)
            if not warte_auf_platz():
                print("ABBRUCH: Server seit %d s ohne freien Platz, %s fehlt" % (STATUS_WARTEN_MAX_S, g["id"]), flush=True)
                return 4
            anfragen += 1
            start = _jetzt()
            t0 = time.time()
            daten = urllib.parse.urlencode({"data": text}).encode("utf-8")
            req = urllib.request.Request(SERVER, data=daten, headers={"User-Agent": USER_AGENT})
            status, roh, fehler = None, b"", None
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_OVERPASS_S + 60) as r:
                    status = r.status
                    roh = r.read()
            except urllib.error.HTTPError as e:
                status = e.code
                fehler = "HTTP %d" % e.code
            except Exception as e:  # Netz, Zeitueberschreitung
                fehler = "%s: %s" % (type(e).__name__, e)
            letzte = time.time()
            dauer = round(letzte - t0, 1)
            if fehler is None:
                fehler = pruefe_antwort(roh)
            eintrag = {"gebiet": g["id"], "anfrage": anfragen, "start": start, "dauer_s": dauer,
                       "http": status, "byte": len(roh), "fehler": fehler}
            if fehler is None:
                d = json.loads(roh.decode("utf-8"))
                eintrag["sha256"] = hashlib.sha256(roh).hexdigest()
                eintrag["timestamp_osm_base"] = d["osm3s"]["timestamp_osm_base"]
                eintrag["elemente"] = len(d["elements"])
                with open(ant_pfad + ".teil", "wb") as f:
                    f.write(roh)
                os.replace(ant_pfad + ".teil", ant_pfad)
            protokoll.append(eintrag)
            with open(protokoll_pfad, "w", encoding="utf-8") as f:
                json.dump(protokoll, f, ensure_ascii=False, indent=1)
            print(json.dumps(eintrag, ensure_ascii=False), flush=True)
            if fehler is None:
                break
            fehl += 1
            if fehl >= FEHLVERSUCHE_MAX:
                print("ABBRUCH: %d Fehlversuche fuer %s" % (fehl, g["id"]), flush=True)
                return 2
    print("fertig, %d Anfragen" % anfragen, flush=True)
    return 0


def main(argv):
    if len(argv) >= 1 and argv[0] == "texte":
        schreibe_texte(lade_gebiete())
        return 0
    if len(argv) >= 2 and argv[0] == "holen":
        max_abfragen = 15
        if "--max-abfragen" in argv:
            max_abfragen = int(argv[argv.index("--max-abfragen") + 1])
        if "--warten-max" in argv:
            global STATUS_WARTEN_MAX_S
            STATUS_WARTEN_MAX_S = int(argv[argv.index("--warten-max") + 1])
        return holen(lade_gebiete(), argv[1], max_abfragen)
    print(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
