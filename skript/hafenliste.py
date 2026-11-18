#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hafenliste Europa: Overpass-Antworten -> GeoJSON fuer die Karte der App Nautly.

Eingang:  ein Ordner mit je einer Overpass-Antwort <gebiet>.json fuer jedes Gebiet aus
          rezept/gebiete.json (geholt mit skript/abfragen.py).
Ausgang:  ein Ordner mit
            haefen-europa.geojson  die Hafenliste (FeatureCollection, Punkte)
            HERKUNFT.json          Lizenz, Pruefsummen, OSM-Stand je Antwort, Regel, Zahlen
            LIZENZ.txt             Lizenzhinweis DE/EN
            lauf-log.json          gelesen, weggefallen je Grund, geschrieben je Klasse, Dateigroesse
            paare-unter-1000m.tsv  benannte Paare unter 1000 m mit verschiedenem Namen (nur zum Ansehen)

Regeln (die Werte stehen als Konstanten unten):
  Klasse      seamark:type anchorage|anchor_berth -> anker; sonst leisure=marina,
              seamark:type=harbour oder harbour != no -> hafen; alles andere faellt weg.
  Name        `name`, nur wenn leer `seamark:name`; NFC, aussen getrimmt. Namen mit + oder ; und
              Namen ueber 255 Byte fallen weg. Ein Klammerzusatz faellt nur nach KLAMMER_WEG weg.
              Ein Name, der nur ein Gattungswort ist ("Marina", "Luka", "Småbåtshamn"), oder nur eine
              Liegeplatznummer (nur Ziffern, ein einzelner Buchstabe oder ein Liegeplatzcode aus einem
              Grossbuchstaben und ein oder zwei Ziffern wie "A1"), gilt als namenlos.
  Gebiete     Ein Eintrag bleibt nur, wenn er echt innerhalb eines Rechtecks liegt (nicht auf dem
              Rand), gemessen an der gerundeten Lage, die die App sieht. So zeigt die App genau
              die Eintraege, die ihr Filter `within` den Kartenkacheln wegnimmt.
  Dubletten   gleicher Name (casefold), Abstand unter 500 m: einer bleibt. Vorfahrt hafen vor
              anker, dann `name` vor `seamark:name`, dann Knoten vor Weg vor Relation, dann
              OSM-Nummer.
  Namenlose   bleiben nur, wenn unter 500 m kein benannter Eintrag liegt; untereinander unter
              300 m bleibt einer (Vorfahrt hafen vor anker, Knoten vor Weg vor Relation, Nummer).
  Merkmale    kind, name (fehlt bei namenlosen), osm, osm_sz (traegt seamark:type),
              sz_name (traegt seamark:name), platz (0 kein Seezeichen, 1 nur Zeichen,
              2 Zeichen und Name bis 12 Zeichen, 3 laengerer Name). Lage auf 5 Stellen.
  Ausgabe     deterministisch: Schluessel sortiert, Punkte nach OSM-Typ und Nummer, kompakt,
              UTF-8. Zwei Laeufe ueber dieselben Antworten ergeben dieselben Bytes.

Aufruf:
  python3 -I skript/hafenliste.py <ordner mit antworten> <zielordner>

Daten: (c) OpenStreetMap-Mitwirkende, ODbL 1.0. Nicht zur Navigation.
Nur Standardbibliothek. Laeuft mit Python 3.9 und neuer.
"""
import gzip
import hashlib
import json
import re
import math
import os
import sys
import unicodedata
import zlib

# ---------------------------------------------------------------------------------------------
# Werte
# ---------------------------------------------------------------------------------------------

ERDRADIUS_SM = 3440.065
METER_JE_SM = 1852.0

DUBLETTE_M = 500.0                    # gleicher Name, Abstand unter 500 m: einer bleibt
NAMENLOS_NAH_BENANNT_M = 500.0        # namenlos nur ohne benannten Eintrag unter 500 m
NAMENLOS_UNTEREINANDER_M = 300.0      # namenlos untereinander: unter 300 m bleibt einer
PAAR_LOG_M = 1000.0                   # Lauf-Log: Paare mit verschiedenem Namen unter 1000 m
NAME_MAX_BYTE = 255
PLATZ_KURZ_MAX_ZEICHEN = 12
STELLEN = 5

KLASSEN = ("hafen", "anker")
KLASSENRANG = {k: i for i, k in enumerate(KLASSEN)}
TYPRANG = {"node": 0, "way": 1, "relation": 2}

ANKER_TYPEN = ("anchorage", "anchor_berth")
NAME_VERBOTENE_ZEICHEN = ("+", ";")

KLAMMER_WEG = ("bodensee", "obersee", "untersee", "überlinger see", "zürichsee", "walensee",
               "vierwaldstättersee", "thunersee", "brienzersee", "bielersee", "neuenburgersee",
               "genfersee", "lac léman", "lac de neuchâtel", "lago maggiore", "lago di lugano",
               "luganersee", "gardasee", "lago di garda", "comer see", "lago di como", "chiemsee",
               "ammersee", "starnberger see", "tegernsee", "müritz", "attersee", "traunsee",
               "wolfgangsee", "mondsee", "neusiedler see", "ostsee", "nordsee", "mittelmeer", "adria",
               "recepcija", "reception", "rezeption", "réception")

GATTUNG_ALLEIN = ("marina", "hafen", "yachthafen", "jachthafen", "sportboothafen", "bootshafen",
                  "fischerhafen", "fischereihafen", "gemeindehafen", "stadthafen", "privathafen",
                  "gondelhafen", "schutzhafen", "anlegestelle", "bojenfeld", "steg", "luka", "lučica",
                  "porat", "mandrač", "port", "porto", "harbour", "havn", "hamn", "haven")
# Nautly-Ergaenzung zu R0 (Oscar 17.11.2026 nach Doras D-1): haeufige Gattungsnamen in den Daten
GATTUNG_ALLEIN_NAUTLY = ("småbåtshamn", "småbåtshavn", "gästhamn", "venesatama", "port de plaisance",
                         "capitainerie", "ausstiegsstelle")
# Nautly-Ergaenzung (Doras Sichtabnahme B3, 18.11.2026, Gruende R1, Entscheid Oscar 18.11.): Das Zeichen sagt es schon.
# Unterscheidende (R2: Alter Hafen, Porto Vecchio, Winterhafen) und warnende Namen (R3: Ölhafen, Kalasatama,
# Przystań kajakowa, Réservé) bleiben benannt; die Regel gilt nur fuer den ganzen Namen.
GATTUNG_ALLEIN_B3 = ("przystań", "passantenhaven", "liegestelle sport 24h", "vierasvenesatama", "pienvenesatama",
                     "лодочная станция", "ankerplads")
GATTUNG_ALLEIN = GATTUNG_ALLEIN + GATTUNG_ALLEIN_NAUTLY + GATTUNG_ALLEIN_B3

LIZENZ_KURZ = "ODbL-1.0 https://opendatacommons.org/licenses/odbl/1-0/"
ATTRIBUTION = "© OpenStreetMap contributors https://www.openstreetmap.org/copyright"
REPO = "https://github.com/BodyP0P/nautly-hafenliste"
LIZENZ_URI = "https://opendatacommons.org/licenses/odbl/1-0/"
REGEL = ("R0 mit Abweichung 1 (Ankerplaetze als eigene Klasse) und Abweichung 2 (Vereinshaefen "
         "bleiben); Namenlose nach Nautly D-1 (500 m zu benannten, 300 m untereinander); "
         "nur echt innerhalb der Gebiete")
DATEI = "haefen-europa.geojson"
PAARE_DATEI = "paare-unter-1000m.tsv"

GRUENDE = ("keine Klasse", "keine Lage", "verbotene Zeichen", "Name zu lang", "ausserhalb der Gebiete",
           "auf dem Rand der Gebiete", "Dublette", "namenlos nahe benanntem Eintrag",
           "namenlos nahe anderem namenlosen")

LIZENZ_TXT = """haefen-europa.geojson -- Hafendaten / harbour data
==================================================

DE
Diese Datei enthaelt Haefen, Marinas und Ankerplaetze an den Kuesten und
Seen Europas, abgeleitet aus OpenStreetMap. Die Daten wurden gefiltert, in
den Namen bereinigt und entdoppelt.

Sie ist damit eine abgeleitete Datenbank im Sinne der Open Database License
(ODbL) 1.0 und steht unter denselben Lizenzbedingungen.

  Lizenztext : https://opendatacommons.org/licenses/odbl/1-0/
  Quelle     : (c) OpenStreetMap-Mitwirkende
               https://www.openstreetmap.org/copyright
  Datei, Skript und Abfragen: https://github.com/BodyP0P/nautly-hafenliste

  OSM-Stand, Commit und Pruefsumme: siehe HERKUNFT.json in diesem Ordner

  Die Daten sind unvollstaendig und ungeprueft und werden ohne Gewaehr
  bereitgestellt. Nicht zur Navigation verwenden.

EN
This file contains harbours, marinas and anchorages on the coasts and
lakes of Europe, derived from OpenStreetMap. The data has been filtered,
cleaned up in the names and de-duplicated.

It is therefore a derivative database under the Open Database License
(ODbL) 1.0 and is made available under the same terms.

  Licence    : https://opendatacommons.org/licenses/odbl/1-0/
  Source     : (c) OpenStreetMap contributors
               https://www.openstreetmap.org/copyright
  File, script and queries: https://github.com/BodyP0P/nautly-hafenliste

  OSM snapshot, commit and checksum: see HERKUNFT.json in this folder

  The data is incomplete and unverified and is provided as is.
  Do not use for navigation.
"""

# ---------------------------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------------------------


def abstand_m(lat1, lon1, lat2, lon2):
    """Grosskreisabstand (Haversine) mit dem Erdradius der App, in Metern."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return ERDRADIUS_SM * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h)) * METER_JE_SM


class Raster(object):
    """Nachbarsuche: Wuerfel auf der Einheitskugel mit Kantenlaenge etwas ueber dem Suchabstand.
    Zwei Punkte unter dem Suchabstand liegen in benachbarten Wuerfeln. Entschieden wird jeder
    Kandidat mit abstand_m."""

    def __init__(self, abstand):
        self.kante = abstand / METER_JE_SM / ERDRADIUS_SM * 1.05
        self.abstand = abstand
        self.zellen = {}

    def _zelle(self, lat, lon):
        p, l = math.radians(lat), math.radians(lon)
        k = self.kante
        return (int(math.floor(math.cos(p) * math.cos(l) / k)),
                int(math.floor(math.cos(p) * math.sin(l) / k)),
                int(math.floor(math.sin(p) / k)))

    def dazu(self, schluessel, e):
        x, y, z = self._zelle(e["lat"], e["lon"])
        self.zellen.setdefault((schluessel, x, y, z), []).append(e)

    def naechster_unter(self, schluessel, lat, lon):
        """Ein Eintrag unter dem Suchabstand oder None."""
        x, y, z = self._zelle(lat, lon)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in self.zellen.get((schluessel, x + dx, y + dy, z + dz), ()):
                        if abstand_m(q["lat"], q["lon"], lat, lon) < self.abstand:
                            return q
        return None

    def alle_unter(self, schluessel, lat, lon):
        x, y, z = self._zelle(lat, lon)
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in self.zellen.get((schluessel, x + dx, y + dy, z + dz), ()):
                        d = abstand_m(q["lat"], q["lon"], lat, lon)
                        if d < self.abstand:
                            out.append((q, d))
        return out


def gerundet(x):
    r = round(x, STELLEN)
    return 0.0 if r == 0 else r


def gebiet_von(lat, lon, gebiete):
    """'innen', 'rand' oder 'aussen' fuer die gerundete Lage."""
    rand = False
    for g in gebiete:
        if g["s"] < lat < g["n"] and g["w"] < lon < g["o"]:
            return "innen"
        if g["s"] <= lat <= g["n"] and g["w"] <= lon <= g["o"]:
            rand = True
    return "rand" if rand else "aussen"

# ---------------------------------------------------------------------------------------------
# Je Objekt
# ---------------------------------------------------------------------------------------------


def klasse(tags):
    st = tags.get("seamark:type", "")
    if st in ANKER_TYPEN:
        return "anker"
    if tags.get("leisure") == "marina" or st == "harbour" or ("harbour" in tags and tags["harbour"] != "no"):
        return "hafen"
    return None


def _sauber(s):
    if s is None:
        return ""
    return unicodedata.normalize("NFC", s).strip()


def rohname(tags):
    """(name, quelle): `name`, nur wenn leer `seamark:name`; sonst (None, None)."""
    for schluessel in ("name", "seamark:name"):
        n = _sauber(tags.get(schluessel))
        if n:
            return n, schluessel
    return None, None


def klammer_weg(name):
    if name.endswith(")") and "(" in name:
        i = name.rfind("(")
        innen = name[i + 1:-1].strip().casefold()
        aussen = name[:i].rstrip()
        if aussen and innen in KLAMMER_WEG:
            return aussen
    return name


LIEGEPLATZCODE = re.compile(r"^[A-Z][0-9]{1,2}$")  # Doras R4, Oscar 17.11. (3) und 18.11.: "A1" bis "C3"


def ist_liegeplatznummer(name):
    """Nur Ziffern 0-9, ein einzelner Buchstabe ("12", "A") oder ein Liegeplatzcode ("A1", "C12")."""
    return (name.isascii() and name.isdigit()) or (len(name) == 1 and name.isalpha()) or bool(LIEGEPLATZCODE.match(name))


def platz(osm_sz, sz_name_text, hat_name):
    if not osm_sz:
        return 0
    if not sz_name_text or not hat_name:
        return 1
    return 2 if len(sz_name_text) <= PLATZ_KURZ_MAX_ZEICHEN else 3


def pruefe(typ, oid, tags, lage):
    """Ein OSM-Objekt -> (eintrag, None) oder (None, grund). lage = (lat, lon) oder None.
    eintrag["name"] ist None bei namenlosen; eintrag["namenlos_grund"] sagt dann warum."""
    kl = klasse(tags)
    if kl is None:
        return None, "keine Klasse"
    if lage is None:
        return None, "keine Lage"
    n, quelle = rohname(tags)
    namenlos_grund = None
    if n is None:
        namenlos_grund = "ohne Namen"
    else:
        if any(z in n for z in NAME_VERBOTENE_ZEICHEN):
            return None, "verbotene Zeichen"
        n = klammer_weg(n)
        if not n.strip():
            namenlos_grund = "ohne Namen"
        elif n.casefold() in GATTUNG_ALLEIN:
            namenlos_grund = "nur Gattungswort"
        elif ist_liegeplatznummer(n):
            namenlos_grund = "nur Liegeplatznummer"
        elif len(n.encode("utf-8")) > NAME_MAX_BYTE:
            return None, "Name zu lang"
    if namenlos_grund is not None:
        n, quelle = None, None
    sz_text = _sauber(tags.get("seamark:name"))
    osm_sz = "seamark:type" in tags
    return {
        "kind": kl, "name": n, "quelle": quelle, "namenlos_grund": namenlos_grund,
        "typ": typ, "oid": oid, "lat": lage[0], "lon": lage[1],
        "osm_sz": osm_sz, "sz_name": bool(sz_text), "platz": platz(osm_sz, sz_text, n is not None),
    }, None


def osm_id(e):
    return "%s/%d" % (e["typ"], e["oid"])

# ---------------------------------------------------------------------------------------------
# Menge
# ---------------------------------------------------------------------------------------------


def neues_log():
    return {
        "objekte_gelesen": 0,
        "doppelt_im_eingang": 0,
        "keine_klasse": 0,
        "klassen": {k: {"gelesen": 0, "weg": {g: 0 for g in GRUENDE if g != "keine Klasse"},
                        "als_namenlos": {"ohne Namen": 0, "nur Gattungswort": 0, "nur Liegeplatznummer": 0},
                        "geschrieben": 0, "geschrieben_benannt": 0, "geschrieben_namenlos": 0}
                    for k in KLASSEN},
    }


def _rang_benannt(e):
    return (KLASSENRANG[e["kind"]], 0 if e["quelle"] == "name" else 1, TYPRANG[e["typ"]], e["oid"])


def _rang_namenlos(e):
    return (KLASSENRANG[e["kind"]], TYPRANG[e["typ"]], e["oid"])


def erzeuge(objekte, gebiete, log=None):
    """objekte: Folge von (typ, oid, tags, lage). Rueckgabe (eintraege, log, paare).
    eintraege sortiert nach OSM-Typ und Nummer."""
    if log is None:
        log = neues_log()
    kl_log = log["klassen"]
    gesehen = set()
    kandidaten = []
    for typ, oid, tags, lage in objekte:
        if (typ, oid) in gesehen:
            log["doppelt_im_eingang"] += 1
            continue
        gesehen.add((typ, oid))
        log["objekte_gelesen"] += 1
        e, grund = pruefe(typ, oid, tags, lage)
        if grund == "keine Klasse":
            log["keine_klasse"] += 1
            continue
        kl = e["kind"] if e is not None else klasse(tags)
        kl_log[kl]["gelesen"] += 1
        if e is None:
            kl_log[kl]["weg"][grund] += 1
            continue
        lage_app = gebiet_von(gerundet(e["lat"]), gerundet(e["lon"]), gebiete)
        if lage_app != "innen":
            kl_log[kl]["weg"]["auf dem Rand der Gebiete" if lage_app == "rand" else "ausserhalb der Gebiete"] += 1
            continue
        if e["namenlos_grund"]:
            kl_log[kl]["als_namenlos"][e["namenlos_grund"]] += 1
        kandidaten.append(e)

    # Benannte: R0-Dublette
    benannte = sorted((e for e in kandidaten if e["name"] is not None), key=_rang_benannt)
    raster = Raster(DUBLETTE_M)
    behalten = []
    for e in benannte:
        nk = e["name"].casefold()
        if raster.naechster_unter(nk, e["lat"], e["lon"]) is not None:
            kl_log[e["kind"]]["weg"]["Dublette"] += 1
            continue
        raster.dazu(nk, e)
        behalten.append(e)

    # Namenlose: erst gegen alle behaltenen Benannten, dann untereinander
    nah = Raster(NAMENLOS_NAH_BENANNT_M)
    for e in behalten:
        nah.dazu(None, e)
    unter = Raster(NAMENLOS_UNTEREINANDER_M)
    for e in sorted((e for e in kandidaten if e["name"] is None), key=_rang_namenlos):
        if nah.naechster_unter(None, e["lat"], e["lon"]) is not None:
            kl_log[e["kind"]]["weg"]["namenlos nahe benanntem Eintrag"] += 1
            continue
        if unter.naechster_unter(None, e["lat"], e["lon"]) is not None:
            kl_log[e["kind"]]["weg"]["namenlos nahe anderem namenlosen"] += 1
            continue
        unter.dazu(None, e)
        behalten.append(e)

    behalten.sort(key=lambda e: (TYPRANG[e["typ"]], e["oid"]))
    for e in behalten:
        kl_log[e["kind"]]["geschrieben"] += 1
        kl_log[e["kind"]]["geschrieben_benannt" if e["name"] is not None else "geschrieben_namenlos"] += 1

    # Lauf-Log: benannte Paare unter 1000 m mit verschiedenem Namen (D-3), nur zum Ansehen
    paar_raster = Raster(PAAR_LOG_M)
    paare = []
    for e in behalten:
        if e["name"] is None:
            continue
        for q, d in paar_raster.alle_unter(None, e["lat"], e["lon"]):
            if q["name"].casefold() != e["name"].casefold():
                a, b = sorted((q, e), key=lambda x: (TYPRANG[x["typ"]], x["oid"]))
                paare.append([osm_id(a), a["name"], osm_id(b), b["name"], int(round(d))])
        paar_raster.dazu(None, e)
    paare.sort(key=lambda p: (p[4], p[0], p[2]))
    return behalten, log, paare


def geht_auf(log):
    """Je Klasse: gelesen = weggefallen + geschrieben."""
    return {k: v["gelesen"] == sum(v["weg"].values()) + v["geschrieben"] for k, v in log["klassen"].items()}

# ---------------------------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------------------------


def als_feature(e):
    props = {"kind": e["kind"], "osm": osm_id(e), "osm_sz": e["osm_sz"], "platz": e["platz"],
             "sz_name": e["sz_name"]}
    if e["name"] is not None:
        props["name"] = e["name"]
    return {"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [gerundet(e["lon"]), gerundet(e["lat"])]},
            "properties": props}


def geojson_bytes(eintraege):
    fc = {"type": "FeatureCollection", "license": LIZENZ_KURZ, "attribution": ATTRIBUTION, "source": REPO,
          "features": [als_feature(e) for e in eintraege]}
    return json.dumps(fc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def paare_tsv(paare):
    """Tabulator-getrennt, eine Zeile je Paar; Tabulatoren und Zeilenumbrueche in Namen werden Leerzeichen."""
    def feld(x):
        return str(x).replace("\t", " ").replace("\n", " ").replace("\r", " ")
    zeilen = ["meter\tosm_a\tname_a\tosm_b\tname_b"]
    zeilen += ["\t".join(feld(x) for x in (p[4], p[0], p[1], p[2], p[3])) for p in paare]
    return ("\n".join(zeilen) + "\n").encode("utf-8")


def lies_antwort(pfad):
    with open(pfad, "rb") as f:
        roh = f.read()
    d = json.loads(roh.decode("utf-8"))
    if "remark" in d:
        raise ValueError("%s: Overpass-Bemerkung %r" % (os.path.basename(pfad), d["remark"][:200]))
    return roh, d


def objekte_aus(antworten):
    for _, d in antworten:
        for el in d["elements"]:
            if "lat" in el and "lon" in el:
                lage = (el["lat"], el["lon"])
            elif "center" in el:
                lage = (el["center"]["lat"], el["center"]["lon"])
            else:
                lage = None
            yield el["type"], el["id"], el.get("tags", {}), lage


def sha256_datei(pfad):
    with open(pfad, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def baue(rohordner, ziel, gebiete_pfad=None):
    hier = os.path.dirname(os.path.abspath(__file__))
    gebiete_pfad = gebiete_pfad or os.path.join(os.path.dirname(hier), "rezept", "gebiete.json")
    with open(gebiete_pfad, encoding="utf-8") as f:
        gebiete = json.load(f)["gebiete"]
    antworten, eingaenge = [], []
    for g in gebiete:
        pfad = os.path.join(rohordner, g["id"] + ".json")
        roh, d = lies_antwort(pfad)
        antworten.append((roh, d))
        eingaenge.append({"gebiet": g["id"], "datei": g["id"] + ".json", "byte": len(roh),
                          "sha256": hashlib.sha256(roh).hexdigest(),
                          "timestamp_osm_base": d["osm3s"]["timestamp_osm_base"],
                          "elemente": len(d["elements"])})
    eintraege, log, paare = erzeuge(objekte_aus(antworten), gebiete)
    b = geojson_bytes(eintraege)
    auf = geht_auf(log)
    if not all(auf.values()):
        raise RuntimeError("Lauf-Log geht nicht auf: %r" % auf)

    sha = hashlib.sha256(b).hexdigest()
    datei = {"datei": DATEI, "byte": len(b), "sha256": sha,
             "byte_gzip9": len(gzip.compress(b, 9, mtime=0)), "byte_deflate6": len(zlib.compress(b, 6))}
    je_klasse = {k: log["klassen"][k]["geschrieben"] for k in KLASSEN}
    namen = {}
    for e in eintraege:
        if e["name"] is not None:
            namen.setdefault(e["kind"], {}).setdefault(e["name"], 0)
            namen[e["kind"]][e["name"]] += 1
    haeufig = {k: sorted(v.items(), key=lambda kv: (-kv[1], kv[0]))[:15] for k, v in sorted(namen.items())}
    lauf_log = {
        "regel": REGEL,
        "eingaenge": eingaenge,
        "objekte_gelesen": log["objekte_gelesen"],
        "doppelt_im_eingang": log["doppelt_im_eingang"],
        "keine_klasse": log["keine_klasse"],
        "klassen": log["klassen"],
        "geht_auf": auf,
        "geschrieben": len(eintraege),
        "datei": datei,
        "haeufigste_namen": haeufig,
        "paare_unter_1000m_verschiedener_name": {"anzahl": len(paare), "datei": PAARE_DATEI},
        "python_unicode": unicodedata.unidata_version,
    }
    skript_sha = {n: sha256_datei(os.path.join(hier, n)) for n in ("abfragen.py", "hafenliste.py")}
    herkunft = {
        "datei": DATEI,
        "byte": len(b),
        "sha256": sha,
        "lizenz": "OpenStreetMap, (c) OpenStreetMap-Mitwirkende, ODbL 1.0",
        "lizenzUri": LIZENZ_URI,
        "repo": REPO,
        "repoCommit": None,
        "repoCommitHinweis": "Wird beim Uebernehmen in die App gesetzt; im Repo zeigt der Commit dieser Datei den Stand.",
        "quelle": {"server": "https://overpass-api.de/api/interpreter", "abfragen": "rezept/<gebiet>.query.txt",
                   "antworten": eingaenge},
        "osmStand": max(e["timestamp_osm_base"] for e in eingaenge),
        "rezept": {"skript": "skript/hafenliste.py", "abfrage": "skript/abfragen.py", "gebiete": "rezept/gebiete.json",
                   "sha256": dict(skript_sha, **{"gebiete.json": sha256_datei(gebiete_pfad)})},
        "regel": REGEL,
        "punkteJeKlasse": je_klasse,
        "punkteBenanntNamenlos": {k: {"benannt": log["klassen"][k]["geschrieben_benannt"],
                                      "namenlos": log["klassen"][k]["geschrieben_namenlos"]} for k in KLASSEN},
        "unicode": unicodedata.unidata_version,
    }

    os.makedirs(ziel, exist_ok=True)
    ausgaben = (
        (DATEI, b),
        ("HERKUNFT.json", (json.dumps(herkunft, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")),
        ("LIZENZ.txt", LIZENZ_TXT.encode("utf-8")),
        ("lauf-log.json", (json.dumps(lauf_log, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")),
        (PAARE_DATEI, paare_tsv(paare)),
    )
    for name, inhalt in ausgaben:
        teil = os.path.join(ziel, name + ".teil")
        with open(teil, "wb") as f:
            f.write(inhalt)
        os.replace(teil, os.path.join(ziel, name))
    return lauf_log


def zusammenfassung(lauf_log):
    z = ["gelesen %d (doppelt im Eingang %d, ohne Klasse %d)" % (
        lauf_log["objekte_gelesen"], lauf_log["doppelt_im_eingang"], lauf_log["keine_klasse"])]
    for k in KLASSEN:
        v = lauf_log["klassen"][k]
        z.append("%s: gelesen %d" % (k, v["gelesen"]))
        for g, n in v["weg"].items():
            z.append("  weg %-34s %6d" % (g, n))
        for g, n in v["als_namenlos"].items():
            z.append("  als namenlos gefuehrt (%s) %6d" % (g, n))
        z.append("  geschrieben %d (benannt %d, namenlos %d)" % (
            v["geschrieben"], v["geschrieben_benannt"], v["geschrieben_namenlos"]))
    z.append("geht auf: %r" % lauf_log["geht_auf"])
    d = lauf_log["datei"]
    z.append("geschrieben gesamt %d" % lauf_log["geschrieben"])
    z.append("datei %s roh %d B, gzip9 %d B, deflate6 %d B, sha256 %s" % (
        d["datei"], d["byte"], d["byte_gzip9"], d["byte_deflate6"], d["sha256"]))
    z.append("paare unter 1000 m mit verschiedenem Namen: %d" % lauf_log["paare_unter_1000m_verschiedener_name"]["anzahl"])
    return "\n".join(z)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 64
    lauf_log = baue(argv[0], argv[1])
    print(zusammenfassung(lauf_log))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
