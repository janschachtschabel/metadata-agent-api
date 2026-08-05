# `POST /upload` — Antwortformat

Stand nach Einführung von `node_full`. **Bestehende Felder sind unverändert** — wer
heute gegen `/upload` programmiert, muss nichts anpassen.

## Request-Schalter

```jsonc
{
  "metadata": { "...": "..." },   // Output von /generate
  "return_full_node": true        // NEU, Default: false
}
```

## Antwort

| Feld | Typ | Immer da? | Bedeutung |
|---|---|---|---|
| `success` | bool | ja | Upload erfolgreich |
| `duplicate` | bool \| null | – | `true` wenn `ccm:wwwurl` bereits existiert |
| `node` | object \| null | bei Erfolg + bei Duplikat | Kurzinfo (unverändert) |
| `node_full` | object \| null | **nur bei `return_full_node: true`** | Kompletter edu-sharing Node |
| `error` | string \| null | – | Fehlermeldung |
| `step` | string \| null | – | Schritt, an dem es scheiterte (z. B. `setMetadata`) |
| `fields_written` | int \| null | bei Erfolg | Geschriebene Felder |
| `fields_skipped` | int \| null | bei Erfolg | Übersprungene Felder (nicht repo-fähig) |
| `field_errors` | array \| null | – | `[{field_id, error, status_code}]` |
| `preview` | object \| null | – | Status des Vorschaubild-Uploads |

### `node` — die bisherige Kurzinfo

```jsonc
{
  "nodeId": "5ab4b434-4832-45ca-b4b4-34483265ca5d",
  "title": "Workshop KI in der Bildung",
  "description": "Ein Workshop über…",       // auf 200 Zeichen gekürzt
  "wwwurl": "https://example.org/workshop",
  "repositoryUrl": "https://repository.staging.openeduhub.net/edu-sharing/components/render/5ab4b434-…"
}
```

Die Werte stammen aus den **gesendeten** Metadaten, nicht aus dem Repository.
`repositoryUrl` ist ein Konstrukt des Agenten und existiert in edu-sharing nicht.

### `node_full` — der Node aus dem Repository

Nur vorhanden, wenn `return_full_node: true` gesetzt war. Enthält den Node **so, wie
ihn edu-sharing liefert** — identische Struktur zum `node`-Objekt aus
`GET /node/v1/nodes/-home-/{id}/metadata` und aus der Antwort von `createChild`.

```jsonc
{
  "ref":        { "repo": "…", "id": "5ab4b434-…" },
  "parent":     { "repo": "…", "id": "21144164-…" },   // Inbox-Ordner
  "type":       "ccm:io",
  "aspects":    [ "…" ],
  "properties": {
    "cclom:title":               [ "Workshop KI in der Bildung" ],
    "cclom:general_description": [ "Ein Workshop über…" ],
    "ccm:wwwurl":                [ "https://example.org/workshop" ]
  }
}
```

Der Ausschnitt zeigt nur die Felder, auf die es hier ankommt — maßgeblich ist die
Node-Definition der edu-sharing REST-API, nicht diese Datei.

**Feldzuordnung zwischen beiden Objekten:**

| `node` | `node_full` |
|---|---|
| `nodeId` | `ref.id` |
| `title` | `properties["cclom:title"][0]` |
| `wwwurl` | `properties["ccm:wwwurl"][0]` |
| `description` (gekürzt) | `properties["cclom:general_description"][0]` (ungekürzt) |
| `repositoryUrl` | *kein Gegenstück* |

Beachten: In `node_full` sind Property-Werte **immer Arrays**, auch bei einem einzigen
Wert.

## Wann `node_full` leer bleibt

- `return_full_node` war nicht gesetzt
- Das Zurücklesen ist fehlgeschlagen — der Upload gilt trotzdem als erfolgreich
  (`success: true`), weil der Node bereits geschrieben wurde. Ein Lesefehler danach
  darf einen erfolgreichen Schreibvorgang nicht als Fehlschlag melden.

## Beispiele

**Erfolg mit vollständigem Node**

```jsonc
{
  "success": true,
  "duplicate": null,
  "node":      { "nodeId": "5ab4b434-…", "title": "Workshop KI in der Bildung", "…": "…" },
  "node_full": { "ref": { "id": "5ab4b434-…" }, "properties": { "…": "…" } },
  "fields_written": 23,
  "fields_skipped": 4,
  "preview": { "success": true, "method": "pageshot" }
}
```

**Duplikat** — `node`/`node_full` beschreiben den **bereits vorhandenen** Node:

```jsonc
{
  "success": false,
  "duplicate": true,
  "node":      { "nodeId": "abc-…", "title": "Schon vorhanden", "…": "…" },
  "node_full": { "ref": { "id": "abc-…" }, "…": "…" },
  "error": "URL existiert bereits: \"Schon vorhanden\""
}
```

## Kosten

`return_full_node: true` erzeugt einen zusätzlichen Repository-Aufruf nach allen
Schreibvorgängen. Der Node wird also im **finalen** Zustand gelesen — inklusive
Metadaten, Aspects, Collections und Extended Data, nicht im leeren Zustand direkt
nach dem Anlegen.

Deshalb Default `false`: `/upload` führt bereits mehrere sequentielle
edu-sharing-Aufrufe innerhalb eines 45-Sekunden-Timeouts aus, und auf Serverless
zählt jeder weitere.
