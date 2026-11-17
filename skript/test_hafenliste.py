# -*- coding: utf-8 -*-
"""
Tests fuer skript/hafenliste.py und skript/abfragen.py.

    python3 -I -m unittest discover -s skript -v

Die Tags von Marina Zadar und D-Marin Borik stammen aus OpenStreetMap (relation/6625940,
way/185016124; (c) OpenStreetMap-Mitwirkende, ODbL 1.0), gekuerzt auf die Schluessel, die das
Skript liest. Alle anderen Objekte sind ausgedacht.
"""
import hashlib
import itertools
import json
import math
import os
import random
import tempfile
import unittest

import abfragen
import hafenliste as h

HIER = os.path.dirname(os.path.abspath(__file__))
GEBIETE = abfragen.lade_gebiete(os.path.join(os.path.dirname(HIER), "rezept", "gebiete.json"))

# Ein Rechteck fuer die Mengenfaelle, weit weg von allen Raendern.
PROBE_GEBIET = [{"id": "probe", "s": 40.0, "w": 10.0, "n": 50.0, "o": 20.0}]

MARINA_ZADAR = {"leisure": "marina", "name": "Marina Zadar", "seamark:harbour:category": "marina",
                "seamark:name": "Marina Zadar", "seamark:type": "harbour", "type": "multipolygon"}
D_MARIN_BORIK = {"alt_name": "Marina Borik", "leisure": "marina", "name": "D-Marin Borik",
                 "seamark:harbour:category": "marina", "seamark:type": "harbour"}


def nord_um(lat, lon, meter):
    """Punkt `meter` genau noerdlich (gleicher Meridian), im Abstandsmass der App."""
    return lat + math.degrees(meter / h.METER_JE_SM / h.ERDRADIUS_SM), lon


def obj(typ, oid, tags, lat=45.0, lon=15.0):
    return (typ, oid, tags, (lat, lon))


def lies(pfad):
    with open(pfad, "rb") as f:
        return f.read()


def lauf(objekte, gebiete=PROBE_GEBIET):
    eintraege, log, paare = h.erzeuge(objekte, gebiete)
    return eintraege, log, paare


class EinzelobjektTest(unittest.TestCase):

    def test_marina_zadar_hafen_mit_seezeichen_und_kurzem_namen(self):
        e, grund = h.pruefe("relation", 6625940, MARINA_ZADAR, (44.119204, 15.2279169))
        self.assertIsNone(grund)
        self.assertEqual(e["kind"], "hafen")
        self.assertEqual(e["name"], "Marina Zadar")
        self.assertTrue(e["osm_sz"])
        self.assertTrue(e["sz_name"])
        self.assertEqual(e["platz"], 2)

    def test_d_marin_borik_seezeichen_ohne_seezeichen_namen(self):
        e, grund = h.pruefe("way", 185016124, D_MARIN_BORIK, (44.1297932, 15.2100886))
        self.assertIsNone(grund)
        self.assertEqual(e["name"], "D-Marin Borik")
        self.assertTrue(e["osm_sz"])
        self.assertFalse(e["sz_name"])
        self.assertEqual(e["platz"], 1)

    def test_platz_langer_seezeichen_name_und_ohne_seezeichen(self):
        e, _ = h.pruefe("node", 1, {"leisure": "marina", "name": "Marina Punat",
                                     "seamark:type": "harbour", "seamark:name": "ACI Marina Punat Krk"}, (45, 15))
        self.assertEqual(e["platz"], 3)
        e, _ = h.pruefe("node", 1, {"leisure": "marina", "name": "Marina Punat"}, (45, 15))
        self.assertEqual(e["platz"], 0)
        self.assertFalse(e["osm_sz"])

    def test_boje_faellt_weg(self):
        e, grund = h.pruefe("node", 1, {"seamark:type": "mooring", "mooring:category": "buoy",
                                         "name": "Boje 7"}, (45, 15))
        self.assertIsNone(e)
        self.assertEqual(grund, "keine Klasse")

    def test_harbour_no_faellt_weg(self):
        self.assertEqual(h.pruefe("node", 1, {"harbour": "no", "name": "X"}, (45, 15))[1], "keine Klasse")

    def test_ankerplatz_eigene_klasse(self):
        e, _ = h.pruefe("node", 1, {"seamark:type": "anchorage", "name": "Uvala Sv. Ante"}, (45, 15))
        self.assertEqual(e["kind"], "anker")
        e, _ = h.pruefe("node", 1, {"seamark:type": "anchor_berth", "name": "A"}, (45, 15))
        self.assertEqual(e["kind"], "anker")

    def test_ohne_namen_wird_namenlos(self):
        e, grund = h.pruefe("node", 1, {"leisure": "marina"}, (45, 15))
        self.assertIsNone(grund)
        self.assertIsNone(e["name"])
        self.assertEqual(e["namenlos_grund"], "ohne Namen")

    def test_nur_gattungswort_wird_namenlos(self):
        for n in ("Marina", "luka", "Port", "Lučica", "Marina (Bodensee)"):
            e, grund = h.pruefe("node", 1, {"leisure": "marina", "name": n}, (45, 15))
            self.assertIsNone(grund, n)
            self.assertIsNone(e["name"], n)
            self.assertEqual(e["namenlos_grund"], "nur Gattungswort", n)

    def test_gattungsnamen_nautly_werden_namenlos(self):
        for n in ("Småbåtshamn", "småbåtshavn", "Gästhamn", "Venesatama", "Port de Plaisance", "Capitainerie",
                  "Ausstiegsstelle"):
            e, grund = h.pruefe("node", 1, {"leisure": "marina", "name": n}, (45, 15))
            self.assertIsNone(grund, n)
            self.assertIsNone(e["name"], n)
            self.assertEqual(e["namenlos_grund"], "nur Gattungswort", n)
        for n in ("Småbåtshamn Lilla Bommen", "Ausstiegsstelle nur für Kanuten", "Port de Plaisance de Nice"):
            self.assertEqual(h.pruefe("node", 1, {"leisure": "marina", "name": n}, (45, 15))[0]["name"], n)

    def test_liegeplatznummer_wird_namenlos(self):
        for n in ("1", "12", "A", "b", "Ž"):
            e, _ = h.pruefe("node", 1, {"seamark:type": "anchor_berth", "name": n}, (45, 15))
            self.assertIsNone(e["name"], n)
            self.assertEqual(e["namenlos_grund"], "nur Liegeplatznummer", n)
        for n in ("A1", "12a", "Box 42", "Ab", "١٢"):
            e, _ = h.pruefe("node", 1, {"seamark:type": "anchor_berth", "name": n}, (45, 15))
            self.assertEqual(e["name"], n, n)

    def test_namenlos_mit_seezeichen_platz_1(self):
        e, _ = h.pruefe("node", 1, {"leisure": "marina", "name": "Marina",
                                     "seamark:type": "harbour", "seamark:name": "Marina"}, (45, 15))
        self.assertIsNone(e["name"])
        self.assertEqual(e["platz"], 1)

    def test_verbotene_zeichen_fallen_weg(self):
        self.assertEqual(h.pruefe("node", 1, {"leisure": "marina", "name": "A;B"}, (45, 15))[1], "verbotene Zeichen")
        self.assertEqual(h.pruefe("node", 1, {"leisure": "marina", "name": "A+B"}, (45, 15))[1], "verbotene Zeichen")

    def test_name_zu_lang(self):
        self.assertEqual(h.pruefe("node", 1, {"leisure": "marina", "name": "Marina " + "Ä" * 125}, (45, 15))[1],
                         "Name zu lang")
        e, _ = h.pruefe("node", 1, {"leisure": "marina", "name": "Marina " + "Ä" * 124}, (45, 15))
        self.assertIsNotNone(e)

    def test_klammer_nur_nach_liste(self):
        self.assertEqual(h.pruefe("node", 1, {"leisure": "marina", "name": "Hafen Lindau (Bodensee)"}, (45, 15))[0]["name"],
                         "Hafen Lindau")
        self.assertEqual(h.pruefe("node", 1, {"leisure": "marina", "name": "Hafen Ruderbaum (Altnau)"}, (45, 15))[0]["name"],
                         "Hafen Ruderbaum (Altnau)")

    def test_vereinshafen_bleibt(self):
        for n in ("Segelclub Kreuzlingen", "Jedriličarski klub Labud", "Seglerhafen Rorschach"):
            e, grund = h.pruefe("node", 1, {"leisure": "marina", "name": n}, (45, 15))
            self.assertIsNone(grund, n)
            self.assertEqual(e["name"], n)

    def test_name_vor_seamark_name_und_nfc(self):
        e, _ = h.pruefe("node", 1, {"leisure": "marina", "name": " Alter Hafen ", "seamark:name": "Hafen Arbon"}, (45, 15))
        self.assertEqual((e["name"], e["quelle"]), ("Alter Hafen", "name"))
        e, _ = h.pruefe("node", 1, {"seamark:type": "harbour", "seamark:name": "Žman"}, (45, 15))
        self.assertEqual((e["name"], e["quelle"]), ("Žman", "seamark:name"))


class MengeTest(unittest.TestCase):

    def test_dublette_499_m_einer_501_m_zwei(self):
        lat2, lon2 = nord_um(45.0, 15.0, 499)
        eintraege, log, _ = lauf([obj("node", 1, {"leisure": "marina", "name": "Luka Sali"}),
                                  obj("node", 2, {"leisure": "marina", "name": "luka sali"}, lat2, lon2)])
        self.assertEqual([h.osm_id(e) for e in eintraege], ["node/1"])
        self.assertEqual(log["klassen"]["hafen"]["weg"]["Dublette"], 1)
        lat2, lon2 = nord_um(45.0, 15.0, 501)
        eintraege, _, _ = lauf([obj("node", 1, {"leisure": "marina", "name": "Luka Sali"}),
                                obj("node", 2, {"leisure": "marina", "name": "Luka Sali"}, lat2, lon2)])
        self.assertEqual(len(eintraege), 2)

    def test_dublette_hafen_vor_anker(self):
        lat2, lon2 = nord_um(45.0, 15.0, 100)
        eintraege, _, _ = lauf([obj("node", 1, {"seamark:type": "anchorage", "name": "Pakleni"}),
                                obj("node", 2, {"harbour": "yes", "name": "Pakleni"}, lat2, lon2)])
        self.assertEqual([(h.osm_id(e), e["kind"]) for e in eintraege], [("node/2", "hafen")])

    def test_dublette_name_vor_seamark_name_dann_typ(self):
        lat2, lon2 = nord_um(45.0, 15.0, 100)
        eintraege, _, _ = lauf([obj("node", 1, {"seamark:type": "harbour", "seamark:name": "Veli Iž"}),
                                obj("way", 9, {"leisure": "marina", "name": "Veli Iž"}, lat2, lon2)])
        self.assertEqual([h.osm_id(e) for e in eintraege], ["way/9"])
        eintraege, _, _ = lauf([obj("relation", 1, {"leisure": "marina", "name": "Veli Iž"}),
                                obj("way", 9, {"leisure": "marina", "name": "Veli Iž"}, lat2, lon2)])
        self.assertEqual([h.osm_id(e) for e in eintraege], ["way/9"])

    def test_namenlos_allein_bleibt_nahe_benanntem_faellt_weg(self):
        lat2, lon2 = nord_um(45.0, 15.0, 499)
        eintraege, log, _ = lauf([obj("node", 1, {"leisure": "marina", "name": "Marina Zadar"}),
                                  obj("node", 2, {"seamark:type": "anchorage"}, lat2, lon2)])
        self.assertEqual([h.osm_id(e) for e in eintraege], ["node/1"])
        self.assertEqual(log["klassen"]["anker"]["weg"]["namenlos nahe benanntem Eintrag"], 1)
        lat2, lon2 = nord_um(45.0, 15.0, 501)
        eintraege, _, _ = lauf([obj("node", 1, {"leisure": "marina", "name": "Marina Zadar"}),
                                obj("node", 2, {"seamark:type": "anchorage"}, lat2, lon2)])
        self.assertEqual([h.osm_id(e) for e in eintraege], ["node/1", "node/2"])
        self.assertNotIn("name", h.als_feature(eintraege[1])["properties"])

    def test_gattungsname_nahe_benanntem_faellt_weg(self):
        lat2, lon2 = nord_um(45.0, 15.0, 200)
        eintraege, _, _ = lauf([obj("node", 1, {"leisure": "marina", "name": "Marina Zadar"}),
                                obj("node", 2, {"leisure": "marina", "name": "Marina"}, lat2, lon2)])
        self.assertEqual([h.osm_id(e) for e in eintraege], ["node/1"])

    def test_namenlose_untereinander_299_m_einer_301_m_zwei(self):
        lat2, lon2 = nord_um(45.0, 15.0, 299)
        eintraege, log, _ = lauf([obj("node", 1, {"seamark:type": "anchorage"}),
                                  obj("node", 2, {"harbour": "yes"}, lat2, lon2)])
        self.assertEqual([(h.osm_id(e), e["kind"]) for e in eintraege], [("node/2", "hafen")])
        self.assertEqual(log["klassen"]["anker"]["weg"]["namenlos nahe anderem namenlosen"], 1)
        lat2, lon2 = nord_um(45.0, 15.0, 301)
        eintraege, _, _ = lauf([obj("node", 1, {"seamark:type": "anchorage"}),
                                obj("node", 2, {"harbour": "yes"}, lat2, lon2)])
        self.assertEqual(len(eintraege), 2)

    def test_namenlos_wird_zuerst_gegen_benannte_geprueft(self):
        # A (Hafen, namenlos) 400 m vom benannten N, B (Anker, namenlos) 200 m von A und 600 m von N.
        # A faellt wegen N, B bleibt, statt mit A zusammen zu verschwinden.
        la, loa = nord_um(45.0, 15.0, 400)
        lb, lob = nord_um(45.0, 15.0, 600)
        eintraege, _, _ = lauf([obj("node", 1, {"leisure": "marina", "name": "Marina N"}),
                                obj("node", 2, {"harbour": "yes"}, la, loa),
                                obj("node", 3, {"seamark:type": "anchorage"}, lb, lob)])
        self.assertEqual([h.osm_id(e) for e in eintraege], ["node/1", "node/3"])

    def test_paare_unter_1000_m_ins_log(self):
        lat2, lon2 = nord_um(45.0, 15.0, 400)
        lat3, lon3 = nord_um(45.0, 15.0, 1500)
        _, _, paare = lauf([obj("way", 79636905, {"leisure": "marina", "name": "D-Marin Dalmacija"}),
                            obj("node", 5, {"leisure": "marina", "name": "Marina Dalmatia"}, lat2, lon2),
                            obj("node", 6, {"leisure": "marina", "name": "Fern"}, lat3, lon3)])
        self.assertEqual(paare, [["node/5", "Marina Dalmatia", "way/79636905", "D-Marin Dalmacija", 400]])

    def test_lauf_log_geht_auf(self):
        lat2, lon2 = nord_um(45.0, 15.0, 100)
        _, log, _ = lauf([obj("node", 1, {"leisure": "marina", "name": "A"}),
                          obj("node", 2, {"leisure": "marina", "name": "A"}, lat2, lon2),
                          obj("node", 3, {"leisure": "marina", "name": "A;B"}),
                          obj("node", 4, {"seamark:type": "anchorage"}, 60.0, 15.0),
                          obj("node", 1, {"leisure": "marina", "name": "A"}),
                          ("node", 7, {"leisure": "marina", "name": "B"}, None),
                          obj("node", 8, {"amenity": "bench"})])
        self.assertEqual(h.geht_auf(log), {"hafen": True, "anker": True})
        self.assertEqual(log["doppelt_im_eingang"], 1)
        self.assertEqual(log["keine_klasse"], 1)
        self.assertEqual(log["klassen"]["anker"]["weg"]["ausserhalb der Gebiete"], 1)
        self.assertEqual(log["klassen"]["hafen"]["weg"]["keine Lage"], 1)


class GebieteTest(unittest.TestCase):

    def test_kein_paar_hat_nur_eine_gemeinsame_kante(self):
        for a, b in itertools.combinations(GEBIETE, 2):
            breite = min(a["o"], b["o"]) - max(a["w"], b["w"])
            hoehe = min(a["n"], b["n"]) - max(a["s"], b["s"])
            if breite < 0 or hoehe < 0:
                continue
            self.assertTrue(breite > 0 and hoehe > 0,
                            "%s und %s beruehren sich nur an einer Kante oder Ecke" % (a["id"], b["id"]))

    def test_kein_hafen_auf_einer_inneren_kante_fehlt(self):
        # Jeder Kantenpunkt, dessen Umgebung ganz abgedeckt ist (also eine innere Kante), muss echt
        # innerhalb eines Rechtecks liegen. Sonst haette Overpass ihn, `within` aber nicht.
        eps = 1e-4

        def gedeckt(lat, lon):
            return any(x["s"] <= lat <= x["n"] and x["w"] <= lon <= x["o"] for x in GEBIETE)

        geprueft = 0
        for g in GEBIETE:
            kanten = []
            for i in range(0, 201):
                t = i / 200.0
                lat = round(g["s"] + t * (g["n"] - g["s"]), 5)
                lon = round(g["w"] + t * (g["o"] - g["w"]), 5)
                kanten += [(g["s"], lon), (g["n"], lon), (lat, g["w"]), (lat, g["o"])]
            for lat, lon in kanten:
                if not all(gedeckt(lat + a, lon + b) for a in (-eps, 0, eps) for b in (-eps, 0, eps)):
                    continue
                geprueft += 1
                self.assertEqual(h.gebiet_von(lat, lon, GEBIETE), "innen", "%s Kante %s,%s" % (g["id"], lat, lon))
        self.assertGreater(geprueft, 1000)

    def test_hafen_auf_der_kante_westmed_adria_bleibt(self):
        eintraege, _, _ = h.erzeuge([obj("node", 1, {"leisure": "marina", "name": "Kantenhafen"}, 40.0, 10.0),
                                     obj("node", 2, {"leisure": "marina", "name": "Kantenhafen 2"}, 40.0, 10.1)],
                                    GEBIETE)
        self.assertEqual(len(eintraege), 2)

    def test_hafen_auf_dem_aeusseren_rand_faellt_weg(self):
        eintraege, log, _ = h.erzeuge([obj("node", 1, {"leisure": "marina", "name": "Randhafen"}, 35.0, 0.0),
                                       obj("node", 2, {"leisure": "marina", "name": "Draussen"}, 30.0, 0.0)],
                                      GEBIETE)
        self.assertEqual(eintraege, [])
        self.assertEqual(log["klassen"]["hafen"]["weg"]["auf dem Rand der Gebiete"], 1)
        self.assertEqual(log["klassen"]["hafen"]["weg"]["ausserhalb der Gebiete"], 1)

    def test_rand_gilt_fuer_die_gerundete_lage(self):
        # 10.0000001 liegt gerundet auf der Kante von adria, aber echt in westmed: bleibt.
        # 35.0000004 liegt roh echt in westmed, gerundet auf dessen Suedrand (aeusserer Rand): faellt weg.
        eintraege, _, _ = h.erzeuge([obj("node", 1, {"leisure": "marina", "name": "A"}, 40.0, 10.0000001),
                                     obj("node", 2, {"leisure": "marina", "name": "B"}, 35.0000004, 0.0)], GEBIETE)
        self.assertEqual([h.osm_id(e) for e in eintraege], ["node/1"])

    def test_binnenseen_und_inseln_abgedeckt(self):
        orte = {"Bodensee Romanshorn": (47.566, 9.380), "Zuerichsee Rapperswil": (47.226, 8.815),
                "Genfersee Ouchy": (46.506, 6.627), "Balaton Balatonfuered": (46.955, 17.893),
                "Berlin Wannsee": (52.420, 13.170), "Gardasee Riva": (45.885, 10.843),
                "Lago Maggiore Locarno": (46.165, 8.800), "Lampedusa": (35.498, 12.605),
                "Kanaren Las Palmas": (28.130, -15.420), "Madeira Funchal": (32.645, -16.910),
                "Azoren Horta": (38.530, -28.625), "Island Reykjavik": (64.150, -21.940),
                "Faeroeer Torshavn": (62.008, -6.770), "Asowsches Meer Berdjansk": (46.750, 36.790),
                "Asowsches Meer Rostow": (47.210, 39.700)}
        for n, (lat, lon) in orte.items():
            self.assertEqual(h.gebiet_von(lat, lon, GEBIETE), "innen", n)

    def test_abfragen_ohne_meta_und_nur_klassenfilter(self):
        for g in GEBIETE:
            t = abfragen.abfragetext(g)
            self.assertNotIn("meta", t)
            self.assertIn("out center tags;", t)
            self.assertNotIn("mooring", t)

    def test_antwort_mit_personenbezug_wird_abgelehnt(self):
        gut = {"osm3s": {"timestamp_osm_base": "2026-11-17T00:00:00Z"}, "elements": [{"type": "node", "id": 1}]}
        self.assertIsNone(abfragen.pruefe_antwort(json.dumps(gut).encode()))
        schlecht = dict(gut, elements=[{"type": "node", "id": 1, "user": "x", "uid": 1}])
        self.assertIn("user", abfragen.pruefe_antwort(json.dumps(schlecht).encode()))
        abbruch = dict(gut, remark="runtime error: Query timed out")
        self.assertIn("Bemerkung", abfragen.pruefe_antwort(json.dumps(abbruch).encode()))


class AusgabeTest(unittest.TestCase):

    def _objekte(self):
        lat2, lon2 = nord_um(45.0, 15.0, 2000)
        return [obj("relation", 6625940, MARINA_ZADAR, 44.119204, 15.2279169),
                obj("way", 185016124, D_MARIN_BORIK, 44.1297932, 15.2100886),
                obj("node", 3, {"seamark:type": "anchorage"}, lat2, lon2),
                obj("node", 4, {"leisure": "marina", "name": "Šibenik"}, 43.7, 15.9)]

    def test_lizenzfelder_auf_oberster_ebene(self):
        eintraege, _, _ = lauf(self._objekte())
        d = json.loads(h.geojson_bytes(eintraege).decode("utf-8"))
        self.assertEqual(sorted(d.keys()), ["attribution", "features", "license", "source", "type"])
        self.assertEqual(d["license"], "ODbL-1.0 https://opendatacommons.org/licenses/odbl/1-0/")
        self.assertEqual(d["attribution"], "© OpenStreetMap contributors https://www.openstreetmap.org/copyright")
        self.assertEqual(d["source"], "https://github.com/BodyP0P/nautly-hafenliste")
        self.assertEqual(d["type"], "FeatureCollection")
        for f in d["features"]:
            self.assertTrue(set(f["properties"]) <= {"kind", "name", "osm", "osm_sz", "platz", "sz_name"})
            self.assertNotIn(None, f["properties"].values())

    def test_zwei_laeufe_dieselben_bytes_auch_bei_anderer_reihenfolge(self):
        a = h.geojson_bytes(lauf(self._objekte())[0])
        b = h.geojson_bytes(lauf(self._objekte())[0])
        self.assertEqual(a, b)
        gemischt = self._objekte()
        random.Random(7).shuffle(gemischt)
        self.assertEqual(h.geojson_bytes(lauf(gemischt)[0]), a)

    def test_ausgabe_form(self):
        b = h.geojson_bytes(lauf(self._objekte())[0])
        self.assertTrue(b.startswith(b'{"attribution":'))
        self.assertTrue(b.endswith(b'"type":"FeatureCollection"}'))
        self.assertIn("Šibenik".encode("utf-8"), b)
        d = json.loads(b.decode("utf-8"))
        self.assertEqual([f["properties"]["osm"] for f in d["features"]],
                         ["node/3", "node/4", "way/185016124", "relation/6625940"])
        self.assertEqual(d["features"][3]["geometry"]["coordinates"], [15.22792, 44.1192])

    def test_baue_schreibt_fuenf_dateien_byte_gleich(self):
        antwort = {"version": 0.6, "osm3s": {"timestamp_osm_base": "2026-11-17T12:00:00Z"},
                   "elements": [{"type": "relation", "id": 6625940, "center": {"lat": 44.119204, "lon": 15.2279169},
                                 "tags": MARINA_ZADAR},
                                {"type": "node", "id": 3, "lat": 43.7, "lon": 15.9, "tags": {"seamark:type": "anchorage"}}]}
        with tempfile.TemporaryDirectory() as t:
            roh = os.path.join(t, "roh")
            os.makedirs(roh)
            gebiete_pfad = os.path.join(t, "gebiete.json")
            with open(gebiete_pfad, "w", encoding="utf-8") as f:
                json.dump({"gebiete": PROBE_GEBIET}, f)
            with open(os.path.join(roh, "probe.json"), "w", encoding="utf-8") as f:
                json.dump(antwort, f)
            ergebnisse = []
            for lauf_nr in (1, 2):
                ziel = os.path.join(t, "aus%d" % lauf_nr)
                h.baue(roh, ziel, gebiete_pfad)
                ergebnisse.append({n: lies(os.path.join(ziel, n)) for n in sorted(os.listdir(ziel))})
            self.assertEqual(sorted(ergebnisse[0]), ["HERKUNFT.json", "LIZENZ.txt", "haefen-europa.geojson", "lauf-log.json",
                                                   "paare-unter-1000m.tsv"])
            self.assertEqual(ergebnisse[0], ergebnisse[1])
            herkunft = json.loads(ergebnisse[0]["HERKUNFT.json"].decode("utf-8"))
            for feld in ("lizenz", "lizenzUri", "repo", "repoCommit", "sha256", "byte", "quelle", "rezept", "regel",
                         "punkteJeKlasse"):
                self.assertIn(feld, herkunft)
            self.assertEqual(herkunft["sha256"], hashlib.sha256(ergebnisse[0]["haefen-europa.geojson"]).hexdigest())
            self.assertEqual(herkunft["punkteJeKlasse"], {"hafen": 1, "anker": 1})
            self.assertEqual(herkunft["quelle"]["antworten"][0]["timestamp_osm_base"], "2026-11-17T12:00:00Z")
            lizenz = ergebnisse[0]["LIZENZ.txt"].decode("utf-8")
            self.assertIn("abgeleitete Datenbank", lizenz)
            self.assertIn("derivative database", lizenz)
            self.assertIn("https://opendatacommons.org/licenses/odbl/1-0/", lizenz)
            self.assertIn("https://github.com/BodyP0P/nautly-hafenliste", lizenz)
            self.assertIn("Nicht zur Navigation verwenden.", lizenz)


if __name__ == "__main__":
    unittest.main()
