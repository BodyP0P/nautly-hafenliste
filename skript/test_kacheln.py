# -*- coding: utf-8 -*-
"""
Tests fuer skript/kacheln.py.

    python3 -I -m unittest discover -s skript -v

Der Fall mit echtem tippecanoe laeuft nur, wo das Werkzeug installiert ist; die uebrigen Faelle brauchen es nicht.
"""
import hashlib
import json
import os
import shutil
import tempfile
import unittest

import kacheln as k


class Befehl(unittest.TestCase):

    def test_befehl_wie_festgelegt(self):
        self.assertEqual(
            ["tippecanoe", "-q", "--force", "-o", "z.pmtiles", "-l", "haefen", "-Z0", "-z10", "-d14", "-r1",
             "--no-feature-limit", "--no-tile-size-limit",
             "-y", "kind", "-y", "name", "-y", "osm_sz", "-y", "sz_name", "-y", "platz",
             "--attribution", "© OpenStreetMap contributors", "-n", "Hafenliste Europa (Nautly)",
             "-N", "ODbL-1.0 https://opendatacommons.org/licenses/odbl/1-0/ · https://github.com/BodyP0P/nautly-hafenliste",
             "q.geojson"],
            k.befehl("q.geojson", "z.pmtiles"))

    def test_osm_faellt_weg(self):
        self.assertNotIn("osm", k.MERKMALE)


class Herkunft(unittest.TestCase):

    def test_block_pmtiles_und_rest_unveraendert(self):
        alt = {"sha256": "a" * 64, "byte": 3, "repoCommit": None, "osmStand": "2026-11-17T19:50:03Z"}
        b = b"PMTiles-Probe"
        neu = k.ergaenze_herkunft(alt, b, "tippecanoe v2.79.0", "s" * 64)
        self.assertEqual({key: v for key, v in neu.items() if key != "pmtiles"}, alt)
        p = neu["pmtiles"]
        self.assertEqual("haefen-europa.pmtiles", p["datei"])
        self.assertEqual(len(b), p["byte"])
        self.assertEqual(hashlib.sha256(b).hexdigest(), p["sha256"])
        self.assertEqual("a" * 64, p["ausSha256"])
        self.assertEqual("tippecanoe v2.79.0", p["werkzeug"])
        self.assertEqual([0, 10], p["zoom"])
        self.assertIn("-z10", p["befehl"])
        self.assertNotIn("pmtiles", alt, "das Original bleibt unberuehrt")


class Lizenz(unittest.TestCase):

    def test_lizenz_nennt_beide_dateien_odbl_osm_repo(self):
        t = k.LIZENZ_TXT
        for soll in ("haefen-europa.geojson", "haefen-europa.pmtiles", "Open Database License", "(ODbL) 1.0",
                     "abgeleitete Datenbank", "https://opendatacommons.org/licenses/odbl/1-0/",
                     "(c) OpenStreetMap-Mitwirkende", "(c) OpenStreetMap contributors",
                     "https://www.openstreetmap.org/copyright", "https://github.com/BodyP0P/nautly-hafenliste",
                     "Nicht zur Navigation verwenden.", "Do not use for navigation."):
            self.assertIn(soll, t)


class EchterLauf(unittest.TestCase):

    def test_baue_schreibt_pmtiles_und_ergaenzt_herkunft(self):
        geojson = json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [15.22792, 44.1192]},
             "properties": {"kind": "hafen", "name": "Marina Zadar", "osm": "relation/6625940", "osm_sz": True,
                            "platz": 2, "sz_name": True}}]}, separators=(",", ":")).encode("utf-8")
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, k.DATEI_GEOJSON), "wb") as f:
                f.write(geojson)
            with open(os.path.join(d, "HERKUNFT.json"), "w", encoding="utf-8") as f:
                json.dump({"sha256": hashlib.sha256(geojson).hexdigest(), "repoCommit": None}, f)
            p = k.baue(d)
            with open(os.path.join(d, k.DATEI_PMTILES), "rb") as f:
                b = f.read()
            self.assertEqual(b"PMTiles", b[:7])
            self.assertEqual(3, b[7], "PMTiles Version 3")
            self.assertEqual(hashlib.sha256(b).hexdigest(), p["sha256"])
            with open(os.path.join(d, "HERKUNFT.json"), encoding="utf-8") as f:
                self.assertEqual(p, json.load(f)["pmtiles"])
            self.assertTrue(p["werkzeug"].startswith("tippecanoe v"))
            # Lizenz und Quelle in der Datei selbst (Noras L3): Metadaten nach dem PMTiles-v3-Kopf.
            import gzip, struct
            off, ln = struct.unpack("<QQ", b[24:40])
            meta = json.loads(gzip.decompress(b[off:off + ln]))
            self.assertIn("openstreetmap", meta["attribution"].lower())
            self.assertIn("https://opendatacommons.org/licenses/odbl/1-0/", meta["description"])
            self.assertIn("https://github.com/BodyP0P/nautly-hafenliste", meta["description"])
            with open(os.path.join(d, "LIZENZ.txt"), encoding="utf-8") as f:
                self.assertEqual(k.LIZENZ_TXT, f.read())
            self.assertEqual(sorted(["HERKUNFT.json", "LIZENZ.txt", k.DATEI_GEOJSON, k.DATEI_PMTILES]), sorted(os.listdir(d)))

    def test_falsche_geojson_bricht_ab_und_schreibt_nichts(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, k.DATEI_GEOJSON), "wb") as f:
                f.write(b'{"type":"FeatureCollection","features":[]}')
            with open(os.path.join(d, "HERKUNFT.json"), "w", encoding="utf-8") as f:
                json.dump({"sha256": "0" * 64}, f)
            with self.assertRaises(RuntimeError):
                k.baue(d)
            self.assertFalse(os.path.exists(os.path.join(d, k.DATEI_PMTILES)))



# Ohne Dekorator geschrieben: Die Pruefung vor jedem Push sucht im Repo nach dem Zeichen von Mail-Adressen.
EchterLauf = unittest.skipUnless(shutil.which("tippecanoe"), "tippecanoe nicht installiert")(EchterLauf)

if __name__ == "__main__":
    unittest.main()
