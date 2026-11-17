# nautly-hafenliste

## Deutsch

Hafenliste Europa für die Karte der App **Nautly** (Törn-Logbuch), abgeleitet aus OpenStreetMap.

**© OpenStreetMap-Mitwirkende** — <https://www.openstreetmap.org/copyright>

Diese Hafenliste ist eine abgeleitete Datenbank von OpenStreetMap und steht unter der **Open Database License (ODbL) 1.0** (Volltext: `LICENSE`).

- Abfragedatum: 17.11.2026 (Overpass API, overpass-api.de); den genauen OSM-Stand je Abfrage nennt `daten/HERKUNFT.json`.
- Die Abfragetexte liegen in `rezept/` (je Gebiet eine Datei), die Gebiete in `rezept/gebiete.json`.

### Daten und Skript

**Dateien in `daten/`:**
- `haefen-europa.geojson` ist die Hafenliste. Genau diese Datei, Byte für Byte, liegt in der App Nautly für Android.
- `HERKUNFT.json` nennt Lizenz, Prüfsumme, OSM-Stand und Prüfsumme jeder Overpass-Antwort, die Regel und die Zahl der Punkte je Klasse.
- `LIZENZ.txt` ist der Lizenzhinweis (Deutsch und Englisch).
- `lauf-log.json` und `paare-unter-1000m.tsv` zeigen, was das Skript gelesen, weggelassen und geschrieben hat.

**Inhalt:** Häfen, Marinas und Ankerplätze an den Küsten und Seen Europas, als Punkte. Jeder Punkt trägt `kind` (`hafen` oder `anker`), `name` (fehlt bei Einträgen ohne eigenen Namen), `osm` (das OSM-Objekt, etwa `way/185016124`), `osm_sz` (das Objekt trägt `seamark:type`), `sz_name` (es trägt `seamark:name`) und `platz` (0 bis 3, wie viel Platz die App für OpenSeaMap-Zeichen freihält). Die Datei selbst trägt `license`, `attribution` und `source`.

**Regeln:**
- `seamark:type=anchorage` oder `anchor_berth` wird `anker`. `leisure=marina`, `seamark:type=harbour` oder `harbour` (ausser `no`) wird `hafen`.
- Der Name ist `name`, und nur wenn er fehlt `seamark:name`. Namen mit `+` oder `;` und Namen über 255 Byte fallen weg. Ein Name, der nur ein Gattungswort ist („Marina“, „Luka“, „Småbåtshamn“), oder nur eine Liegeplatznummer (nur Ziffern oder ein einzelner Buchstabe), gilt als fehlend.
- Gleicher Name unter 500 m: Ein Eintrag bleibt. Einträge ohne Namen bleiben nur, wenn unter 500 m kein benannter liegt, und untereinander bleibt unter 300 m einer.
- Ein Eintrag bleibt nur, wenn er echt innerhalb eines Gebiets liegt, nicht auf dessen Rand.

**Erzeugen:**

```
python3 -I skript/abfragen.py holen <ordner>        # Overpass, mit Pausen, höchstens 15 Abfragen
python3 -I skript/hafenliste.py <ordner> daten       # schreibt daten/
python3 -I -m unittest discover -s skript            # Tests
```

Nur Python-Standardbibliothek, Python 3.9 oder neuer. Zwei Läufe über dieselben Antworten ergeben dieselben Bytes.

Die Daten sind unvollständig und ungeprüft und werden ohne Gewähr bereitgestellt. Nicht zur Navigation verwenden.

## English

Harbour list for Europe for the map of the app **Nautly** (sailing logbook), derived from OpenStreetMap.

**© OpenStreetMap contributors** — <https://www.openstreetmap.org/copyright>

This harbour list is a derived database of OpenStreetMap and is licensed under the **Open Database License (ODbL) 1.0** (full text: `LICENSE`).

- Query date: 17 November 2026 (Overpass API, overpass-api.de); `daten/HERKUNFT.json` gives the exact OSM snapshot of each query.
- The query texts are in `rezept/` (one file per area), the areas in `rezept/gebiete.json`.

### Data and script

**Files in `daten/`:**
- `haefen-europa.geojson` is the harbour list. This exact file, byte for byte, ships in the Nautly app for Android.
- `HERKUNFT.json` gives the licence, checksum, OSM snapshot and checksum of each Overpass response, the rule and the number of points per class.
- `LIZENZ.txt` is the licence notice (German and English).
- `lauf-log.json` and `paare-unter-1000m.tsv` show what the script read, left out and wrote.

**Content:** harbours, marinas and anchorages on the coasts and lakes of Europe, as points. Each point carries `kind` (`hafen` or `anker`), `name` (missing for entries without a name of their own), `osm` (the OSM object, e.g. `way/185016124`), `osm_sz` (the object has `seamark:type`), `sz_name` (it has `seamark:name`) and `platz` (0 to 3, how much room the app keeps free for OpenSeaMap symbols). The file itself carries `license`, `attribution` and `source`.

**Rules:**
- `seamark:type=anchorage` or `anchor_berth` becomes `anker`. `leisure=marina`, `seamark:type=harbour` or `harbour` (except `no`) becomes `hafen`.
- The name is `name`, and only if it is missing `seamark:name`. Names with `+` or `;` and names over 255 bytes are dropped. A name that is only a generic word ("Marina", "Luka", "Småbåtshamn") or only a berth number (digits only or a single letter) counts as missing.
- Same name within 500 m: one entry remains. Entries without a name remain only if no named entry lies within 500 m, and among each other one remains within 300 m.
- An entry remains only if it lies strictly inside an area, not on its edge.

**Generate:** see the commands above. Python standard library only, Python 3.9 or newer. Two runs over the same responses give the same bytes.

The data is incomplete and unverified and is provided as is. Do not use for navigation.
