#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Feuer Europa: Geofabrik-Auszuege -> Lage und Laengenklasse der Feuerkennungen fuer die Karte der App Nautly.

Wozu: Mit eingeblendeten Seezeichen schreibt OpenSeaMap neben jedes Feuer seine Kennung ("Fl(2)R.4s2M"). Die App legt
an diese Stellen unsichtbare Platzhalter, damit ihre eigene Schrift die Kennung nicht ueberdeckt. Dafuer braucht sie
nur die Lage und wie lang die Kennung etwa ist. Die Kennung selbst steht nicht in der Datei.

Eingang:  ein oder mehrere OSM-Auszuege von Geofabrik (https://download.geofabrik.de/, *.osm.pbf), zusammen deckend fuer
          die Gebiete aus rezept/gebiete.json. Neben jedem Auszug darf die Pruefsumme von Geofabrik liegen
          (<auszug>.md5); sie wird in HERKUNFT-feuer.json uebernommen.
Werkzeug: osmium (https://osmcode.org/osmium-tool/) fuer Filter und Export, tippecanoe fuer die Kacheln. Kein Netz:
          Das Skript fragt keinen Server an, auch keinen Overpass-Server.
Ausgang:  im Zielordner
            feuer-europa.geojson   Punkte mit genau einem Merkmal "klasse" (1 kurz, 2 lang), Lage auf 5 Stellen
            feuer-europa.pmtiles   dieselben Punkte als Vektorkacheln, Ebene "feuer", nur Zoom 10
            HERKUNFT-feuer.json    Auszuege (Datei, Byte, md5, OSM-Stand), Befehle, Pruefsummen, Zahlen je Gebiet
            feuer-lauf-log.json    gelesen, weggefallen je Grund, geschrieben je Klasse und Gebiet
            LIZENZ.txt             Lizenzhinweis DE/EN fuer Hafen- und Feuerdaten (derselbe Text wie skript/kacheln.py)
          Zwischendateien (gefilterte Auszuege, Export) liegen im Arbeitsordner, nicht im Repo.

Regeln:
  Auswahl     Objekte mit dem Merkmal `seamark:light:character` oder einem nummerierten `seamark:light:<n>:character`
              (Sektorenfeuer; Oscars Nachtrag zum Kriterium B4, 21.11.2026, F-B4-2), je nicht leer. Das Lauf-Log
              zaehlt die nur nummerierten getrennt, damit die Zahl mit und ohne sie feststeht.
  Gebiete     wie skript/hafenliste.py: echt innerhalb eines Rechtecks aus rezept/gebiete.json (nicht auf dem Rand),
              gemessen an der gerundeten Lage.
  Lage        Knoten: seine Koordinate. Weg und Flaeche: Mitte des umschliessenden Rechtecks der Geometrie.
  Doppelt     dasselbe OSM-Objekt aus zwei Auszuegen (Grenzgebiete) zaehlt einmal.
  Kennung     so zusammengesetzt, wie OpenSeaMap sie ab Google-Zoom 15 neben das Feuer schreibt (Renderer "seachart",
              Datei render/Signals.java, Methode lights()): ein einzelnes Licht "Fl(2)R.4s2M", Sektorenfeuer je Gruppe
              eine Zeile "Fl.WRG.4s10m9-6M". Gemessen wird die laengste Zeile, in Zeichen.
  Klasse      1 (kurz) bis KURZ_BIS Zeichen, 2 (lang) darueber.
  Ausgabe     deterministisch: Punkte nach OSM-Typ und Nummer, Schluessel sortiert, kompakt, UTF-8.

Aufruf:
  python3 -I skript/feuer.py <arbeitsordner> <zielordner> <auszug.osm.pbf> [<auszug.osm.pbf> ...]

Daten: (c) OpenStreetMap-Mitwirkende, ODbL 1.0. Nicht zur Navigation.
Nur Standardbibliothek. Laeuft mit Python 3.9 und neuer.
"""
import decimal
import hashlib
import json
import math
import os
import subprocess
import sys

# ---------------------------------------------------------------------------------------------
# Werte
# ---------------------------------------------------------------------------------------------

KURZ_BIS = 10                         # Doras Startwerte B4: kurz bis 10 Zeichen, lang darueber
KLASSE_KURZ = 1
KLASSE_LANG = 2
STELLEN = 5                           # Lage auf 5 Stellen wie die Hafenliste
MERKMAL = "seamark:light:character"
FILTER = "nwr/seamark:light:*"        # breit, damit das Lauf-Log auch die nur nummerierten Lichter zaehlt

DATEI = "feuer-europa.geojson"
DATEI_PMTILES = "feuer-europa.pmtiles"
DATEI_HERKUNFT = "HERKUNFT-feuer.json"
DATEI_LOG = "feuer-lauf-log.json"
EBENE = "feuer"
ZOOM = 10                             # nur Zoom 10; die App zeigt die Ebene ab MapLibre 14 und vergroessert Zoom 10
REPO = "https://github.com/BodyP0P/nautly-hafenliste"
ATTRIBUTION = "© OpenStreetMap contributors"
NAME = "Feuer Europa (Nautly)"
LIZENZ_KURZ = "ODbL-1.0 https://opendatacommons.org/licenses/odbl/1-0/"
LIZENZ_URI = "https://opendatacommons.org/licenses/odbl/1-0/"
BESCHREIBUNG = "ODbL-1.0 https://opendatacommons.org/licenses/odbl/1-0/ · https://github.com/BodyP0P/nautly-hafenliste"
GEOFABRIK = "https://download.geofabrik.de/"

# Derselbe Text wie skript/kacheln.py (LIZENZ_TXT); ein Test haelt beide gleich.
LIZENZ_TXT = """haefen-europa.geojson, haefen-europa.pmtiles -- Hafendaten / harbour data
feuer-europa.geojson, feuer-europa.pmtiles   -- Feuerdaten / light data
========================================================================

DE
haefen-europa.* enthalten Haefen, Marinas und Ankerplaetze an den Kuesten und
Seen Europas, abgeleitet aus OpenStreetMap. Die Daten wurden gefiltert, in
den Namen bereinigt und entdoppelt. haefen-europa.pmtiles enthaelt dieselben
Punkte als Vektorkacheln (PMTiles), so wie die App Nautly sie zeichnet.

feuer-europa.* enthalten die Lage der Leuchtfeuer mit Kennung in denselben
Gebieten, abgeleitet aus OpenStreetMap, je Feuer nur die Lage und ob die
Kennung kurz oder lang ist. feuer-europa.pmtiles enthaelt dieselben Punkte
als Vektorkacheln (PMTiles).

Sie sind damit eine abgeleitete Datenbank im Sinne der Open Database License
(ODbL) 1.0 und stehen unter denselben Lizenzbedingungen.

  Lizenztext : https://opendatacommons.org/licenses/odbl/1-0/
  Quelle     : (c) OpenStreetMap-Mitwirkende
               https://www.openstreetmap.org/copyright
  Dateien, Skript und Abfragen: https://github.com/BodyP0P/nautly-hafenliste

  OSM-Stand, Commit und Pruefsummen: siehe HERKUNFT.json und
  HERKUNFT-feuer.json in diesem Ordner

  Die Daten sind unvollstaendig und ungeprueft und werden ohne Gewaehr
  bereitgestellt. Nicht zur Navigation verwenden.

EN
haefen-europa.* contain harbours, marinas and anchorages on the coasts and
lakes of Europe, derived from OpenStreetMap. The data has been filtered,
cleaned up in the names and de-duplicated. haefen-europa.pmtiles holds the
same points as vector tiles (PMTiles), as drawn by the Nautly app.

feuer-europa.* contain the position of lights with a characteristic in the
same areas, derived from OpenStreetMap, for each light only its position and
whether the characteristic is short or long. feuer-europa.pmtiles holds the
same points as vector tiles (PMTiles).

They are therefore a derivative database under the Open Database License
(ODbL) 1.0 and are made available under the same terms.

  Licence    : https://opendatacommons.org/licenses/odbl/1-0/
  Source     : (c) OpenStreetMap contributors
               https://www.openstreetmap.org/copyright
  Files, script and queries: https://github.com/BodyP0P/nautly-hafenliste

  OSM snapshot, commit and checksums: see HERKUNFT.json and
  HERKUNFT-feuer.json in this folder

  The data is incomplete and unverified and is provided as is.
  Do not use for navigation.
"""

# ---------------------------------------------------------------------------------------------
# Kennung wie OpenSeaMap (seachart, render/Signals.java, lights())
# ---------------------------------------------------------------------------------------------

# Werte von seamark:light:character, die seachart kennt, und wie es sie schreibt (S57val Litchr, Signals LightCharacters).
ZEICHEN = ("F", "Fl", "LFl", "Q", "VQ", "UQ", "Iso", "Oc", "IQ", "IVQ", "IUQ", "Mo", "FFl", "FlLFl", "OcFl", "FLFl",
           "Al.Oc", "Al.LFl", "Al.Fl", "Al.Gr", "Q+LFl", "VQ+LFl", "UQ+LFl", "Al", "Al.FFl")
# Sektorenfeuer: seachart fasst die Wechselfeuer unter dem Grundzeichen zusammen.
ZEICHEN_SEKTOR = {"Al": "F", "Al.Oc": "Oc", "Al.LFl": "LFl", "Al.Fl": "Fl", "Al.FFl": "FFl"}
# Farben, fuer die seachart einen Buchstaben hat (Signals LightLetters).
FARBE = {"white": "W", "red": "R", "green": "G", "blue": "Bu", "yellow": "Y", "amber": "Am", "violet": "Vi",
         "orange": "Or"}
# Java haengt fuer einen fehlenden Eintrag "null" an (String + null). seachart schreibt das so in die Karte.
JAVA_NULL = "null"


def zahl(text):
    """Merkmalswert als Zahl wie seachart (Double), sonst None (fehlt, leer, keine endliche Zahl)."""
    if text is None:
        return None
    try:
        x = float(str(text).strip())
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def df(x):
    """Java DecimalFormat("#.#"): eine Nachkommastelle, kaufmaennisch zur geraden Ziffer (HALF_EVEN), ohne ".0"."""
    d = decimal.Decimal(x).quantize(decimal.Decimal("0.1"), rounding=decimal.ROUND_HALF_EVEN)
    s = format(d, "f")
    if s.endswith(".0"):
        s = s[:-2]
    if s in ("-0",):
        s = "0"
    return s


def lichter(tags):
    """Die Lichter eines Objekts: {0: {...}} fuer `seamark:light:<merkmal>`, {n: {...}} fuer `seamark:light:<n>:<merkmal>`."""
    out = {}
    for k, v in tags.items():
        if not k.startswith("seamark:light:"):
            continue
        rest = k[len("seamark:light:"):].split(":")
        if len(rest) == 1:
            out.setdefault(0, {})[rest[0]] = v
        elif len(rest) == 2 and rest[0].isdigit():
            out.setdefault(int(rest[0]), {})[rest[1]] = v
    return out


def _liste(v):
    return [x.strip() for x in v.split(";")] if v else []


def _buchstabe(farbe):
    return FARBE.get(farbe, JAVA_NULL)


def kennung_einzeln(l):
    """Ein einzelnes Licht (seachart, Zweig ohne Licht Nummer 1), etwa "Fl(2)R.4s2M" oder "Fl(3)10s14m15M"."""
    kat = _liste(l.get("category"))
    s = "Dir" if "directional" in kat else ""
    s += l.get("multiple", "")
    chr_ = l.get("character")
    if chr_:
        name = chr_ if chr_ in ZEICHEN else JAVA_NULL
        grp = l.get("group")
        if grp is not None:
            if chr_ in ("Q+LFl", "VQ+LFl", "UQ+LFl"):
                s += "%s(%s)+LFl" % (chr_.split("+")[0], grp)
            else:
                s += "%s(%s)" % (name, grp)
        else:
            s += name
    farben = _liste(l.get("colour"))
    if farben and not (len(farben) == 1 and farben[0] == "white"):
        if s and not s.endswith(")"):
            s += "."
        s += "".join(_buchstabe(f) for f in farben)
    s += "(vert)" if "vertical" in kat else ""
    s += "(hor)" if "horizontal" in kat else ""
    per, hgt, rng, mxr = (zahl(l.get(k)) for k in ("period", "height", "range", "maximum_range"))
    if s and (per is not None or hgt is not None or mxr is not None) and not s.endswith(")"):
        s += "."
    s += df(per) + "s" if per is not None else ""
    s += df(hgt) + "m" if hgt is not None else ""
    s += df(rng) + "M" if rng is not None else ""
    s += "(Front)" if "front" in kat else ""
    s += "(Rear)" if "rear" in kat else ""
    s += "(Upper)" if "upper" in kat else ""
    s += "(Lower)" if "lower" in kat else ""
    return s


def kennung_sektoren(alle):
    """Sektorenfeuer (seachart, Zweig mit Licht Nummer 1, ab Google-Zoom 15): je Gruppe gleicher Art eine Zeile."""
    sekt = []
    for n in sorted(alle):
        l = alle[n]
        chr_ = l.get("character")
        if chr_ not in ZEICHEN:
            continue                    # seachart: CHR_UNKN faellt weg
        farben = _liste(l.get("colour"))
        sekt.append({
            "dir": "directional" in _liste(l.get("category")),
            "chr": ZEICHEN_SEKTOR.get(chr_, chr_),
            "grp": l.get("group") or "",
            "per": zahl(l.get("period")) or 0.0,
            "rng": zahl(l.get("range")) or 0.0,
            "hgt": zahl(l.get("height")) or 0.0,
            "col": farben[0] if farben else None,
        })
    gruppen = []
    for s in sekt:
        for g in gruppen:
            m = g[0]
            if (s["dir"], s["chr"], s["grp"], s["per"], s["hgt"]) == (m["dir"], m["chr"], m["grp"], m["per"], m["hgt"]):
                g.append(s)
                break
        else:
            gruppen.append([s])
    gruppen.sort(key=lambda g: -len(g))           # stabil wie seachart: groessere Gruppe zuerst
    zeilen = []
    for g in gruppen:
        farbweite = []
        for s in g:
            for fw in farbweite:
                if fw[0] == s["col"]:
                    fw[1] = max(fw[1], s["rng"])
                    break
            else:
                farbweite.append([s["col"], s["rng"]])
        farbweite.sort(key=lambda fw: -fw[1])     # stabil: groesste Tragweite zuerst
        m = g[0]
        z = ("Dir" if m["dir"] else "") + m["chr"]
        z += "(%s)" % m["grp"] if m["grp"] else "."
        z += "".join(_buchstabe(fw[0]) for fw in farbweite)
        r0 = farbweite[0][1]
        if m["per"] > 0 or m["hgt"] > 0 or r0 > 0:
            z += "."
        if m["per"] > 0:
            z += df(m["per"]) + "s"
        if m["hgt"] > 0:
            z += df(m["hgt"]) + "m"
        if r0 > 0:
            z += df(r0)
            if len(farbweite) == 2:
                z += "/" + df(farbweite[1][1])
            elif len(farbweite) > 2:
                z += "-" + df(farbweite[-1][1])
            z += "M"
        zeilen.append(z)
    return zeilen


def kennung(tags):
    """Die Zeilen, die OpenSeaMap neben das Feuer schreibt (eine bei einem einzelnen Licht).

    seachart nimmt den Sektorenzweig, wenn es ein Licht Nummer 1 gibt. Faengt die Nummerierung erst spaeter an, gilt hier
    trotzdem der Sektorenzweig: Sonst entstuende aus dem leeren Licht 0 eine leere Kennung (technischer Entscheid Kai)."""
    alle = lichter(tags)
    if any(n >= 1 for n in alle):
        return kennung_sektoren(alle)
    return [kennung_einzeln(alle.get(0, {}))]


def klasse(zeilen):
    """1 (kurz), wenn die laengste Zeile hoechstens KURZ_BIS Zeichen hat, sonst 2 (lang)."""
    laenge = max((len(z) for z in zeilen), default=0)
    return KLASSE_KURZ if laenge <= KURZ_BIS else KLASSE_LANG

# ---------------------------------------------------------------------------------------------
# Lage und Gebiete
# ---------------------------------------------------------------------------------------------


def gerundet(x):
    r = round(x, STELLEN)
    return 0.0 if r == 0 else r


def osm_kennung(fid):
    """osmium export -u type_id: n<id>, w<id>, r<id>; Flaeche a<2*Weg> oder a<2*Relation+1>."""
    t, n = fid[0], int(fid[1:])
    if t == "n":
        return "node", n
    if t == "w":
        return "way", n
    if t == "r":
        return "relation", n
    if t == "a":
        return ("way", n // 2) if n % 2 == 0 else ("relation", (n - 1) // 2)
    raise ValueError("unbekannte Kennung %r" % fid)


def lage(geometrie):
    """Knoten: (lat, lon). Sonst Mitte des umschliessenden Rechtecks aller Koordinaten. Ohne Koordinaten None."""
    if not geometrie:
        return None
    c = geometrie.get("coordinates")
    if geometrie.get("type") == "Point":
        return c[1], c[0]
    lo_min = la_min = float("inf")
    lo_max = la_max = float("-inf")
    stapel = [c]
    while stapel:
        x = stapel.pop()
        if not x:
            continue
        if isinstance(x[0], (int, float)):
            lo_min, lo_max = min(lo_min, x[0]), max(lo_max, x[0])
            la_min, la_max = min(la_min, x[1]), max(la_max, x[1])
        else:
            stapel.extend(x)
    if lo_min == float("inf"):
        return None
    return (la_min + la_max) / 2, (lo_min + lo_max) / 2


def gebiete_von(lat, lon, gebiete):
    """Die Gebiete, in denen die Lage echt innen liegt (wie hafenliste.py: der Rand zaehlt nicht)."""
    return [g["id"] for g in gebiete if g["s"] < lat < g["n"] and g["w"] < lon < g["o"]]

# ---------------------------------------------------------------------------------------------
# Erzeugen
# ---------------------------------------------------------------------------------------------

RANG = {"node": 0, "way": 1, "relation": 2}


# Pruefnamen (Doras Prueforte B4): Treffer stehen im Lauf-Log mit OSM-Objekt, Schluesselart und Klasse.
PRUEFNAMEN = ("Ostri Rat",)


def nummerierte_kennung(tags):
    """True, wenn das Objekt eine nicht leere nummerierte Kennung traegt (`seamark:light:<n>:character`)."""
    for k, v in tags.items():
        rest = k[len("seamark:light:"):].split(":") if k.startswith("seamark:light:") else []
        if len(rest) == 2 and rest[0].isdigit() and rest[1] == "character" and (v or "").strip():
            return True
    return False


def neues_log(gebiete):
    return {"zeilen": 0, "ohne_kennung_im_export": 0, "doppelt_im_eingang": 0, "ohne_merkmal": 0,
            "ohne_lage": 0, "ausserhalb": 0, "auf_dem_rand": 0, "geschrieben": 0,
            "geschrieben_mit_merkmal": 0, "geschrieben_nur_nummeriert": 0,
            "je_klasse": {"kurz": 0, "lang": 0}, "je_gebiet": {g["id"]: 0 for g in gebiete},
            "je_gebiet_nur_nummeriert": {g["id"]: 0 for g in gebiete},
            "sektorenfeuer": 0, "laengen": {}, "pruefnamen": []}


def erzeuge(features, gebiete, log=None):
    """features: (fid, tags, geometrie) aus dem Export. Ergebnis: Punkte [{typ, id, lat, lon, klasse}] und das Log."""
    log = log if log is not None else neues_log(gebiete)
    gesehen = set()
    punkte = []
    for fid, tags, geom in features:
        log["zeilen"] += 1
        try:
            typ, oid = osm_kennung(fid)
        except (ValueError, TypeError, IndexError):
            log["ohne_kennung_im_export"] += 1
            continue
        if (typ, oid) in gesehen:
            log["doppelt_im_eingang"] += 1
            continue
        gesehen.add((typ, oid))
        mit_merkmal = bool((tags.get(MERKMAL) or "").strip())
        if not mit_merkmal and not nummerierte_kennung(tags):
            log["ohne_merkmal"] += 1
            continue
        l = lage(geom)
        if l is None:
            log["ohne_lage"] += 1
            continue
        lat, lon = gerundet(l[0]), gerundet(l[1])
        drin = gebiete_von(lat, lon, gebiete)
        if not drin:
            rand = any(g["s"] <= lat <= g["n"] and g["w"] <= lon <= g["o"] for g in gebiete)
            log["auf_dem_rand" if rand else "ausserhalb"] += 1
            continue
        zeilen = kennung(tags)
        k = klasse(zeilen)
        if len(zeilen) > 1 or 1 in lichter(tags):
            log["sektorenfeuer"] += 1
        laenge = str(max((len(z) for z in zeilen), default=0))
        log["laengen"][laenge] = log["laengen"].get(laenge, 0) + 1
        log["je_klasse"]["kurz" if k == KLASSE_KURZ else "lang"] += 1
        for g in drin:
            log["je_gebiet"][g] += 1
            if not mit_merkmal:
                log["je_gebiet_nur_nummeriert"][g] += 1
        log["geschrieben_mit_merkmal" if mit_merkmal else "geschrieben_nur_nummeriert"] += 1
        name = tags.get("seamark:name") or tags.get("name") or ""
        if any(n in name for n in PRUEFNAMEN):
            log["pruefnamen"].append({"osm": "%s/%d" % (typ, oid), "name": name, "klasse": k, "zeilen": zeilen,
                                      "schluessel": "seamark:light:character" if mit_merkmal else "nur nummeriert"})
        punkte.append({"typ": typ, "id": oid, "lat": lat, "lon": lon, "klasse": k})
    punkte.sort(key=lambda p: (RANG[p["typ"]], p["id"]))
    log["geschrieben"] = len(punkte)
    log["laengen"] = dict(sorted(log["laengen"].items(), key=lambda kv: int(kv[0])))
    return punkte, log


def geht_auf(log):
    """Jede gelesene Zeile ist genau einmal verbucht."""
    weg = sum(log[k] for k in ("ohne_kennung_im_export", "doppelt_im_eingang", "ohne_merkmal", "ohne_lage",
                               "ausserhalb", "auf_dem_rand"))
    return {"zeilen": weg + log["geschrieben"] == log["zeilen"],
            "klassen": sum(log["je_klasse"].values()) == log["geschrieben"],
            "schluessel": log["geschrieben_mit_merkmal"] + log["geschrieben_nur_nummeriert"] == log["geschrieben"]}


def geojson_bytes(punkte):
    fc = {"type": "FeatureCollection", "license": LIZENZ_KURZ, "attribution": ATTRIBUTION, "source": REPO,
          "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
                        "properties": {"klasse": p["klasse"]}} for p in punkte]}
    return json.dumps(fc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

# ---------------------------------------------------------------------------------------------
# Werkzeuge (osmium, tippecanoe)
# ---------------------------------------------------------------------------------------------


def basisname(auszug):
    n = os.path.basename(auszug)
    return n[:-len(".osm.pbf")] if n.endswith(".osm.pbf") else n


def befehl_filter(auszug, ziel):
    """osmium tags-filter: alle Objekte mit einem Merkmal seamark:light:*, Tags der nur mitgenommenen Knoten weg (-t)."""
    return ["osmium", "tags-filter", auszug, FILTER, "-t", "--overwrite", "-o", ziel]


def befehl_export(quelle, ziel):
    """osmium export als GeoJSON-Folge, eine Zeile je Objekt, Kennung n/w/r/a<id>."""
    return ["osmium", "export", quelle, "-f", "geojsonseq", "-u", "type_id", "--overwrite", "-o", ziel]


def befehl_stand(auszug):
    """OSM-Stand des Auszugs aus dem Dateikopf (Geofabrik setzt osmosis_replication_timestamp)."""
    return ["osmium", "fileinfo", "-g", "header.option.osmosis_replication_timestamp", auszug]


def befehl_kacheln(quelle, ziel):
    return ["tippecanoe", "-q", "--force", "-o", ziel, "-l", EBENE, "-Z%d" % ZOOM, "-z%d" % ZOOM, "-d14", "-r1",
            "--no-feature-limit", "--no-tile-size-limit", "-y", "klasse",
            "--attribution", ATTRIBUTION, "-n", NAME, "-N", BESCHREIBUNG, quelle]


def lies_export(pfad, log):
    """Eine Datei aus `osmium export -f geojsonseq`: je Zeile ein Objekt (mit oder ohne Satztrenner RS)."""
    with open(pfad, "rb") as f:
        for roh in f:
            roh = roh.strip(b"\x1e \t\r\n")
            if not roh:
                continue
            ft = json.loads(roh.decode("utf-8"))
            fid = ft.get("id")
            if not isinstance(fid, str) or len(fid) < 2:
                log["zeilen"] += 1
                log["ohne_kennung_im_export"] += 1
                continue
            yield fid, ft.get("properties") or {}, ft.get("geometry")


def sha256_datei(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def werkzeug_version(name):
    r = subprocess.run([name, "--version"], capture_output=True, text=True, check=True)
    return (r.stdout + r.stderr).strip().splitlines()[0]


def md5_neben(auszug):
    p = auszug + ".md5"
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read().split()[0]


def schreibe(ziel, name, inhalt):
    teil = os.path.join(ziel, name + ".teil")
    with open(teil, "wb") as f:
        f.write(inhalt)
    os.replace(teil, os.path.join(ziel, name))


def baue(arbeit, ziel, auszuege, gebiete_pfad=None):
    hier = os.path.dirname(os.path.abspath(__file__))
    gebiete_pfad = gebiete_pfad or os.path.join(os.path.dirname(hier), "rezept", "gebiete.json")
    with open(gebiete_pfad, encoding="utf-8") as f:
        gebiete = json.load(f)["gebiete"]
    os.makedirs(arbeit, exist_ok=True)
    os.makedirs(ziel, exist_ok=True)
    eingaenge, exporte = [], []
    for a in auszuege:
        b = basisname(a)
        stand = subprocess.run(befehl_stand(a), capture_output=True, text=True, check=True).stdout.strip()
        if not stand:
            raise RuntimeError("%s: kein OSM-Stand im Dateikopf" % os.path.basename(a))
        gefiltert = os.path.join(arbeit, b + ".feuer.osm.pbf")
        export = os.path.join(arbeit, b + ".feuer.geojsonseq")
        subprocess.run(befehl_filter(a, gefiltert), check=True)
        subprocess.run(befehl_export(gefiltert, export), check=True)
        exporte.append(export)
        eingaenge.append({"datei": os.path.basename(a), "byte": os.path.getsize(a), "md5Geofabrik": md5_neben(a),
                          "osmStand": stand, "export": {"datei": os.path.basename(export),
                                                        "byte": os.path.getsize(export),
                                                        "sha256": sha256_datei(export)}})
    log = neues_log(gebiete)

    def alle():
        for e in exporte:
            yield from lies_export(e, log)

    punkte, log = erzeuge(alle(), gebiete, log)
    auf = geht_auf(log)
    if not all(auf.values()):
        raise RuntimeError("Lauf-Log geht nicht auf: %r" % auf)
    gj = geojson_bytes(punkte)
    schreibe(ziel, DATEI, gj)
    teil = os.path.join(ziel, "teil-" + DATEI_PMTILES)      # tippecanoe waehlt das Format nach der Endung
    subprocess.run(befehl_kacheln(os.path.join(ziel, DATEI), teil), check=True)
    os.replace(teil, os.path.join(ziel, DATEI_PMTILES))
    pm = os.path.join(ziel, DATEI_PMTILES)
    herkunft = {
        "datei": DATEI,
        "byte": len(gj),
        "sha256": hashlib.sha256(gj).hexdigest(),
        "lizenz": "OpenStreetMap, (c) OpenStreetMap-Mitwirkende, ODbL 1.0",
        "lizenzUri": LIZENZ_URI,
        "repo": REPO,
        "repoCommit": None,
        "repoCommitHinweis": "Wird beim Uebernehmen in die App gesetzt; im Repo zeigt der Commit dieser Datei den Stand.",
        "quelle": {"geofabrik": GEOFABRIK, "auszuege": eingaenge, "filter": FILTER, "merkmal": MERKMAL,
                   "auchNummeriert": "seamark:light:<n>:character",
                   "werkzeug": werkzeug_version("osmium")},
        "osmStand": min(e["osmStand"] for e in eingaenge),
        "osmStandHinweis": "der aelteste Stand ueber alle Auszuege",
        "rezept": {"skript": "skript/feuer.py", "gebiete": "rezept/gebiete.json",
                   "sha256": {"feuer.py": sha256_datei(os.path.abspath(__file__)),
                              "gebiete.json": sha256_datei(gebiete_pfad)},
                   "befehle": [" ".join(befehl_stand("<auszug>")), " ".join(befehl_filter("<auszug>", "<gefiltert>")),
                               " ".join(befehl_export("<gefiltert>", "<export>"))]},
        "regel": {"klasse": {"1": "kurz, Kennung bis %d Zeichen" % KURZ_BIS, "2": "lang, ueber %d Zeichen" % KURZ_BIS},
                  "kennung": "wie OpenSeaMap (seachart render/Signals.java lights()), laengste Zeile"},
        "punkte": len(punkte),
        "punkteJeKlasse": log["je_klasse"],
        "punkteJeGebiet": log["je_gebiet"],
        "punkteMitMerkmal": log["geschrieben_mit_merkmal"],
        "punkteNurNummeriert": log["geschrieben_nur_nummeriert"],
        "pmtiles": {"datei": DATEI_PMTILES, "byte": os.path.getsize(pm), "sha256": sha256_datei(pm),
                    "ausDatei": DATEI, "ausSha256": hashlib.sha256(gj).hexdigest(), "ebene": EBENE,
                    "zoom": [ZOOM, ZOOM], "merkmale": ["klasse"], "werkzeug": werkzeug_version("tippecanoe"),
                    "befehl": " ".join(befehl_kacheln(DATEI, DATEI_PMTILES))},
    }
    lauf_log = dict(log, geht_auf=auf, eingaenge=eingaenge)
    schreibe(ziel, DATEI_HERKUNFT, (json.dumps(herkunft, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode())
    schreibe(ziel, DATEI_LOG, (json.dumps(lauf_log, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode())
    schreibe(ziel, "LIZENZ.txt", LIZENZ_TXT.encode("utf-8"))
    return herkunft, lauf_log


def zusammenfassung(herkunft, lauf_log):
    z = ["zeilen %d, doppelt %d, ohne Kennung %d, ohne Lage %d, ausserhalb %d, Rand %d" % (
        lauf_log["zeilen"], lauf_log["doppelt_im_eingang"], lauf_log["ohne_merkmal"], lauf_log["ohne_lage"],
        lauf_log["ausserhalb"], lauf_log["auf_dem_rand"])]
    z.append("geschrieben %d: kurz %d, lang %d (Sektorenfeuer %d; mit %s %d, nur nummeriert %d)" % (
        lauf_log["geschrieben"], lauf_log["je_klasse"]["kurz"], lauf_log["je_klasse"]["lang"], lauf_log["sektorenfeuer"],
        MERKMAL, lauf_log["geschrieben_mit_merkmal"], lauf_log["geschrieben_nur_nummeriert"]))
    z.append("nur nummeriert je Gebiet %s" % json.dumps(lauf_log["je_gebiet_nur_nummeriert"]))
    z.append("pruefnamen %s" % json.dumps(lauf_log["pruefnamen"], ensure_ascii=False))
    for g, n in lauf_log["je_gebiet"].items():
        z.append("  %-15s %7d" % (g, n))
    z.append("laengen %s" % json.dumps(lauf_log["laengen"]))
    z.append("geht auf: %r" % lauf_log["geht_auf"])
    z.append("%s %d B sha256 %s" % (herkunft["datei"], herkunft["byte"], herkunft["sha256"]))
    p = herkunft["pmtiles"]
    z.append("%s %d B sha256 %s (%s)" % (p["datei"], p["byte"], p["sha256"], p["werkzeug"]))
    z.append("osmStand %s" % herkunft["osmStand"])
    return "\n".join(z)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 64
    herkunft, lauf_log = baue(argv[0], argv[1], argv[2:])
    print(zusammenfassung(herkunft, lauf_log))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
