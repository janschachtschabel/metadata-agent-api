# WLO-Repository-Felder

Alle Felder, die beim Upload ins WLO edu-sharing Repository geschrieben werden —
Stand Schema-Version **2.0.0** (Kontexte `default` und `mds_oeh`, identisch).

Maßgeblich ist das Flag `system.repo_field: true` im Schema. `get_repo_fields()`
sammelt daraus `core.json` **plus** das Schema des erkannten Inhaltstyps;
`_normalize_for_repo()` schreibt ausschließlich Felder aus dieser Menge.

Legende: **sichtbar** = wird im Webcomponent-Canvas angezeigt (`ask_user: true`),
**versteckt** = wird nicht angezeigt (`ask_user: false`), Wert läuft aber von
`/generate` bis `/upload` durch.

---

## core.json — gilt für alle Inhaltstypen

| Feld | Label | Canvas | KI |
|------|-------|--------|----|
| `cclom:title` | Titel | sichtbar | ja |
| `cclom:general_description` | Beschreibungstext | sichtbar | ja |
| `cclom:general_keyword` | Schlagwörter | sichtbar | ja |
| `ccm:wwwurl` | Web-URL | sichtbar | ja |
| `preview:url` | URL des Vorschaubildes | versteckt | ja |
| `cclom:general_language` | Sprache | sichtbar | ja |
| `ccm:educationalcontext` | Bildungsstufe | sichtbar | ja |
| `ccm:taxonid` | Fach | sichtbar | ja |
| `ccm:educationalintendedenduserrole` | Zielgruppe | sichtbar | ja |
| `ccm:oeh_quality_relevancy_for_education` | Geeignet für Bildung (WLO-Suche) | versteckt | ja |
| `ccm:oeh_quality_criminal_law` | Strafrecht | versteckt | ja |
| `ccm:oeh_quality_protection_of_minors` | Jugendschutz | versteckt | ja |
| `ccm:oeh_quality_copyright_law` | Urheberrecht | versteckt | ja |
| `ccm:oeh_quality_personal_law` | Persönlichkeitsrechte | versteckt | ja |
| `ccm:oeh_quality_correctness` | Sachrichtigkeit | versteckt | ja |
| `ccm:oeh_quality_data_privacy` | Datenschutz | versteckt | ja |
| `ccm:oeh_quality_neutralness` | Neutralität | versteckt | ja |
| `ccm:oeh_quality_didactics` | Didaktik/Methodik | versteckt | ja |
| `ccm:oeh_quality_medial` | Medial passend | versteckt | ja |
| `ccm:oeh_quality_transparentness` | Anbieter Renommee | versteckt | ja |
| `ccm:oeh_quality_currentness` | Aktualität | versteckt | ja |
| `ccm:oeh_buffet_criteria` | Kriterien für Redaktionsbuffet | versteckt | ja |

**Nicht** als Repo-Feld markiert (bewusst): `ccm:oeh_extendedType` (wird separat
über den Extended-Data-Pfad geschrieben) und `oeh:new_lrt` (wird beim Upload aus
dem Inhaltstyp nach `ccm:oeh_lrt` abgeleitet).

---

## Qualitätsfelder — Werte

Die Wertebereiche stammen aus dem Live-Metadatensatz `mds_oeh` des Repositories
(`/rest/mds/v1/metadatasets/-home-/mds_oeh`, Staging und Prod identisch,
geprüft am 2026-08-10).

Nachprüfen lässt sich das jederzeit — das Skript vergleicht alle 13 Vokabulare
Feld für Feld gegen beide Repositories und liefert Exit-Code 1 bei Abweichung:

```bash
python scripts/check_quality_vocabularies.py
```

Die beiden unten dokumentierten Abweichungen (`correctness`, `usable_for_buffet`)
sind dort als bewusst akzeptiert hinterlegt und werden als `OK*` ausgewiesen.

### Am lebenden Repository verifiziert

Ein Testknoten wurde am 2026-08-10 gegen Staging geschrieben und zurückgelesen.
Alle 13 Felder kamen wertgleich an; 11 lösen auf ein Label auf, die zwei
dokumentierten Abweichungen liefern wie erwartet ein leeres `_DISPLAYNAME`:

| Feld | Gespeichert | `_DISPLAYNAME` |
|------|-------------|----------------|
| `ccm:oeh_quality_criminal_law` | `…/quality/no_auto_findings` | keine Auffälligkeiten gefunden (Maschine) |
| `ccm:oeh_quality_personal_law` | `…/quality/auto_findings` | Auffälligkeiten gefunden (Maschine) |
| `ccm:oeh_quality_data_privacy` | `…/quality_data_privacy/5` | ✰✰✰✰✰ keinerlei Datenweitergabe |
| `ccm:oeh_quality_medial` | `…/quality_media/3` | ✰✰✰ Medial passend |
| `ccm:oeh_quality_transparentness` | `…/quality_transparency/5` | ✰✰✰✰✰ renommierter Anbieter, korrekte Kontaktangaben |
| `ccm:oeh_quality_relevancy_for_education` | `1` | Ja - geeignet |
| `ccm:oeh_quality_currentness` | `3` | ✰✰✰ 3-A zeitlos aktuell |
| **`ccm:oeh_quality_correctness`** | `4` | *(leer — nicht im Valuespace)* |
| `ccm:oeh_buffet_criteria` | `content_valid`, `speech_valid`, `usable_for_buffet` | Sachrichtigkeit, Sprachliche Verständlichkeit, *(leer)* |

Der Knoten trägt danach den Aspect `ccm:oeh` — edu-sharing setzt ihn beim
Schreiben selbst, es braucht dafür keinen Eintrag in `_ensure_aspects`.

### Binär

`ccm:oeh_quality_relevancy_for_education` — einfache Werte, keine URIs:

| Wert | Label |
|------|-------|
| `0` | Nein – ungeeignet |
| `1` | Ja – geeignet |

### K.O.-Kriterien

`ccm:oeh_quality_criminal_law`, `…_protection_of_minors`, `…_copyright_law`,
`…_personal_law`:

| Geschriebener Wert | Label im Repository | Alt-Wert (Zahl) |
|--------------------|---------------------|-----------------|
| `http://w3id.org/openeduhub/vocabs/quality/no_auto_findings` | keine Auffälligkeiten gefunden (Maschine) | `2` |
| `http://w3id.org/openeduhub/vocabs/quality/auto_findings` | Auffälligkeiten gefunden (Maschine) | `1` |

Die Maschinen-Varianten sind bewusst die einzigen, die die KI setzen kann — die
Mensch-Varianten (`human_findings` / `no_human_findings`, Alt-Werte `0` / `3`)
bleiben der Redaktion vorbehalten.

> **Achtung bei Alt-Daten:** Die frühere Skala war `0 = Nein – unauffällig`,
> `1 = Ja – auffällig`. Im aktuellen Valuespace ist `0` als Alt-ID dem Wert
> `human_findings` (= auffällig) zugeordnet — die Zahl `0` bedeutet heute also
> das Gegenteil von früher. Deshalb schreibt die API die URIs und keine Zahlen.

### 0–5-Skalen

`ccm:oeh_quality_data_privacy` — URIs `http://w3id.org/openeduhub/vocabs/quality_data_privacy/0…5`:

| Stufe | Label |
|-------|-------|
| 0 | heimlich unangemessen datensaugend |
| 1 | intransparent unangemessen viel datensaugend |
| 2 | intransparent Daten saugend |
| 3 | transparent unangemessen viel datensaugend |
| 4 | angemessen viele Daten mit Einverständnis |
| 5 | keinerlei Datenweitergabe |

`ccm:oeh_quality_neutralness` — URIs `http://w3id.org/openeduhub/vocabs/quality_neutrality/0…5`:

| Stufe | Label |
|-------|-------|
| 0 | manipulativ |
| 1 | unneutral |
| 2 | ideologisch eingefärbt, aber korrekter Inhalt |
| 3 | ideologisch eingefärbt, aber transparent |
| 4 | neutrale Formulierung |
| 5 | neutrale Formulierung, unabhängiger Ersteller |

`ccm:oeh_quality_didactics` — URIs `http://w3id.org/openeduhub/vocabs/quality_didactics/0…5`:

| Stufe | Label |
|-------|-------|
| 0 | Methodik unangemessen |
| 1 | Methodik ausreichend |
| 2 | angemessene Methodik |
| 3 | gute Methodik |
| 4 | moderne, gute Methodik |
| 5 | moderne, sehr gute Methodik |

`ccm:oeh_quality_medial` — URIs `http://w3id.org/openeduhub/vocabs/quality_media/0…5`:

| Stufe | Label |
|-------|-------|
| 0 | Medial unpassend |
| 1 | Medial schwierig |
| 2 | Medial ausreichend, aber suboptimal |
| 3 | Medial passend |
| 4 | Medial gut |
| 5 | Medial hervorragend |

`ccm:oeh_quality_transparentness` — URIs `http://w3id.org/openeduhub/vocabs/quality_transparency/0…5`:

| Stufe | Label |
|-------|-------|
| 0 | keine Angabe oder unseriös |
| 1 | Anbieter benannt, keine Kontaktangaben |
| 2 | Anbieter benannt, Kontaktangaben vorhanden |
| 3 | Anbieter benannt, umfangreiche Kontaktangaben |
| 4 | Anbieter bekannt, umfangreiche Kontaktangaben |
| 5 | renommierter Anbieter, korrekte Kontaktangaben |

### 0–5-Skalen ohne URI-Wertebereich

Für diese beiden Felder gibt es im MDS **kein** URI-Vokabular — die Werte sind
die blanken Zahlen `0`…`5`, genau wie in allen bisher kuratierten Nodes.

`ccm:oeh_quality_correctness` (Sachrichtigkeit):

| Wert | Label |
|------|-------|
| `0` | sachlich falsch |
| `1` | enthält Unkorrektheiten |
| `2` | sehr stark vereinfacht |
| `3` | stark vereinfacht |
| `4` | sachlich richtig, keine/wenige Belege angeführt |
| `5` | wissenschaftlich belegt |

> **Hinweis:** Der MDS-Valuespace für `ccm:oeh_quality_correctness` enthält
> aktuell nicht diese Skala, sondern die K.O.-Werte
> (`human_findings` / `auto_findings` / …). Die Zahlen `0`…`5` werden deshalb
> geschrieben wie bisher, lösen in der Redaktionsumgebung aber kein Label auf
> (`_DISPLAYNAME` bleibt leer) — dasselbe gilt bereits heute für alle
> kuratierten Bestands-Nodes mit diesem Feld.

`ccm:oeh_quality_currentness` (Aktualität) — MDS-konform:

| Wert | Label |
|------|-------|
| `0` | veralteter Inhalt |
| `1` | veraltet, aber teils noch relevant |
| `2` | veraltete Darstellung, inhaltlich noch aktuell |
| `3` | zeitlos aktuell |
| `4` | aktueller Wissensstand |
| `5` | hochaktuell/neuester Wissensstand |

### Mehrfachauswahl

`ccm:oeh_buffet_criteria` — einfache Werte, keine URIs, mehrere gleichzeitig:

| Wert | Label |
|------|-------|
| `content_valid` | Sachrichtigkeit |
| `speech_valid` | Sprachliche Verständlichkeit |
| `medial_relevant` | Medial passend |
| `didactics_valid` | Didaktik / Methodik gut |
| `accessible` | Barrierearmut |
| `usable_for_buffet` | Gesamturteil: für das Redaktionsbuffet geeignet |

`usable_for_buffet` steht nicht im MDS-Valuespace, kommt aber in den Live-Daten
des Repositories vor und wird von der KI nur gesetzt, wenn `content_valid`,
`speech_valid`, `medial_relevant` und `didactics_valid` gemeinsam erfüllt sind.

---

## Inhaltstyp-spezifische Schemata

### event.json

| Feld | Label |
|------|-------|
| `ccm:oeh_event_begin` | Start (Datum/Zeit) |
| `ccm:oeh_event_end` | Ende (Datum/Zeit) |
| `ccm:price` | Kosten |
| `ccm:oeh_competence_requirements` | Vorkenntnisse (Kompetenzen) |
| `ccm:competence` | Lernziele (Kompetenzen) |
| `ccm:oeh_competence_check` | Lernzielkontrolle (Kompetenzen) |
| `ccm:oeh_publisher_combined` | Publisher / Herausgeber |
| `ccm:educationalintendedenduserrole` | Zielgruppe |

### learning_material.json

| Feld | Label |
|------|-------|
| `ccm:educationaltypicalagerange_from` | Typisches Mindestalter (Jahre) |
| `ccm:educationaltypicalagerange_to` | Typisches Höchstalter (Jahre) |
| `ccm:oeh_competence_requirements` | Vorausgesetzte Kompetenzen |
| `ccm:competence` | Zu erwerbende Kompetenzen |
| `ccm:oeh_competence_check` | Überprüfte Kompetenzen |
| `ccm:price` | Kosten |
| `cm:author` | Autor:in / Urheber:in |
| `ccm:oeh_publisher_combined` | Publisher / Herausgeber |
| `ccm:custom_license` | Benutzerdefinierte Lizenz |
| `ccm:commonlicense_key` | Lizenztyp (CC) |
| `ccm:commonlicense_cc_version` | Lizenzversion |
| `ccm:fskRating` | FSK-Bewertung |

### didactic_planning_tools.json

| Feld | Label |
|------|-------|
| `ccm:oeh_competence_requirements` | Vorausgesetzte Kompetenzen |
| `ccm:competence` | Zu erwerbende Kompetenzen |
| `ccm:oeh_competence_check` | Überprüfte Kompetenzen |
| `ccm:educationaldifficulty` | Schwierigkeitsgrad |
| `dpf:duration` | Geschätzte Dauer |
| `cclom:typicallearningtime` | Zeitbedarf im Unterricht |
| `cm:author` | Autor:in / Urheber:in |
| `ccm:oeh_publisher_combined` | Publisher / Herausgeber |
| `ccm:custom_license` | Benutzerdefinierte Lizenz |
| `ccm:commonlicense_key` | Lizenztyp (CC) |
| `ccm:commonlicense_cc_version` | Lizenzversion |

### education_offer.json

| Feld | Label |
|------|-------|
| `ccm:oeh_competence_requirements` | Vorkenntnisse (Kompetenzen) |
| `ccm:competence` | Lernziele (Kompetenzen) |
| `ccm:oeh_competence_check` | Lernzielkontrolle (Kompetenzen) |
| `ccm:price` | Kosten |
| `ccm:oeh_publisher_combined` | Publisher / Herausgeber |

### tool_service.json

| Feld | Label |
|------|-------|
| `ccm:price` | Kosten |
| `ccm:oeh_publisher_combined` | Publisher / Herausgeber |
| `ccm:custom_license` | Benutzerdefinierte Lizenz |

### occupation.json

| Feld | Label |
|------|-------|
| `ccm:oeh_competence_requirements` | Erforderliche Kompetenzen |
| `ccm:competence` | Vermittelte Kompetenzen |
| `ccm:oeh_competence_check` | Nachgewiesene Kompetenzen |

### organization.json

| Feld | Label |
|------|-------|
| `ccm:price` | Kosten |

### person.json

Kein Feld mit `repo_field: true`.

---

## Felder ohne `repo_field`, die trotzdem geschrieben werden

Diese setzt der Upload-Pfad unabhängig vom Schema-Flag:

| Feld | Wann |
|------|------|
| `ccm:linktype` | Immer beim Anlegen (`USER_GENERATED`) |
| `ccm:oeh_extendedType` | `write_extended_data: true` — URI des Inhaltstyps |
| `ccm:oeh_extendedData` | `write_extended_data: true` — vollständiges Metadaten-JSON |
| `ccm:oeh_extendedText` | `write_extended_data: true` und `extended_text` gesetzt |
| `ccm:oeh_lrt` | Aus `ccm:oeh_extendedType` abgeleitet |
| `ccm:commonlicense_key` | `CUSTOM`, wenn `ccm:custom_license` nicht auf das Vokabular passt. Kein Fallback, wenn gar keine Lizenz erkannt wurde — das Feld bleibt leer |
| `ccm:commonlicense_cc_version` | Aus `ccm:custom_license` abgeleitet — bei CC-Links aus der URL, sonst `4.0` für CC-Keys ohne Version |
| `ccm:lifecyclecontributer_author` | Aus `cm:author` als VCARD |
| `cm:latitude` / `cm:longitude` | Aus `schema:location[].geo` bzw. `schema:geo` |

---

## Gesamtzahl

39 eindeutige Feld-IDs mit `repo_field: true` über alle Schemata — 22 davon in
`core.json` und damit für jeden Inhaltstyp aktiv.

Im MDS existiert darüber hinaus noch `ccm:oeh_quality_language` (Sprachlich,
0–5 als URIs unter `…/vocabs/quality_language/`) und `ccm:oeh_quality_login`
(Login notwendig, `0` / `1`). Beide sind bewusst noch nicht angelegt.
