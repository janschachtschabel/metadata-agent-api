# `POST /upload` — Antwortformat

Stand nach Einführung von `node_full`. **Bestehende Felder sind unverändert** — wer
heute gegen `/upload` programmiert, muss nichts anpassen.

## Request-Schalter

```jsonc
{
  "metadata": { "...": "..." },   // Output von /generate
  "return_full_node": true,       // Default: false
  "collection_id": ["3039bdb2-…"], // NEU, optional — immer eine Liste von
                                   // IDs oder Sammlungs-URLs
  "workflow_steps": [             // NEU, Default: ["200_tocheck"]
    "200_tocheck",
    "140_ELEMENT_LEGALLY_APPROVED"
  ]
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
| `schema_used` | string \| null | bei Erfolg | **NEU** — Typschema, gegen das geschrieben wurde. `null` = nur `core.json` |
| `repo_fields_available` | int \| null | bei Erfolg | **NEU** — wie viele Felder dieses Schema überhaupt schreiben darf (core 26, +`event.json` 33, +`learning_material.json` 40) |
| `fields_skipped` | int \| null | bei Erfolg | Übersprungene Felder (nicht repo-fähig) |
| `field_errors` | array \| null | – | `[{field_id, error, status_code}]` |
| `preview` | object \| null | – | Status des Vorschaubild-Uploads |
| `collections` | array \| null | **nur wenn Sammlungen angegeben waren** | `[{collectionId, success, error}]` |
| `workflow` | array \| null | **nur bei `start_workflow: true`** | `[{status, success, error}]` in ausgeführter Reihenfolge |
| `node_created` | bool \| null | bei Erfolg | **NEU** — `true`, wenn dieser Aufruf den Node angelegt hat; `false`, wenn er über `node_id` übergeben wurde |
| `discarded_node` | string \| null | nur nach Abbruch | ID des unvollständigen Nodes, der zurückgenommen wurde. **Nie gesetzt, wenn `node_id` übergeben wurde** — ein fremder Node wird nicht verworfen |

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

### `collections` und `workflow`

```jsonc
{
  "collections": [
    { "collectionId": "3039bdb2-…", "success": true,  "error": null },
    { "collectionId": "unbekannt",  "success": false, "error": "HTTP 404: …" }
  ],
  "workflow": [
    { "status": "200_tocheck",                 "success": true, "error": null },
    { "status": "140_ELEMENT_LEGALLY_APPROVED", "success": true, "error": null }
  ]
}
```

Beide Schritte laufen **nach** dem Schreiben der Metadaten. Ein Fehlschlag dort
setzt `success` des Uploads nicht zurück — der Node existiert dann bereits mit
allen Metadaten, nur die Sammlungs-Referenz bzw. der Workflow-Schritt fehlt. Das
steht im jeweiligen Eintrag.

Jeder Workflow-Schritt ist ein eigener Aufruf und damit ein eigener Eintrag in
der Workflow-Historie des Nodes — inklusive ausführendem Nutzer. Für bereits
hochgeladene Nodes gibt es denselben Ablauf als `POST /workflow/{node_id}`.

## Abbruch nach dem Anlegen

Der Upload legt den Node zuerst an und füllt ihn danach. Bricht die Verbindung
dazwischen ab — Timeout, Netzfehler —, bliebe sonst ein Node im Eingangsordner
zurück, der nur seinen Titel trägt: für den Aufrufer unsichtbar, der `success:
false` sieht und es erneut versucht, wobei jedes Mal einer mehr liegen bleibt.

Deshalb nimmt die API den angelegten Node in diesem Fall zurück (Papierkorb,
`recycle=true`, also wiederherstellbar) und meldet ihn als `discarded_node`:

```jsonc
{
  "success": false,
  "error": "Timeout bei der Verbindung zum Repository: … (unvollständiger Node wurde verworfen)",
  "discarded_node": "244bf208-de5e-4543-8bf2-08de5ed543fe"
}
```

Scheitert auch das Verwerfen, bleibt der Node bestehen und wird als `node.nodeId`
mit einem entsprechenden Hinweis in `error` zurückgegeben — dann ist ein manueller
Eingriff nötig.

Ein Fehler **vor** dem Anlegen verwirft nichts; ein erfolgreicher Upload ebenso
wenig.

## Kosten

`return_full_node: true` erzeugt einen zusätzlichen Repository-Aufruf nach allen
Schreibvorgängen. Der Node wird also im **finalen** Zustand gelesen — inklusive
Metadaten, Aspects, Collections und Extended Data, nicht im leeren Zustand direkt
nach dem Anlegen.

Deshalb Default `false`: `/upload` führt bereits mehrere sequentielle
edu-sharing-Aufrufe innerhalb eines 45-Sekunden-Timeouts aus, und auf Serverless
zählt jeder weitere.
