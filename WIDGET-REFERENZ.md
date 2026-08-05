# `<metadata-agent-canvas>` — Kompaktreferenz

Stand: verifiziert gegen `src/static/widget/dist/main.js` (Build vom 20.03.) und `src/main.py`.

---

## 1. Einbindung

```html
<!-- MUSS vor den Scripts stehen (i18n + Schema laden vor dem ersten @Input-Zyklus) -->
<script>window.__ENV = { agentUrl: 'https://API-URL' };</script>

<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/icon?family=Material+Icons|Material+Icons+Outlined" rel="stylesheet">

<link rel="stylesheet" href="https://API-URL/widget/dist/styles.css">
<script src="https://API-URL/widget/dist/runtime.js" defer></script>
<script src="https://API-URL/widget/dist/polyfills.js" defer></script>
<script src="https://API-URL/widget/dist/main.js" defer></script>

<metadata-agent-canvas api-url="https://API-URL" layout="default"></metadata-agent-canvas>
```

Priorität der API-URL: `api-url`-Attribut > `window.__ENV.agentUrl` > Build-`environment.apiUrl`.

Alle Attribute sind Angular-Element-Inputs — kebab-case im HTML, camelCase per JS (`el.showSaveButton = true`).

---

## 2. Layouts (Ansichten)

7 echte Layouts. Jedes bringt eigene Defaults mit; `show-*`-Attribute überschreiben sie einzeln.

| Layout | Input | Statusbar | Content-Type | Footer | JSON-Loader | Save | Upload | Field-Actions | Spalten | borderless | readonly |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `default` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 1 | – | – |
| `plugin` | ✅ | ✅ | ✅ | – | – | ✅ | ✅ | ✅ | 1 | ✅ | – |
| `dialog` | – | – | – | – | – | ✅ | – | ✅ | 1 | ✅ | – |
| `detail` | – | – | – | – | – | – | – | – | **4** | ✅ | **✅** |
| `clean` | – | – | ✅ | – | – | – | – | ✅ | 1 | ✅ | – |
| `prueftisch` | – | – | ✅ | – | – | – | – | ✅ | 1 | ✅ | – |
| `prueftisch-org` | – | – | ✅ | – | – | – | – | – | 1 | ✅ | **✅** |

Floating Controls, Reset-Button und Sprachumschalter sind in **allen** Layouts an.

### Aliase (`layout="…"`)

| Ziel | Aliase |
|---|---|
| `default` | `standalone`, `local`, `normal`, `edit`, `bookmarklet`, `webcomponent`, `embed`, `embedded`, `viewer`, `view`, `readonly` |
| `plugin` | `browser-extension`, `extension`, `sidebar` |
| `dialog` | `modal`, `review`, `redaktion` |
| `detail` | `preview`, `print` |
| `clean` | `metadatenpruefdialog`, `pruefung`, `validation`, `check` |
| `prueftisch` | `reviewtable`, `table`, `qa`, `prueftisch-gross`, `prueftisch-large`, `reviewtable-large`, `qa-large` |
| `prueftisch-org` | `reviewtable-org`, `qa-org`, `prueftisch-org-large`, `reviewtable-org-large`, `qa-org-large` |

> ⚠️ **Abweichung zur README:** Die `-gross`/`-large`-Aliase setzen **keine** 2 Spalten. `getLayout()` löst nur den Namen auf. Für 2 Spalten zusätzlich `columns="2"` setzen.
> ⚠️ `layout="readonly"` ist ein Alias auf `default` — schaltet **nicht** readonly. Dafür `readonly="true"`.

---

## 3. Alle Attribute (vollständige Input-Liste, 40 Stück)

### Konfiguration

| Attribut | Werte | Default | Wirkung |
|---|---|---|---|
| `api-url` | URL | – | API-Basis. Setzt zusätzlich i18n-Reload. **Pflicht** (oder `window.__ENV`) |
| `layout` | s. o. | `default` | Layout inkl. Alias-Auflösung |
| `context-name` | `default`, `mds_oeh` | `default` | Schema-Kontext |
| `schema-version` | `1.8.1`, `latest` | `latest` | Schema-Version |
| `columns` | `1`–`4` | Layout-Default | Wird geparst, außerhalb 1–4 ignoriert |
| `background-color` | CSS-Farbe | `""` | Hintergrund |
| `input-mode` | `text`, `url`, `nodeId` | `text` | Aktiver Eingabemodus |
| `instance-id` | String | `default` | Multi-Instanz-Bindung |
| `debug` | `true`/`false` | `false` | Konsolen-Logging (global, nicht pro Instanz) |

### Sichtbarkeit

Zwei Coercion-Klassen — das ist der häufigste Stolperstein:

**Opt-in** (`undefined` → Layout-Default; **nur** `true`/`"true"` schaltet an, alles andere aus):
`show-input-area`, `show-status-bar`, `show-footer`, `show-floating-controls`, `controls` (Alias), `show-upload-button`, `show-save-button`, `show-json-loader`, `show-language-switcher`, `show-content-type`, `show-reset-button`, `show-page-mode`, `show-content-type-only`

**Opt-out** (`undefined` → Layout-Default; **nur** `false`/`"false"` schaltet aus):
`show-core-fields`, `show-special-fields`, `show-field-actions`, `show-preview` (Default `true`)

| Attribut | Was |
|---|---|
| `show-input-area` | Eingabebereich (Text/URL/NodeId-Umschalter + Extract-Button) |
| `show-status-bar` | Fortschritt / Feldzähler |
| `show-core-fields` | Kernfelder (Titel, Beschreibung, Keywords …) |
| `show-special-fields` | Schema-abhängige Spezialfelder |
| `show-footer` | Fußzeile |
| `show-floating-controls` | Container der schwebenden Buttons |
| `show-field-actions` | Buttons pro Feld (Status, Info, Geo, Copy) |
| `show-upload-button` | Upload ins Repository |
| `show-save-button` | JSON-Download |
| `show-json-loader` | JSON-Import |
| `show-language-switcher` | de/en |
| `show-content-type` | Content-Type-Selector |
| `show-reset-button` | Reset in den Floating Controls |
| `show-page-mode` | „Seite neu laden" (Plugin-Modus, feuert `reloadFromPage`) |
| `show-content-type-only` | Nur Content-Type-Selector in den Controls |
| `show-preview` | Vorschaubild |

### Verhalten

| Attribut | Coercion | Wirkung |
|---|---|---|
| `readonly` | opt-in | Nur-Lesen |
| `viewer-mode` | opt-in | Alias für `readonly` |
| `borderless` | opt-in | Rahmenlos |
| `flat-groups` | opt-out | Feldgruppen pro Schema zusammenfassen |
| `highlight-ai` | opt-out (Default `false`) | KI-Felder farblich markieren |
| `enable-screenshot` | opt-out | Screenshot bei URL-Extraktion |
| `screenshot-method` | `pageshot` \| `playwright` | andere Werte werden ignoriert |
| `auto-extract` | truthy (nicht `false`/`0`) | löst sofort Extraktion aus |
| `force-reset` | truthy | Reset **ohne** Bestätigungsdialog, leert Text/URL/NodeId |

### Daten setzen

| Attribut | Typ | Hinweis |
|---|---|---|
| `text` | String | Füllt das Textfeld |
| `url` | String | Füllt das URL-Feld |
| `content-type` | Schema-Datei (`event.json`) **oder** Vokabular-URI | wird gepuffert, bis Content-Types geladen sind |
| `metadata-input` | Objekt | **Nur per JS** (`el.metadataInput = {...}`), löst Import via `ngOnChanges` aus |
| `preview-image` | Data-URL oder URL | Vorschaubild |

---

## 4. Events

Genau **vier** Custom Events sind im Build vorhanden:

```js
const canvas = document.querySelector('metadata-agent-canvas');

canvas.addEventListener('metadataChange', e => {/* debounced 50 ms nach jeder State-Änderung */});
canvas.addEventListener('metadataSubmit', e => {/* Submit/Save geklickt */});
canvas.addEventListener('uploadResult',  e => {/* nach /upload */});
canvas.addEventListener('reloadFromPage', () => {/* "Seite neu laden", Plugin-Modus */});
```

> ⚠️ `GET /widget/info` nennt zusätzlich `extractionComplete` und `contentTypeDetected` — **die existieren im aktuellen Build nicht.**

### Payload `metadataChange` / `metadataSubmit`

```jsonc
{
  "contextName": "default",
  "schemaVersion": "1.8.1",
  "metadataset": "event.json",
  "metadataset_uri": "http://w3id.org/openeduhub/vocabs/contentTypes/event",
  "language": "de",
  "exportedAt": "2026-08-04T10:00:00.000Z",
  "metadata": { "cclom:title": "…", "ccm:wwwurl": "…" },
  "_origins": { "cclom:title": "ai", "ccm:wwwurl": "user" },  // Herkunft je gefülltem Feld
  "_source_text": "…",          // nur wenn Text-Eingabe vorhanden
  "preview_image_url": "…"      // nur wenn Vorschaubild vorhanden
}
```

Dieselbe Struktur wird von `metadata-input` und vom JSON-Import akzeptiert (ein nacktes `{ "cclom:title": … }` geht auch).

### Payload `uploadResult`

```jsonc
{ "success": true, "nodeId": "…", "repositoryUrl": "…", "error": null, "duplicate": false }
```

### Eingehendes Event: `plugin-extract`

Der einzige programmatische Trigger von außen:

```js
canvas.dispatchEvent(new CustomEvent('plugin-extract', {
  detail: { text: '…', url: '…', inputMode: 'url', reset: true }
}));
```
Setzt (optional Reset), übernimmt `text`/`url`/`inputMode` und startet die Extraktion. **`nodeId` wird hier nicht ausgewertet.**

### Multi-Instanz

Gleiche `instance-id` → geteilter State. Events feuern nur von der **ersten registrierten** Instanz (`_isPrimary`), also genau einmal. Verschiedene IDs → isolierte States und eigene Events. Laufzeitwechsel: `el.instanceId = 'x'`.

---

## 5. Bestandsinhalte via Node-ID — was geht, was nicht

| Schritt | Widget | API |
|---|---|---|
| **Lesen** (Metadaten + Volltext aus Node) | ✅ `input-mode="nodeId"`, Node-ID **manuell ins Feld tippen** | ✅ `POST /generate` mit `input_source: "node_id"` |
| **Ändern** (im Canvas editieren) | ✅ | ✅ (`existing_metadata`) |
| **Zurückspeichern in denselben Node** | ❌ | ❌ |

**Details:**

- **Lesen:** `startNodeIdExtraction()` ruft `POST /generate` mit `input_source: "node_id"`, `node_id`, `include_core: true`, `enable_geocoding: true`, `normalize: true` und — falls schon Felder gefüllt sind — `existing_metadata`. Serverseitig holt `InputSourceService` `…/node/v1/nodes/-home-/{id}/metadata` + `…/textContent`. `input_source: "node_url"` nimmt zusätzlich die `ccm:wwwurl` als Crawler-Fallback, wenn kein Volltext hinterlegt ist.
- **Kein `node-id`-Attribut.** Die Input-Liste des Custom Elements enthält `text`, `url`, `inputMode` — aber **kein** `nodeId`. `GET /widget/info` dokumentiert `node-id` und `source-url`; beide existieren als Element-Attribute nicht. Node-ID ist derzeit nur über das UI-Eingabefeld setzbar.
- **Speichern:** `POST /upload` legt **immer einen neuen Node** im konfigurierten Inbox-Ordner an (`_create_node` → `_ensure_aspects` → `_set_metadata` → Collections → Extended Data → Workflow). Es gibt keinen Endpunkt, der einen vorhandenen Node aktualisiert.
- **Duplikatlogik:** `check_duplicates: true` sucht per `ccm:wwwurl`. Bei Treffer bricht der Upload ab (`duplicate: true` + vorhandene `nodeId`). Der Widget-Dialog bietet dann „trotzdem hochladen" — das erzeugt einen **zweiten Node**, kein Update.
- **Gegenprüfen:** `POST /upload/verify/{node_id}` — ohne Body reines Auslesen, mit Body SOLL/IST-Diff je Feld (`match`, `mismatch`, `missing_in_repo`, `extra_in_repo`, `not_written`).

**Wenn echtes In-place-Update gebraucht wird:** Round-trip selbst bauen — `POST /generate` (`input_source: node_id`) → bearbeiten → `PUT …/node/v1/nodes/-home-/{id}/metadata?versionComment=…&obeyMds=false` direkt gegen edu-sharing. Die Logik dafür liegt in `RepositoryService._set_metadata()`, ist aber nicht über einen Endpunkt erreichbar. Ein `target_node_id`-Parameter an `/upload` wäre der kleinste Eingriff.

---

## 6. Einzelne Metadaten generieren

### a) `POST /extract-field` — genau ein Feld

```jsonc
{
  "input_source": "node_id",        // text | url | node_id | node_url
  "node_id": "cbf66543-…",
  "text": "", "source_url": "",
  "extraction_method": "browser",   // simple | browser
  "output_format": "markdown",      // markdown | txt | html
  "context": "default", "version": "latest",
  "schema_file": "event.json",      // core.json für Kernfelder
  "field_id": "schema:startDate",
  "existing_metadata": {},          // Kontext für das LLM
  "language": "de",
  "normalize": true,
  "llm_provider": "b-api-openai",   // openai | b-api-openai | b-api-academiccloud
  "llm_model": "gpt-4.1-mini"
}
```

Antwort: `field_id`, `field_label`, `value`, `raw_value` (vor Normalisierung), `previous_value`, `changed`, `normalized`, `context`, `version`, `schema_file`, `processing`.

> ⚠️ Die Widget-`ApiService` hat `extractField()` implementiert, aber **kein UI-Element ruft sie auf**. Einzelfeld-Regeneration ist aktuell nur per API nutzbar — z. B. aus der Host-Anwendung heraus, das Ergebnis dann per `el.metadataInput = {...}` zurückspielen.

### b) `POST /generate` mit `regenerate_fields` — Teilmenge

```jsonc
{
  "input_source": "node_id",
  "node_id": "…",
  "existing_metadata": { /* aktueller Stand */ },
  "regenerate_fields": ["cclom:title", "cclom:general_description"],
  "regenerate_empty": false,   // true: alle leeren Felder neu ziehen
  "schema_file": "event.json"
}
```
Nur die gelisteten Felder werden neu extrahiert, der Rest kommt unverändert aus `existing_metadata`.

---

## 7. API-Endpunkte (alle 14)

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/health` | Health Check |
| GET | `/widget/info` | Einbettungs-Infos (⚠️ teils veraltet, s. o.) |
| GET | `/widget/i18n/{lang}.json` | UI-Übersetzungen |
| GET | `/info/schemata` | Verfügbare Kontexte |
| GET | `/info/schemas/{context}/{version}` | Schemas eines Kontexts |
| GET | `/info/schema/{context}/{version}/{schema_file}` | Einzelne Schema-Definition |
| POST | `/detect-content-type` | Content-Type erkennen |
| POST | `/generate` | Metadaten generieren (Voll oder `regenerate_fields`) |
| POST | `/extract-field` | Einzelfeld generieren |
| POST | `/validate` | Metadaten validieren |
| POST | `/export/markdown` | Markdown-Export |
| POST | `/upload` | Neuen Node im Repository anlegen |
| POST | `/upload/verify/{node_id}` | SOLL/IST-Vergleich |
| POST | `/screenshot` | Screenshot (optional direkt als Node-Preview) |

`repository` ist überall **deprecated und wirkungslos** — die Repo-URL kommt aus `METADATA_AGENT_REPOSITORY_URL`.

---

## 8. Steuerungs-Rezepte

**Reines Anzeige-Widget aus vorhandenem JSON:**
```html
<metadata-agent-canvas id="c" api-url="…" layout="detail" columns="3" readonly="true"></metadata-agent-canvas>
<script>document.getElementById('c').metadataInput = payload;</script>
```

**Prüfdialog ohne eigene Speicherung, Host übernimmt:**
```html
<metadata-agent-canvas id="c" api-url="…" layout="dialog" show-save-button="false"
                       show-upload-button="false" highlight-ai="true"></metadata-agent-canvas>
<script>
  document.getElementById('c').addEventListener('metadataSubmit', e => meinSpeichern(e.detail));
</script>
```

**2-spaltiger Prüftisch (Alias reicht nicht):**
```html
<metadata-agent-canvas api-url="…" layout="prueftisch" columns="2" flat-groups="true"></metadata-agent-canvas>
```

**Extraktion von außen anstoßen:**
```js
canvas.dispatchEvent(new CustomEvent('plugin-extract', {
  detail: { url: 'https://example.org', inputMode: 'url', reset: true }
}));
```

---

## 9. Bekannte Doku-Abweichungen (verifiziert)

| Quelle | Behauptung | Realität im Build |
|---|---|---|
| `/widget/info` | Attribute `node-id`, `source-url`, `show-input`, `show-controls` | existieren nicht (`controls` gibt es, `show-controls` nicht) |
| `/widget/info` | Layouts `compact`, `minimal` | keine Aliase → fallen auf `default` zurück |
| `/widget/info` | Events `extractionComplete`, `contentTypeDetected` | existieren nicht |
| README | `prueftisch-gross` → `columns=2` | Alias ändert die Spalten nicht |
| README | Layout-Alias `readonly` | mappt auf `default`, schaltet nicht readonly |
