# -*- coding: utf-8 -*-
"""
Tests fuer skript/feuer.py.

    python3 -I -m unittest discover -s skript -v

Der Fall mit echtem osmium und tippecanoe laeuft nur, wo beide Werkzeuge installiert sind; die uebrigen Faelle brauchen
sie nicht.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import feuer as f
import kacheln

GEBIETE = [
    {"id": "adria", "s": 35.0, "w": 10.0, "n": 46.0, "o": 21.1},
    {"id": "ostmed", "s": 33.0, "w": 21.0, "n": 46.5, "o": 42.0},
]


def licht(**merkmale):
    """Tags eines einzelnen Lichts: licht(character="Fl", group="2") -> seamark:light:character=Fl, ..."""
    return {"seamark:light:" + k: v for k, v in merkmale.items()}


def sektoren(*lichter, **gemeinsam):
    """Tags eines Sektorenfeuers: je Licht seamark:light:<n>:<merkmal>, n ab 1."""
    t = {}
    for n, l in enumerate(lichter, start=1):
        for k, v in dict(gemeinsam, **l).items():
            t["seamark:light:%d:%s" % (n, k)] = v
    return t


class Kennung(unittest.TestCase):
    """Die Kennung, wie OpenSeaMap sie schreibt; die Beispiele stehen so in Doras Bildern (B3, B4)."""

    def einzeln(self, soll, **m):
        self.assertEqual([soll], f.kennung(licht(**m)))

    def test_gazenica_fl2r_4s2m(self):
        self.einzeln("Fl(2)R.4s2M", character="Fl", group="2", colour="red", period="4", range="2")

    def test_ostri_rat_weiss_ohne_farbbuchstaben(self):
        self.einzeln("Fl(3)10s14m15M", character="Fl", group="3", colour="white", period="10", height="14", range="15")

    def test_kiel_fl_g_4s(self):
        self.einzeln("Fl.G.4s", character="Fl", colour="green", period="4")

    def test_borik_fl_r_3s5m4m(self):
        self.einzeln("Fl.R.3s5m4M", character="Fl", colour="red", period="3", height="5", range="4")

    def test_fl2g_5s6m4m(self):
        self.einzeln("Fl(2)G.5s6m4M", character="Fl", group="2", colour="green", period="5", height="6", range="4")

    def test_nur_zeichen(self):
        self.einzeln("Q", character="Q", colour="white")

    def test_q_lfl_mit_gruppe(self):
        self.einzeln("Q(6)+LFl.15s", character="Q+LFl", group="6", period="15")

    def test_unbekanntes_zeichen_wie_java(self):
        self.einzeln("null.R", character="Blink", colour="red")

    def test_zahlen_wie_decimalformat(self):
        self.einzeln("Iso.R.2.5s", character="Iso", colour="red", period="2.5")
        self.einzeln("Iso.R.4s", character="Iso", colour="red", period="4.0")
        self.einzeln("Iso.R.1.2s", character="Iso", colour="red", period="1.25")   # HALF_EVEN, 1.25 ist exakt
        self.einzeln("Iso.R.0.3s", character="Iso", colour="red", period="0.35")   # binaer 0.3499...
        self.einzeln("Iso.R", character="Iso", colour="red", period="lang")       # keine Zahl: fehlt

    def test_richtfeuer_und_vertikal(self):
        self.einzeln("DirOc.WRG(vert)6s", character="Oc", colour="white;red;green", period="6",
                     category="directional;vertical")

    def test_sektorenfeuer_eine_gruppe_drei_farben(self):
        t = sektoren({"colour": "white", "range": "9"}, {"colour": "red", "range": "6"},
                     {"colour": "green", "range": "6"}, character="Fl", period="4", height="10")
        self.assertEqual(["Fl.WRG.4s10m9-6M"], f.kennung(t))

    def test_sektorenfeuer_zwei_farben_und_al(self):
        t = sektoren({"colour": "white", "range": "9"}, {"colour": "red", "range": "6"}, character="Al.Fl", period="4")
        self.assertEqual(["Fl.WR.4s9/6M"], f.kennung(t))

    def test_sektorenfeuer_zwei_gruppen_groessere_zuerst(self):
        t = sektoren({"colour": "red", "range": "3", "character": "Oc", "period": "5"},
                     {"colour": "white", "range": "9", "character": "Fl", "period": "4"},
                     {"colour": "green", "range": "7", "character": "Fl", "period": "4"})
        self.assertEqual(["Fl.WG.4s9/7M", "Oc.R.5s3M"], f.kennung(t))


class Klasse(unittest.TestCase):
    """Doras Startwerte B4: kurz bis 10 Zeichen, lang darueber. Sabotage (d) kippt hier."""

    def test_zehn_zeichen_kurz(self):
        self.assertEqual(f.KLASSE_KURZ, f.klasse(["Fl(2)R.4s2"]))

    def test_elf_zeichen_lang(self):
        self.assertEqual(f.KLASSE_LANG, f.klasse(["Fl(2)R.4s2M"]))

    def test_gazenica_lang_kiel_kurz(self):
        self.assertEqual(f.KLASSE_LANG, f.klasse(f.kennung(licht(character="Fl", group="2", colour="red", period="4",
                                                                 range="2"))))
        self.assertEqual(f.KLASSE_KURZ, f.klasse(f.kennung(licht(character="Fl", colour="green", period="4"))))

    def test_laengste_zeile_zaehlt(self):
        self.assertEqual(f.KLASSE_LANG, f.klasse(["Q", "Fl.WG.4s9/7M"]))


def merkmal(fid, tags, lon, lat):
    return fid, tags, {"type": "Point", "coordinates": [lon, lat]}


class Erzeugen(unittest.TestCase):

    def test_mit_kennung_auch_nur_nummeriert(self):
        """Oscars Nachtrag F-B4-2: Sektorenfeuer mit nur nummerierten Schluesseln gehoeren dazu, getrennt gezaehlt."""
        punkte, log = f.erzeuge([
            merkmal("n1", licht(character="Fl", colour="red", period="4"), 15.2, 44.1),
            merkmal("n2", sektoren({"colour": "white", "range": "9"}, {"colour": "red", "range": "6"},
                                   character="Fl", period="4", height="10"), 15.3, 44.1),
            merkmal("n3", {"seamark:light:colour": "red"}, 15.4, 44.1),
            merkmal("n4", {"seamark:light:1:colour": "red", "seamark:light:1:character": " "}, 15.5, 44.1),
        ], GEBIETE)
        self.assertEqual([1, 2], [p["id"] for p in punkte])
        self.assertEqual([f.KLASSE_KURZ, f.KLASSE_LANG], [p["klasse"] for p in punkte])   # "Fl.WR.4s10m9/6M"
        self.assertEqual(2, log["ohne_merkmal"])
        self.assertEqual(1, log["geschrieben_mit_merkmal"])
        self.assertEqual(1, log["geschrieben_nur_nummeriert"])
        self.assertEqual({"adria": 1, "ostmed": 0}, log["je_gebiet_nur_nummeriert"])
        self.assertTrue(all(f.geht_auf(log).values()))

    def test_nummerierung_ab_zwei_nimmt_sektorenzweig(self):
        t = {"seamark:light:2:character": "Fl", "seamark:light:2:colour": "green", "seamark:light:2:period": "4"}
        self.assertEqual(["Fl.G.4s"], f.kennung(t))

    def test_pruefnamen_im_log(self):
        tags = dict(sektoren({"colour": "white", "range": "15"}, character="Fl", group="3", period="10"),
                    **{"seamark:name": "Ostri Rat"})
        _, log = f.erzeuge([merkmal("n9", tags, 15.2, 44.1)], GEBIETE)
        self.assertEqual([{"osm": "node/9", "name": "Ostri Rat", "klasse": f.KLASSE_LANG, "zeilen": ["Fl(3)W.10s15M"],
                           "schluessel": "nur nummeriert"}], log["pruefnamen"])

    def test_gebiete_innen_rand_aussen_und_je_gebiet(self):
        punkte, log = f.erzeuge([
            merkmal("n1", licht(character="Fl"), 15.2, 44.1),          # adria
            merkmal("n2", licht(character="Fl"), 21.05, 40.0),         # adria und ostmed (Ueberlappung)
            merkmal("n3", licht(character="Fl"), 10.0, 40.0),          # Rand
            merkmal("n4", licht(character="Fl"), 5.0, 40.0),           # aussen
        ], GEBIETE)
        self.assertEqual([1, 2], [p["id"] for p in punkte])
        self.assertEqual({"adria": 2, "ostmed": 1}, log["je_gebiet"])
        self.assertEqual(1, log["auf_dem_rand"])
        self.assertEqual(1, log["ausserhalb"])
        self.assertTrue(all(f.geht_auf(log).values()))

    def test_doppelt_aus_zwei_auszuegen_und_flaeche(self):
        punkte, log = f.erzeuge([
            merkmal("n7", licht(character="Fl"), 15.2, 44.1),
            merkmal("n7", licht(character="Fl"), 15.2, 44.1),
            ("w5", licht(character="Fl"), {"type": "LineString", "coordinates": [[15.0, 44.0], [15.2, 44.2]]}),
            ("a10", licht(character="Fl"), {"type": "Polygon", "coordinates": [[[15.0, 44.0], [15.2, 44.0],
                                                                                [15.2, 44.2], [15.0, 44.0]]]}),
        ], GEBIETE)
        self.assertEqual([("node", 7), ("way", 5)], [(p["typ"], p["id"]) for p in punkte])
        self.assertEqual(2, log["doppelt_im_eingang"])
        self.assertEqual((44.1, 15.1), (punkte[1]["lat"], punkte[1]["lon"]))

    def test_klasse_im_punkt(self):
        punkte, _ = f.erzeuge([
            merkmal("n1", licht(character="Fl", group="2", colour="red", period="4", range="2"), 15.2, 44.1),
            merkmal("n2", licht(character="Fl", colour="green", period="4"), 15.3, 44.1),
        ], GEBIETE)
        self.assertEqual([2, 1], [p["klasse"] for p in punkte])


class Ausgabe(unittest.TestCase):

    def test_nur_lage_und_klasse_keine_kennung(self):
        punkte, _ = f.erzeuge([
            merkmal("n2", licht(character="Fl", group="2", colour="red", period="4", range="2", name="Gazenica"),
                    15.2600049, 44.0930049),
            merkmal("n1", licht(character="Fl", colour="green", period="4"), 15.3, 44.1),
        ], GEBIETE)
        b = f.geojson_bytes(punkte)
        d = json.loads(b)
        self.assertEqual([{"klasse": 1}, {"klasse": 2}], [x["properties"] for x in d["features"]])
        self.assertEqual([15.26, 44.093], d["features"][1]["geometry"]["coordinates"])
        for verboten in (b"Fl", b"Gazenica", b"osm", b"node"):
            self.assertNotIn(verboten, b)

    def test_deterministisch(self):
        e = [merkmal("n%d" % i, licht(character="Fl"), 15.0 + i / 100, 44.0) for i in (3, 1, 2)]
        a = f.geojson_bytes(f.erzeuge(e, GEBIETE)[0])
        b = f.geojson_bytes(f.erzeuge(list(reversed(e)), GEBIETE)[0])
        self.assertEqual(a, b)


class Werkzeuge(unittest.TestCase):

    def test_kein_overpass_kein_netz(self):
        with open(f.__file__, encoding="utf-8") as h:
            quelle = h.read().lower()
        for verboten in ("overpass-api", "interpreter", "import urllib", "import http", "import socket", "requests"):
            self.assertNotIn(verboten, quelle)

    def test_osmium_befehle(self):
        self.assertEqual(["osmium", "tags-filter", "x.osm.pbf", "nwr/seamark:light:*", "-t", "--overwrite", "-o", "y"],
                         f.befehl_filter("x.osm.pbf", "y"))
        self.assertEqual(["osmium", "export", "y", "-f", "geojsonseq", "-u", "type_id", "--overwrite", "-o", "z"],
                         f.befehl_export("y", "z"))

    def test_kacheln_nur_zoom_10(self):
        b = f.befehl_kacheln("q.geojson", "z.pmtiles")
        self.assertIn("-Z10", b)
        self.assertIn("-z10", b)
        self.assertEqual(["-l", "feuer"], b[b.index("-l"):b.index("-l") + 2])
        self.assertEqual(["-y", "klasse"], b[b.index("-y"):b.index("-y") + 2])
        self.assertEqual(1, b.count("-y"))


class Lizenz(unittest.TestCase):

    def test_gleich_wie_kacheln_und_nennt_feuer(self):
        self.assertEqual(kacheln.LIZENZ_TXT, f.LIZENZ_TXT)
        for soll in ("feuer-europa.geojson", "feuer-europa.pmtiles", "haefen-europa.pmtiles", "(ODbL) 1.0",
                     "abgeleitete Datenbank", "derivative database", "HERKUNFT-feuer.json",
                     "Nicht zur Navigation verwenden.", "Do not use for navigation."):
            self.assertIn(soll, f.LIZENZ_TXT)


OSM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="probe">
 <node id="1" version="1" lat="44.0930000" lon="15.2600000">
  <tag k="seamark:type" v="light_minor"/>
  <tag k="seamark:light:character" v="Fl"/>
  <tag k="seamark:light:group" v="2"/>
  <tag k="seamark:light:colour" v="red"/>
  <tag k="seamark:light:period" v="4"/>
  <tag k="seamark:light:range" v="2"/>
 </node>
 <node id="2" version="1" lat="44.1000000" lon="15.3000000">
  <tag k="seamark:light:character" v="Fl"/>
  <tag k="seamark:light:colour" v="green"/>
  <tag k="seamark:light:period" v="4"/>
 </node>
 <node id="3" version="1" lat="44.1100000" lon="15.3100000">
  <tag k="seamark:light:1:character" v="Fl"/>
  <tag k="seamark:light:1:colour" v="white"/>
 </node>
 <node id="4" version="1" lat="44.1200000" lon="15.3200000">
  <tag k="amenity" v="bench"/>
 </node>
 <node id="5" version="1" lat="10.0" lon="10.0">
  <tag k="seamark:light:character" v="Fl"/>
 </node>
</osm>
"""


class EchterLauf(unittest.TestCase):

    def test_osmium_und_tippecanoe(self):
        if not (shutil.which("osmium") and shutil.which("tippecanoe")):
            self.skipTest("osmium oder tippecanoe fehlt")
        d = tempfile.mkdtemp()
        try:
            xml = os.path.join(d, "probe.osm")
            with open(xml, "w", encoding="utf-8") as h:
                h.write(OSM_XML)
            pbf = os.path.join(d, "probe-latest.osm.pbf")
            subprocess.run(["osmium", "cat", xml, "-o", pbf,
                            "--output-header=osmosis_replication_timestamp=2026-11-20T21:21:00Z"], check=True)
            ziel = os.path.join(d, "daten")
            herkunft, log = f.baue(os.path.join(d, "arbeit"), ziel, [pbf])
            self.assertEqual(3, herkunft["punkte"])
            self.assertEqual({"kurz": 2, "lang": 1}, herkunft["punkteJeKlasse"])
            self.assertEqual(1, herkunft["punkteNurNummeriert"])
            self.assertEqual("2026-11-20T21:21:00Z", herkunft["osmStand"])
            self.assertEqual(1, log["ausserhalb"])
            self.assertEqual(sorted([f.DATEI, f.DATEI_PMTILES, f.DATEI_HERKUNFT, f.DATEI_LOG, "LIZENZ.txt"]),
                             sorted(os.listdir(ziel)))
            with open(os.path.join(ziel, f.DATEI_PMTILES), "rb") as h:
                self.assertEqual(b"PMTiles\x03", h.read(8))
            self.assertEqual([10, 10], herkunft["pmtiles"]["zoom"])
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
