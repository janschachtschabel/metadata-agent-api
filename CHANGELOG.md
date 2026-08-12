# Änderungen

Stand: 2026-08-12 · gegenüber Commit `52b008c` (CORS Fix)

Alles unten ist im Arbeitsbaum, noch nicht committet. Die Testsuite umfasst
**579 Tests**; `ruff check` und `ruff format --check` sind sauber.

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
  "repo_fields_available": 33,     // wie viele Felder überhaupt erlaubt waren
  "fields_written": 12
}
```

`metadataset` entscheidet, welches Typschema zusätzlich zu `core.json` gilt —
und damit, wie viele Felder geschrieben werden dürfen (core: 26,
+ `event.json`: 33, + `learning_material.json`: 40). Fehlt es, gibt es keinen
Fehler und keine Warnung. Diese beiden Felder machen den Unterschied sichtbar:

```
mit metadataset  : schema_used="event.json"  repo_fields_available=33
ohne metadataset : schema_used=null          repo_fields_available=26
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

> Der AcademicCloud-Default `deepseek-r1` antwortete auf Staging mit
> `404 Model Not Found`. Behoben in Punkt 13.

### 11. Sechs Felder erreichen das Repository, die vorher weggefiltert wurden

Ein redaktioneller Vergleichs-Upload von WLO-Seite schrieb Felder, die dieser
Agent nicht schrieb. Der Grund waren drei verschiedene Sperren, nicht eine:

| Feld | Sperre | jetzt |
|---|---|---|
| `oeh:new_lrt` | `repo_field: false` | `true` in `core.json` |
| `oeh:required_tools` | `repo_field: false` | `true` in `learning_material.json` |
| `schema:datePublished` | `repo_field: false` **und** Präfix-Filter | `true` + Filter präzisiert |
| `ccm:commonlicense_ai_allow_usage` | in keinem Schema definiert | neu in `core.json` |
| `ccm:commonlicense_ai_generated` | in keinem Schema definiert | neu in `core.json` |
| `ccm:commonlicense_ai_manually_modified` | in keinem Schema definiert | neu in `core.json` |

**Der Präfix-Filter.** `normalize_for_repo()` verwarf jeden Schlüssel mit dem
Präfix `virtual:` **oder** `schema:`, unabhängig vom Schema-Flag. Das war für
`schema:` zu grob: `schema:` ist ein regulärer Namensraum des Repositories, und
`schema:datePublished` wird von der Redaktion direkt geschrieben. Jetzt ist nur
noch `virtual:` unbedingt gesperrt — dahinter steht ein Wert, den edu-sharing
beim Lesen berechnet und nie speichert, für den es also keine sinnvolle
Schema-Einstellung gibt. Über alles andere entscheidet allein `repo_field`.

Das war gefahrlos, weil `repo_field` schon vorher die schärfere der beiden
Sperren war: kein einziges Feld mit `schema:`- oder `virtual:`-Präfix trug
`repo_field: true`, der Präfix-Filter war also faktisch wirkungslos. Die
Transformations-Eingaben `schema:location` und `schema:geo` stehen weiterhin auf
`repo_field: false` und gehen weiter über `cm:latitude`/`cm:longitude` ein — ein
Test wacht darüber, dass das so bleibt. Dieselbe Präzisierung in
`repository_diff.py`, damit `/upload/verify` `schema:datePublished` nicht
weiterhin als `not_written` meldet.

**Die drei KI-Felder** liegen in `core.json` und gelten damit für jeden
Inhaltstyp — eine Veranstaltung kann so gut KI-erzeugt sein wie ein
Arbeitsblatt. Sie sind `string` mit geschlossenem Vokabular `"true"`/`"false"`,
nicht `boolean`: das Repository bekommt `["false"]`, ein Python-`False` würde als
JSON-`false` serialisiert und wäre auf der Leitung ein anderer Wert. Im Canvas
sind sie sichtbar (`ask_user: true`), damit die Redaktion eine falsche
Einschätzung korrigieren kann. Die Prompts setzen einen Wert nur, wenn Text,
Impressum oder Lizenz es hergeben — aus Stil oder Qualität auf KI-Herkunft zu
schließen ist ausdrücklich untersagt.

Dabei fiel ein Fehler im Vokabular-Abgleich auf: `_validate_vocabulary()`
verglich den Wert **exakt** gegen die Konzept-Werte. Ein Modell, das nach
`'true'` oder `'false'` gefragt wird, antwortet aber etwa gleich oft mit einem
JSON-Boolean — und `str(True)` ist `'True'`, nicht `'true'`. Der Wert fiel
kommentarlos auf `None`. Der Abgleich läuft jetzt über die kleingeschriebene
String-Form, zurückgegeben wird weiterhin die Schreibweise aus dem Vokabular.
Kein Vokabular in den Schemata hat Werte, die sich nur in der Groß-/
Kleinschreibung unterscheiden — geprüft, bevor der Vergleich gelockert wurde.

> **Kosten:** drei zusätzliche Extraktions-Calls pro Upload, für jeden
> Inhaltstyp — ein Lernmaterial kommt damit auf 50 statt 47. Sie laufen im
> bestehenden Parallel-Fan-out mit.

`oeh:new_lrt` und `ccm:oeh_lrt` bleiben getrennt: `ccm:oeh_lrt` wird weiterhin
aus dem erkannten Inhaltstyp abgeleitet und mit den Extended Data geschrieben,
`oeh:new_lrt` trägt jetzt zusätzlich, was die Extraktion gefunden hat.

Damit stehen **45 eindeutige Feld-IDs** auf `repo_field: true`, 26 davon in
`core.json` (vorher 39 / 22). `repo_fields_available` in der Upload-Antwort
steigt entsprechend von 34 auf 40 für ein Lernmaterial.

> **Sammlungen** waren nie ein Filter-Problem: der ausgerollte Stand kennt den
> Parameter `collection_id` schlicht nicht (siehe Punkt 4). Ein Deploy behebt das.

**Am lebenden Repository nachgemessen** (2026-08-12, Staging, Knoten
`5443240c-43a2-4961-8324-0c43a22961dd`) — und das Ergebnis ist zur Hälfte
ernüchternd:

| Feld | geschrieben? |
|---|---|
| `ccm:commonlicense_ai_allow_usage` | ✅ |
| `ccm:commonlicense_ai_generated` | ✅ |
| `ccm:commonlicense_ai_manually_modified` | ✅ |
| `oeh:new_lrt` | ❌ verworfen |
| `oeh:required_tools` | ❌ verworfen |
| `schema:datePublished` | ❌ verworfen |

Alfresco quittiert den POST mit `200` und **verwirft Properties, die nicht im
Content-Modell stehen, ohne Rückmeldung**. Weder Statuscode noch
`fields_written` zeigen das an — die einzige Möglichkeit, es zu bemerken, ist
Zurücklesen. Von 100 gelesenen Bestandsknoten trägt kein einziger eines der drei
Felder; `ccm:oeh_lrt` dagegen 91.

Der Lernressourcentyp geht dadurch **nicht** verloren: `ccm:oeh_lrt` wird
weiterhin aus dem erkannten Inhaltstyp abgeleitet und über den
Extended-Data-Pfad geschrieben. Verloren geht der von der KI aus dem Vokabular
extrahierte Wert.

Die drei Flags bleiben auf `true` — das Senden kostet nichts und wirkt ohne
Codeänderung, sobald WLO die Properties anlegt. `WLO-REPO-FELDER.md` führt sie
mit ⚠️ und ist damit zugleich die Liste, die es dafür braucht.

### 12. Durchsatzgrenzen des LLM-Gateways sind einstellbar (neu)

Zwei neue Einstellungen, beide prozessweit wirksam:

```env
METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS=   # leer = gemessener Default
METADATA_AGENT_LLM_MAX_REQUESTS_PER_SECOND=   # leer = gemessener Default, 0 = aus
```

| Provider-Gruppe | gleichzeitig | pro Sekunde |
|---|---:|---:|
| `b-api` (beide B-API-Provider) | **2** | **2** |
| `openai` (nativ) | 10 | keine Grenze |

Die Rate ist **pro Sekunde**, nicht pro Minute: `2` sind 120 Aufrufe/Minute.

Gegen das laufende Vercel-Deployment gemessen — Erschließung mit 50 Feldern:

| Provider / Modell | Dauer |
|---|---|
| `b-api-openai` / `gpt-5.6-luna` | 25,2 s |
| `b-api-academiccloud` / `deepseek-v4-flash` | 32,4 s · 89,6 s |
| `b-api-academiccloud` / `openai-gpt-oss-120b` | 53,1 s |

Die Streuung kommt von der Warteschlange am Gateway, nicht vom Modell.
`vercel.json` deklariert `maxDuration: 60`, der 89,6-Sekunden-Lauf kam trotzdem
mit `200` zurück — die Grenze wird auf diesem Deployment offenbar nicht
durchgesetzt.

**Warum das nötig war.** Die B-API erlaubt exakt zwei Requests gleichzeitig und
etwa zwei pro Sekunde. Das Budget hängt am **Key am Gateway**, nicht am Modell —
`b-api-openai` und `b-api-academiccloud` teilen es sich deshalb. Ein dritter
paralleler Request wird sofort mit `429` abgewiesen, **ohne `retry-after`**: ein
Client kann die Wartezeit nicht ablesen, er muss unter der Grenze bleiben. Mehr
Last hilft nicht, sie schadet — bei 3 req/s fällt der effektive Durchsatz unter
den Wert bei 2 req/s. Der Agent lief mit `DEFAULT_MAX_WORKERS=10` um Faktor 5
darüber, die meisten Feld-Extraktionen landeten im Retry.

**Wo die Grenze sitzt.** In `_call_llm` — dem einzigen Punkt, durch den *jeder*
LLM-Request läuft, auch die Inhaltstyp-Erkennung und die Normalisierung, die
nicht über den parallelen Feld-Fan-out gehen. Ein Retry ist ein eigener Request
und nimmt einen Platz.

Das Semaphore ist **prozessweit**, nicht pro Service-Objekt: `get_llm_service()`
erzeugt bei Provider- oder Modell-Override eine neue `LLMService`-Instanz, ein
instanzgebundenes Limit hätte bei zwei gleichzeitigen API-Requests also die
doppelte Zahl durchgelassen. Ein Test hält das fest.

`DEFAULT_MAX_WORKERS` wird auf die Grenze gedeckelt und das beim Start
ausgewiesen, statt eine Parallelität zu versprechen, die nicht stattfindet:

```
Default Workers: 10 → 2 (limit of b-api)
LLM Throughput: max 2 in flight, max 2 req/s
```

### 13. AcademicCloud-Default ist ein Modell, das es gibt

`deepseek-r1` → **`openai-gpt-oss-120b`**. Der alte Default antwortete mit
`404 Model Not Found`; ein Default, der nicht funktionieren kann, ist schlechter
als keiner, weil nichts am Fehler auf die Einstellung zeigt. Das neue Modell
lieferte in der Messung vom 12.08.2026 die gleichmäßigste Latenz der
AcademicCloud-Modelle (4,99 s ± 2,31 s bei der Extraktion, p95 6,59 s im Chat).

### 14. Nativ OpenAI zieht mit der B-API-Implementierung gleich

- **`METADATA_AGENT_OPENAI_API_BASE`** muss nicht auf OpenAI zeigen. Jeder
  Endpunkt, der `/chat/completions` bedient und einen Bearer-Token annimmt,
  funktioniert — Azure, selbst gehostetes vLLM, ein Gateway davor. Die
  Einstellung gab es schon, dokumentiert war sie nicht.
- **`METADATA_AGENT_OPENAI_TEMPERATURE`** folgt jetzt standardmäßig
  `METADATA_AGENT_LLM_TEMPERATURE`. Vorher ignorierte genau einer von drei
  Providern die gemeinsame Einstellung — eine Falle, kein Feature. Wer den
  eigenen Wert schon setzt, behält ihn.
- Die Durchsatzgrenzen gelten für alle drei Provider, nur mit anderen Defaults.

Was schon vorher providerunabhängig war und es bleibt: die Erkennung der
Reasoning-Modelle (`gpt-5`, `o1`, `o3`, `o4` → `max_completion_tokens`, kein
`temperature`, dafür `verbosity` und `reasoning_effort`) greift bei nativem
OpenAI genauso wie über die B-API.

### 15. `ENV-PARAMETER.md` — vollständige Referenz (neu)

Alle 43 Umgebungsvariablen an einer Stelle, mit Defaults und Betriebsbeispielen.
`README.md`, `INSTALL.md` und `DEPLOYMENT.md` verweisen darauf, statt jeweils
eine eigene, unvollständige Teilliste zu führen.

Zwei Tests halten das Dokument ehrlich: eine Einstellung im Code ohne Eintrag
lässt den Test fehlschlagen, und ein dokumentierter Name, den `Settings` nicht
mehr liest, ebenfalls — letzteres ist der unangenehmere Fall, weil das Setzen
dann so aussieht, als wirke es.

### 16. Der Lernressourcentyp kommt an — im richtigen Feld, aus dem vollen Vokabular

Zwei Fehler, die sich gegenseitig verdeckten.

**Falsches Zielfeld.** Das Schema nennt das Feld `oeh:new_lrt`, und genau so
wurde es geschrieben. Diese Property gibt es im Content-Modell aber nicht — der
POST kam mit `200` zurück, der Wert war weg. Was das Repository führt, ist
**`ccm:oeh_lrt`** (91 von 100 gelesenen Knoten, 124 Werte, alle aus
`…/vocabs/new_lrt/`). Der Upload benennt das Feld beim Schreiben jetzt um, wie
er es bei `cm:author` → `ccm:lifecyclecontributer_author` schon tut. **Die
`/generate`-Antwort bleibt unverändert** — dort heißt das Feld weiter
`oeh:new_lrt`, am Vertrag ändert sich nichts.

**Halbes Vokabular.** Im Schema standen **87** Konzepte, veröffentlicht sind
**220**. Die 87 waren eine saubere Teilmenge — keine veralteten Einträge, keine
abweichenden Labels — es fehlten schlicht 133, darunter „Quelle", „Portal",
„Datenbank" und „Lexikon oder Enzyklopädie". Das Vokabular ist geschlossen, ein
fehlendes Konzept ist also ein Wert, den die Extraktion nie liefern kann. Jetzt
vollständig, mit Snapshot unter `src/schemata/vocabs/new_lrt.json`.

> `new_lrt_aggregated` (48 Konzepte) ist **nicht** das richtige Vokabular:
> kein einziger der 124 gelesenen Werte stammt daraus.

**Die Kollision, die dabei auffiel.** Der Upload schreibt `ccm:oeh_lrt` ein
zweites Mal — aus dem erkannten Inhaltstyp abgeleitet, sechs grobe Typen
(`learning_material` → „Material"). Dieser Schritt läuft **nach** dem
Metadaten-Schreiben und hätte den genaueren extrahierten Wert ersetzt. Er greift
jetzt nur noch, wenn die Extraktion nichts gefunden hat.

**Am lebenden Repository nachgewiesen.** Dieselbe Seite, zweimal hochgeladen:

| | `ccm:oeh_lrt` |
|---|---|
| vorher (`5443240c-…`) | `…/1846d876-…` → **„Material"** (abgeleitet) |
| jetzt (`5d648bba-…`) | `…/9f40cd56-…` → **„Lexikon oder Enzyklopädie"** (extrahiert) |

Das Konzept „Lexikon oder Enzyklopädie" war eines der 133 fehlenden — ohne beide
Korrekturen zusammen wäre es nicht möglich gewesen.

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

579 Tests (vorher keine). Abdeckung der Service-Schicht:

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
