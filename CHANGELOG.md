# Änderungen

Stand: 2026-08-11 · gegenüber Commit `52b008c` (CORS Fix)

Alles unten ist im Arbeitsbaum, noch nicht committet. Die Testsuite umfasst
**452 Tests**; `ruff check` und `ruff format --check` sind sauber.

---

## Was sich für Aufrufer ändert

### 1. Lizenz: kein `COPYRIGHT_FREE` mehr, wenn keine erkannt wurde

**Vorher:** Fand die Extraktion keine Lizenz, schrieb der Upload
`ccm:commonlicense_key: ["COPYRIGHT_FREE"]`.
**Jetzt:** Das Feld bleibt leer.

`COPYRIGHT_FREE` heißt im WLO-Vokabular wörtlich *„Urheberrechtsfrei"*. Der
Extraktions-Prompt liefert bei fehlender CC-Lizenz `null` — daraus eine positive
Rechtsaussage zu machen, veröffentlichte über fremdes Material eine Behauptung,
die niemand geprüft hatte. Die Entscheidung trifft jetzt die Redaktion im
Prüf-Workflow, den der Upload ohnehin startet.

> **Sichtbar in der Redaktion:** Neu hochgeladene Inhalte ohne erkennbare Lizenz
> haben ein leeres Lizenzfeld statt „Urheberrechtsfrei".

### 2. Lizenz: nicht zuordenbare Angaben gehen nicht mehr verloren

**Vorher:** Jeder `ccm:custom_license`-Wert mit einem `/` galt als
Vokabular-URI. Passte das letzte Pfadsegment auf keinen bekannten Schlüssel,
wurde der Wert **gelöscht** und anschließend durch `COPYRIGHT_FREE` ersetzt.

Das Schema definiert `ccm:custom_license` als Freitext und sein Prompt fordert
dort ausdrücklich URLs an — die eigene Extraktion erzeugte also genau die
Eingabe, die den Verlust auslöste:

| Eingabe | vorher | jetzt |
|---|---|---|
| `https://example.com/nutzungsbedingungen` | gelöscht → `COPYRIGHT_FREE` | `CUSTOM`, Text bleibt |
| `Nur für Bildungszwecke / nicht kommerziell` | gelöscht → `COPYRIGHT_FREE` | `CUSTOM`, Text bleibt |
| `© 2024 Uni München` | `CUSTOM`, Text bleibt | unverändert |

### 3. Lizenz: `creativecommons.org`-Links werden abgebildet (neu)

```
https://creativecommons.org/licenses/by-sa/4.0/      → CC_BY_SA + 4.0
https://creativecommons.org/licenses/by-nc-sa/3.0/de/ → CC_BY_NC_SA + 3.0
https://creativecommons.org/publicdomain/zero/1.0/   → CC_0 + 1.0
https://creativecommons.org/publicdomain/mark/1.0/   → PDM (ohne Version)
```

Die Version kommt **aus der URL**, nicht aus einem Default; ein Länderkürzel
(`/3.0/de/`) wird nicht mitgelesen. Ein unbekannter Code (`by-xx`) wird nicht
geraten, sondern bleibt Text mit `CUSTOM`. Steht der Link **innerhalb** eines
Satzes, wird der Schlüssel gesetzt **und** der Text behalten — der Satz kann
mehr sagen als die Lizenz.

Die Schreibweise (`CC_BY_SA`, Unterstriche) ist gegen das Live-Repository
geprüft: WLO speichert genau diese Form.

### 4. `collection_id` ist immer ein Array

```jsonc
{ "collection_id": ["3039bdb2-…"] }   // ✅
{ "collection_id": "3039bdb2-…" }     // ❌ 422
{ "collection_id": [] }               // ✅ wie weglassen
```

`workflow_steps` und `workflow_receiver` nehmen ebenfalls ausschließlich Listen.
Ein Feld, das beide Formen schluckt, machte das Anfrageformat davon abhängig,
welchen Parameter man gerade füllt. Als Einträge werden weiterhin IDs **und**
kopierte Sammlungs-URLs akzeptiert.

*Kein Bruch für bestehende Clients — der Parameter war nie ausgeliefert.*

### 5. Body-Format: alle drei Formen sind jetzt gleichwertig

Betrifft **`/upload`, `/validate` und `/export/markdown`**.

`/generate` liefert die Schema-Marker (`contextName`, `schemaVersion`,
`metadataset`) *neben* `metadata`, alle Verbraucher suchten sie *darin*. Wer die
Antwort unverändert weiterreichte — der von der Doku empfohlene Weg — verlor
sie:

| Endpoint | vorher bei unveränderter `/generate`-Antwort |
|---|---|
| `/upload` | nur `core.json` → bei einer Veranstaltung fielen `ccm:oeh_event_begin`, `ccm:oeh_event_end`, `ccm:price`, `ccm:competence` weg |
| `/validate` | prüfte gegen `learning_material.json` statt `event.json` |
| `/export/markdown` | `schema_used: "auto"` — keine Erkennung |

Jetzt liefern alle drei Formen dasselbe Ergebnis. **Empfohlen ist die
`/generate`-Antwort unverändert** — sie kommt flach, Umschlag und Felder auf
einer Ebene:

```jsonc
// 1) Felder unter metadata                   2) EMPFOHLEN: flach (= /generate)
{ "contextName": "…", "metadataset": "…",    { "contextName": "…",
  "metadata": { "cclom:title": "…" } }         "metadataset": "…",
                                               "cclom:title": "…" }
// 3) alles unter metadata (Webkomponente)
{ "metadata": { "contextName": "…", "metadataset": "…",
                "metadata": { "cclom:title": "…" } } }
```

### 6. Die Antwort sagt, gegen welches Schema geschrieben wurde (neu)

```jsonc
{
  "success": true,
  "schema_used": "event.json",     // null = nur core.json
  "repo_fields_available": 29,     // wie viele Felder überhaupt erlaubt waren
  "fields_written": 12
}
```

`metadataset` entscheidet, welches Typschema zusätzlich zu `core.json` gilt —
und damit, wie viele Felder geschrieben werden dürfen (core: 22,
+ `event.json`: 29, + `learning_material.json`: 34). Fehlt es, gibt es keinen
Fehler und keine Warnung. Diese beiden Felder machen den Unterschied sichtbar:

```
mit metadataset  : schema_used="event.json"  repo_fields_available=29
ohne metadataset : schema_used=null          repo_fields_available=22
```

Der Name `schema_used` ist derselbe wie bei `/validate` und `/export/markdown`.

### 7. `workflow_steps`: leere Liste wird abgelehnt

`[]` liest sich wie „keine Schritte", hätte aber beim Weglassen auf den Standard
`200_tocheck` zurückgefallen — das Gegenteil. Jetzt `422`. Für einen Upload ohne
Workflow: `start_workflow: false`. Unbekannte Status geben ebenfalls `422`,
bevor etwas ins Repository geht.

### 8. `discarded_node` in der Antwort (neu)

Bricht ein Upload ab, nachdem der Node schon angelegt war, wird er
zurückgenommen (Papierkorb, wiederherstellbar) und seine ID steht in
`discarded_node`. Scheitert auch die Rücknahme, bleibt das Feld gesetzt — dann
existiert der Node und muss von Hand weg.

### 9. Autoren-VCARD folgt dem Repository-Format

```
vorher:  BEGIN:VCARD\nFN:Max Müller\nN:Müller;Max\nVERSION:3.0\nEND:VCARD
jetzt:   BEGIN:VCARD\nVERSION:3.0\nFN:Max Müller\nN:Müller;Max;;;\nEND:VCARD
```

Gegen einen echten WLO-Knoten abgeglichen: `VERSION` steht direkt nach `BEGIN`,
`N` hat fünf positionelle Komponenten. edu-sharing zerlegt `N` daraus nach
`ccm:lifecyclecontributer_authorVCARD_SURNAME` / `_GIVENNAME`.

Zusätzlich: Zeilenumbrüche im Namen werden zu Leerzeichen (eine präparierte
Quellseite konnte sonst eigene VCARD-Eigenschaften in die Node-Metadaten
schreiben), `;` und `,` werden in den `N`-Komponenten escaped. `FN` bleibt
bewusst unescaped — dort schützt der Escape nichts und würde als Backslash im
angezeigten Namen landen.

---

### 10. Standard-LLM ist `gpt-5.6-luna`

Vorher `gpt-4.1-mini`. Das neue Modell ist ein Reasoning-Modell der Nano-Klasse
und nimmt einen anderen Request-Body — beides gegen die B-API gemessen:

| Parameter | gpt-5.6-luna |
|---|---|
| `max_tokens` | **400** — „use `max_completion_tokens` instead" |
| `temperature: 0.3` | **400** — nur der Default (1) ist erlaubt |
| `verbosity`, `reasoning_effort` | ✅ (bei `gpt-4.1-mini` beide **400**) |
| `response_format: json_object` | ✅ |

`llm_service` schaltet deshalb per Modell-Präfix (`gpt-5`, `o1`, `o3`, `o4`):
Reasoning-Modelle bekommen `max_completion_tokens` ohne `temperature`, alle
anderen behalten **unverändert** ihren bisherigen Body.

Neue Einstellungen `METADATA_AGENT_LLM_VERBOSITY` und
`METADATA_AGENT_LLM_REASONING_EFFORT`, beide `low`. Leer = Parameter nicht
senden. `reasoning_effort` erlaubt `none`/`low`/`medium`/`high`; `minimal` wird
abgelehnt.

**Warum `low` und nicht `none`:** `none` ist rund 40 % schneller (6,9–8,9 s statt
9,6–15,3 s) und braucht halb so viele Output-Token — verlor aber in 2 von 5
Läufen `ccm:oeh_event_begin` und destabilisierte einmal die Inhaltstyp-Erkennung.
`low` traf in sieben Läufen jedes Mal 8 von 9 Sollfeldern.

> **Bekannt:** Der AcademicCloud-Default `deepseek-r1` antwortet auf Staging mit
> `404 Model Not Found` — unabhängig von dieser Änderung, aber der Provider
> `b-api-academiccloud` ist damit unbrauchbar.

## Konfiguration

### `WLO_REPOSITORY_BASE_URL` entfernt

Die Variable war in `DEPLOYMENT.md` und `INSTALL.md` als Repository-Override
dokumentiert und wurde **von niemandem gelesen** — auch vor dem Refactor nicht.
Wer sie in Produktion setzte, bekam keinen Fehler und schrieb weiter nach
Staging.

Das Ziel-Repository wird ausschließlich über
**`METADATA_AGENT_REPOSITORY_URL`** gesetzt. Bestehende `.env`-Dateien mit der
alten Variable brechen nicht (`extra: "ignore"`).

### UTF-8-Ausgabe unter Windows

Die Fortschrittsausgabe enthält Emoji. Auf einer cp1252-Konsole brach ein Upload
damit mitten im Schreiben mit `UnicodeEncodeError` ab — ausgelöst schon von einem
Autorennamen wie „Philipp Lang". `src/__init__.py` stellt `stdout`/`stderr` beim
Import auf UTF-8. Unter Linux, Docker und Vercel ändert das nichts.

---

## Intern

- **Neue Module** aus `repository_service.py` herausgelöst — reine Umzüge,
  Verhalten unverändert: `repository_values.py` (Feld-Filter, Flattening,
  Autoren, Koordinaten), `repository_licenses.py` (Lizenz-Erkennung),
  `repository_diff.py` (SOLL/IST-Vergleich), `repository_curation.py`
  (Sammlungen, Workflow).
- **`carry_schema_markers()`** in `main.py` — ein Helfer für die drei Endpoints,
  die den Body auf dieselbe Weise entgegennehmen.
- **Diff-Bericht:** Kann kein Schema geladen werden, meldet `/upload/verify` die
  Felder als `not_written` statt `missing_in_repo`. Der Schreibpfad verweigert
  in diesem Fall jeden Schreibvorgang — die Felder fehlen also *durch
  Entscheidung*, nicht weil das Repository sie verloren hätte.
- **Rücknahme-Timeout** auf 5 s begrenzt: Die Rücknahme läuft, nachdem der
  Upload sein Budget schon verbraucht hat, innerhalb einer auf 60 s gedeckelten
  Serverless-Invocation.

### Tests und Abdeckung

452 Tests (vorher keine). Abdeckung der Service-Schicht:

| Modul | Abdeckung |
|---|---|
| `repository_values.py` | 95 % |
| `repository_licenses.py` | 95 % |
| `repository_diff.py` | 95 % |
| `repository_curation.py` | 81 % |
| `repository_service.py` | 77 % |

---

## Was noch offen ist

- **Nichts davon lief gegen ein echtes Repository.** Alle Tests arbeiten gegen
  einen aufgezeichneten HTTP-Client. Gegen die Live-Instanz wurde nur *gelesen*
  (Lizenzvokabular, gespeicherte Knoten, MDS). Ein Test-Upload nach Staging vor
  dem Deploy klärt in einem Durchgang: leeres Lizenzfeld, VCARD-Zerlegung,
  Sammlungen, Workflow-Schritte.
- **Ob edu-sharing RFC-6350-Escapes auflöst,** ist ungeprüft — auf Staging gibt
  es keinen Knoten mit `;` oder `,` im Autorennamen. Folgenlos, seit `FN` nicht
  mehr escaped wird.
- **`repository_service.py`** steht bei 1062 Zeilen und 77 % Abdeckung. Die
  Dublettenerkennung — sie entscheidet, ob ein Upload überhaupt stattfindet —
  ist ungetestet. Ein Modulschnitt ist sinnvoll, aber erst ab höherer Abdeckung
  verantwortbar.
- **`contextName`/`schemaVersion`/`metadataset`** sind keine deklarierten
  Request-Felder, sondern werden aus den Metadaten gelesen. `carry_schema_markers()`
  vereinheitlicht das Verhalten; im OpenAPI-Vertrag steht es nicht.
