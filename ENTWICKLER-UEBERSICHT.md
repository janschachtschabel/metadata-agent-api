# Entwickler-Übersicht: Core-Metadaten, Sammlungen, Workflow

Drei Fragen, kurz beantwortet:

1. [Was `core.json` erzeugt und mitliefert](#1-was-corejson-erzeugt-und-mitliefert)
2. [Sammlungs-ID übergeben](#2-sammlungs-id-übergeben)
3. [Workflow triggern](#3-workflow-triggern)

Alle Angaben sind aus `src/schemata/default/v2.0.0/core.json` und den
Pydantic-Modellen in `src/models/schemas.py` gezogen, nicht abgeschrieben.
Ausführliche Endpoint-Doku: [README.md](README.md).

---

## 1. Was `core.json` erzeugt und mitliefert

`core.json` enthält **24 Felder**. Sie werden bei jedem `/generate`-Aufruf
mitverarbeitet (`include_core: true`, Standard) — zusätzlich zu den Feldern des
inhaltstyp-spezifischen Schemas (`learning_material.json`, `event.json`, …).

### Antwort-Umschlag von `/generate`

```jsonc
{
  "contextName":     "default",
  "schemaVersion":   "2.0.0",
  "metadataset":     "learning_material.json",   // erkannter Inhaltstyp
  "metadataset_uri": "http://w3id.org/openeduhub/vocabs/contentTypes/…",
  "language":        "de",
  "exportedAt":      "2026-08-11T…",
  "metadata":        { /* die Felder, flach */ },
  "processing":      { /* Laufzeit, Provider, Modell, Feldzahlen */ }
}
```

Der komplette Umschlag kann **unverändert** als `/upload`-Body gesendet werden.

### Body-Format beim Upload

**Nimm Form 1:** die `/generate`-Antwort unverändert weiterreichen. `/generate`
antwortet **flach** — Umschlag und Felder auf einer Ebene ([main.py](src/main.py:1786)).
Nichts umbauen, nichts verlieren.

Form 2 und 3 sind gleichwertig und schreiben dieselben Felder; sie existieren,
weil beide im Umlauf sind.

```jsonc
// 1) EMPFOHLEN — genau das, was /generate zurückgibt
{ "contextName": "default", "schemaVersion": "2.0.0", "metadataset": "event.json",
  "cclom:title": "…",
  "collection_id": ["3039bdb2-…"] }          // Optionen daneben

// 2) Felder unter `metadata` — so exportiert die Webkomponente
{ "contextName": "default", "schemaVersion": "2.0.0", "metadataset": "event.json",
  "metadata": { "cclom:title": "…" } }

// 3) Alles unter `metadata` — so sendet die Webkomponente
{ "metadata": { "contextName": "…", "metadataset": "event.json",
                "metadata": { "cclom:title": "…" } } }
```

Die Erkennung hängt an einer einzigen Bedingung: ist `metadata` im Body ein
Objekt, gilt Form 1 oder 3, sonst Form 2. Bei Form 2 sind die Options-Namen
(`collection_id`, `workflow_steps`, `source`, `check_duplicates`, …) auf der
obersten Ebene reserviert — Metadaten-IDs tragen aber alle einen Namensraum
(`ccm:`, `cclom:`, `schema:`), also kollidiert das nicht.

> **`metadataset` immer mitschicken.** Der Schlüssel entscheidet, welches
> Typschema zusätzlich zu `core.json` geladen wird — und damit, welche Felder
> überhaupt geschrieben werden dürfen:
>
> | geladen | Repo-Felder |
> |---|---|
> | nur `core.json` | 22 |
> | + `learning_material.json` | 34 |
> | + `event.json` | 29 |
>
> Fehlt er, fallen bei einer Veranstaltung `ccm:oeh_event_begin`,
> `ccm:oeh_event_end`, `ccm:price` und `ccm:competence` weg — ohne Fehler, mit
> `success: true`. `/generate` liefert ihn mit; wer die Antwort umbaut, muss ihn
> behalten.

Dieselben drei Formen und dieselbe `metadataset`-Regel gelten für **`/validate`**
und **`/export/markdown`** — beide entscheiden daran, gegen welches Schema sie
arbeiten.

### Die 27 Core-Felder

`Repo` = wird ins Repository geschrieben · `KI` = wird von der Extraktion
befüllt · `User` = im Widget sichtbar/editierbar · `[]` = Mehrfachwert

| Feld-ID | Label | Typ | Repo | KI | User | `[]` |
|---|---|---|:--:|:--:|:--:|:--:|
| `cclom:title` | Titel | string | ✅ | ✅ | ✅ | |
| `cclom:general_description` | Beschreibungstext | string | ✅ | ✅ | ✅ | |
| `cclom:general_keyword` | Schlagwörter | array | ✅ | ✅ | ✅ | ✅ |
| `ccm:wwwurl` | Web-URL | uri | ✅ | ✅ | ✅ | |
| `preview:url` | URL des Vorschaubildes | uri | ✅ | ✅ | | |
| `cclom:general_language` | Sprache | string | ✅ | ✅ | ✅ | |
| `ccm:oeh_extendedType` | Inhaltsart(en) | array | ⚠️ | | | |
| `ccm:educationalcontext` | Bildungsstufe | array | ✅ | ✅ | ✅ | ✅ |
| `ccm:taxonid` | Fach | array | ✅ | ✅ | ✅ | ✅ |
| `oeh:new_lrt` | Lernressourcentyp | array | ✅ | ✅ | ✅ | ✅ |
| `ccm:educationalintendedenduserrole` | Zielgruppe | array | ✅ | ✅ | ✅ | ✅ |
| `ccm:commonlicense_ai_allow_usage` | KI-Nutzung erlaubt | string | ✅ | ✅ | ✅ | |
| `ccm:commonlicense_ai_generated` | Mit KI erzeugt | string | ✅ | ✅ | ✅ | |
| `ccm:commonlicense_ai_manually_modified` | KI-Ergebnis redaktionell überarbeitet | string | ✅ | ✅ | ✅ | |
| `ccm:oeh_quality_relevancy_for_education` | Geeignet für Bildung (WLO-Suche) | string | ✅ | ✅ | | |
| `ccm:oeh_quality_criminal_law` | Strafrecht | string | ✅ | ✅ | | |
| `ccm:oeh_quality_protection_of_minors` | Jugendschutz | string | ✅ | ✅ | | |
| `ccm:oeh_quality_copyright_law` | Urheberrecht | string | ✅ | ✅ | | |
| `ccm:oeh_quality_personal_law` | Persönlichkeitsrechte | string | ✅ | ✅ | | |
| `ccm:oeh_quality_correctness` | Sachrichtigkeit | string | ✅ | ✅ | | |
| `ccm:oeh_quality_data_privacy` | Datenschutz | string | ✅ | ✅ | | |
| `ccm:oeh_quality_neutralness` | Neutralität | string | ✅ | ✅ | | |
| `ccm:oeh_quality_didactics` | Didaktik/Methodik | string | ✅ | ✅ | | |
| `ccm:oeh_quality_medial` | Medial passend | string | ✅ | ✅ | | |
| `ccm:oeh_quality_transparentness` | Anbieter Renommee | string | ✅ | ✅ | | |
| `ccm:oeh_quality_currentness` | Aktualität | string | ✅ | ✅ | | |
| `ccm:oeh_buffet_criteria` | Kriterien für Redaktionsbuffet | array | ✅ | ✅ | | ✅ |

⚠️ `ccm:oeh_extendedType` trägt **kein** `repo_field`. Es wird trotzdem
geschrieben — über den Extended-Fields-Schritt beim Upload, nicht über den
normalen Metadaten-Filter.

`oeh:new_lrt` heißt im Repository **`ccm:oeh_lrt`**; der Upload benennt das Feld
beim Schreiben um, genau wie er `cm:author` in
`ccm:lifecyclecontributer_author` überführt. In der `/generate`-Antwort bleibt
es `oeh:new_lrt` — am Vertrag ändert sich nichts. Findet die Extraktion keinen
Typ, leitet der Upload ersatzweise einen groben aus `ccm:oeh_extendedType` ab
(`learning_material` → „Material"). Siehe
[WLO-REPO-FELDER.md](WLO-REPO-FELDER.md).

Die drei `ccm:commonlicense_ai_*`-Felder sind Strings mit genau zwei möglichen
Werten, `"true"` und `"false"` — bewusst kein JSON-Boolean, weil das Repository
`["false"]` erwartet und nicht `[false]`. Die KI setzt sie nur, wenn Text,
Impressum oder Lizenz es hergeben; sonst bleiben sie leer.

### Die zwölf Qualitätsfelder

Sie sind **im Widget unsichtbar** (`ask_user: false`), werden aber von der KI
befüllt, im `/generate`-Output mitgeliefert und beim Upload ins Repository
geschrieben. Wer den Output durchreicht, muss sie also nicht kennen — wer ihn
umbaut, darf sie nicht verlieren.

**Achtung beim Wertebereich:** die Hälfte sind Klartext-Ziffern, die andere
Hälfte Vokabular-URIs — und die URI-Pfade heißen anders als die Felder.

| Feld | Werte |
|---|---|
| `ccm:oeh_quality_relevancy_for_education` | `"0"` \| `"1"` |
| `ccm:oeh_quality_correctness` | `"0"` … `"5"` |
| `ccm:oeh_quality_currentness` | `"0"` … `"5"` |
| `ccm:oeh_quality_criminal_law` | `quality/no_auto_findings` \| `quality/auto_findings` |
| `ccm:oeh_quality_protection_of_minors` | dito |
| `ccm:oeh_quality_copyright_law` | dito |
| `ccm:oeh_quality_personal_law` | dito |
| `ccm:oeh_quality_data_privacy` | `quality_data_privacy/0` … `/5` |
| `ccm:oeh_quality_neutralness` | `quality_neutrality/0` … `/5` ← |
| `ccm:oeh_quality_didactics` | `quality_didactics/0` … `/5` |
| `ccm:oeh_quality_medial` | `quality_media/0` … `/5` ← |
| `ccm:oeh_quality_transparentness` | `quality_transparency/0` … `/5` ← |
| `ccm:oeh_buffet_criteria` | `content_valid`, `speech_valid`, `medial_relevant`, `didactics_valid`, `accessible`, `usable_for_buffet` |

Präfix aller URIs: `http://w3id.org/openeduhub/vocabs/`

← Bei diesen drei heißt der Vokabular-Pfad **anders als das Feld**:
`neutralness` → `quality_neutrality`, `medial` → `quality_media`,
`transparentness` → `quality_transparency`. Wer die URI aus dem Feldnamen
zusammenbaut, erzeugt einen Wert, den WLO nicht auflöst.

> `scripts/check_quality_vocabularies.py` vergleicht diese Wertebereiche gegen
> den Live-MDS und meldet Drift.

### Was beim Upload **nicht** ins Repository geht

`/upload` filtert auf `repo_field: true` und wirft weg:

- alles mit Präfix `virtual:` — von edu-sharing beim Lesen berechnet, nie
  gespeichert. Das gilt unabhängig vom Schema-Flag.
- alles ohne `repo_field: true`, darunter die Transformations-Eingaben
  `schema:location` und `schema:geo` (fließen über `cm:latitude` /
  `cm:longitude` ein)
- die internen Schlüssel `_origins`, `_source_text`
- den Umschlag selbst (`contextName`, `schemaVersion`, `metadataset`, …)

Das Präfix `schema:` allein schließt nichts aus: `schema:datePublished` ist ein
reguläres Repository-Feld und wird geschrieben.

Lädt kein Schema (Fehlerfall), wird **gar nichts** geschrieben statt blind zu
raten.

---

## 2. Sammlungs-ID übergeben

Optionaler Parameter `collection_id` auf `POST /upload` — **immer ein Array**,
auch bei einer einzigen Sammlung.

```jsonc
// Eine Sammlung
{ "metadata": { … }, "collection_id": ["3039bdb2-f51f-4cc8-b1d9-3fb6b0ffc1d9"] }

// Mehrere
{ "metadata": { … }, "collection_id": ["3039bdb2-…", "7a1e0c44-…"] }

// URL aus der Redaktionsumgebung — direkt einfügbar
{ "metadata": { … },
  "collection_id": ["https://repository.staging.openeduhub.net/edu-sharing/components/collections?id=3039bdb2-…"] }
```

Ein nackter String gibt **`422`**. Das ist Absicht: `workflow_steps` und
`workflow_receiver` nehmen ebenfalls ausschließlich Listen — ein Feld, das
beides schluckt, machte das Anfrageformat davon abhängig, welchen Parameter man
gerade füllt.

```jsonc
{ "collection_id": "3039bdb2-…" }     // ❌ 422
{ "collection_id": ["3039bdb2-…"] }   // ✅
{ "collection_id": [] }               // ✅ wie weglassen
```

### Welche Schreibweisen je Eintrag erkannt werden

| Eintrag | Ergebnis |
|---|---|
| `3039bdb2-…` | unverändert |
| `…/components/collections?id=3039bdb2-…&mainnav=true` | ID aus `id`-Parameter |
| `…/components/collections/3039bdb2-…` | letztes Pfadsegment |
| `"  3039bdb2-…  "` | getrimmt |
| `3039bdb2-…#tab` | Fragment entfernt |

Leere Einträge fallen raus; bleibt nichts übrig, gilt das wie weglassen.

### Weitere Quellen und Reihenfolge

Zusätzlich zum Parameter werden Sammlungen aus den Metadaten gelesen:

1. `collection_id` (Parameter)
2. `virtual:collection_id_primary` (Metadaten)
3. `ccm:collection_id` (Metadaten, Liste)

Duplikate fallen raus, die erste Nennung gewinnt.

### Was passiert

Der hochgeladene Inhalt wird als **Referenz** in die Sammlung gelegt. Das
Original bleibt im Inbox-Ordner; die Sammlung bekommt einen Verweis darauf.

### Antwort

```jsonc
{
  "success": true,
  "node": { "nodeId": "…", "repositoryUrl": "…/components/render/…" },
  "collections": [
    { "collectionId": "3039bdb2-…", "success": true },
    { "collectionId": "7a1e0c44-…", "success": false,
      "error": "HTTP 403: …" }
  ]
}
```

`collections` erscheint nur, wenn Sammlungen angegeben waren — **ein Eintrag pro
Sammlung**. Eine fehlgeschlagene Referenzierung setzt `success` auf oberster
Ebene *nicht* auf `false`: der Node ist angelegt und die Metadaten sind
geschrieben. Wer auf die Sammlung angewiesen ist, muss `collections` auswerten.

---

## 3. Workflow triggern

### Standardfall: gar nichts tun

`start_workflow` steht auf `true`. Jeder Upload endet damit automatisch bei:

| | |
|---|---|
| Status | `200_tocheck` — „Zur Prüfung übergeben" |
| Empfänger | `GROUP_ORG_WLO-Uploadmanager` |
| Kommentar | `Upload via Metadata Agent API` |

Der Inhalt liegt danach in der Redaktions-Warteschlange.

### Ohne Workflow hochladen

```jsonc
{ "metadata": { … }, "start_workflow": false }
```

> Eine **leere** `workflow_steps`-Liste ist dafür **nicht** der richtige Weg —
> sie wird mit `422` abgelehnt. Sie liest sich wie „keine Schritte", würde aber
> beim Weglassen auf den Standard zurückfallen, also genau das Gegenteil tun.

### Weiter als `200_tocheck` — direkt beim Upload

```jsonc
{
  "metadata": { … },
  "workflow_steps": ["200_tocheck", "120_METADATA_QUALITY_CONFIRMED", "150_PUBLISH_IN_SEARCH"],
  "workflow_comment": "Automatische Erstprüfung",
  "workflow_receiver": ["GROUP_ORG_WLO-Uploadmanager"]
}
```

Die Status werden **einzeln und der Reihe nach** gesetzt. Das ist Absicht:
edu-sharing schreibt jeden `PUT` als eigenen Eintrag in die Workflow-Historie,
mitsamt handelndem Nutzer. Ein Sprung auf den Endstatus verlöre die Spur, wer
was bestätigt hat.

`workflow_receiver` gilt für alle Schritte. Ohne Angabe bekommt nur
`200_tocheck` die Upload-Manager-Gruppe, spätere Status werden auf den
handelnden Nutzer geschrieben (leerer Empfänger) — so macht es die Redaktion
selbst.

### Später weiterschalten

```
POST /workflow/{node_id}
```

```jsonc
{ "steps": ["140_ELEMENT_LEGALLY_APPROVED", "150_PUBLISH_IN_SEARCH"],
  "comment": "Rechteprüfung abgeschlossen" }
```

`node_id` muss eine Node-UUID sein — der Wert landet in der Repository-URL und
die Anfrage trägt die Zugangsdaten des Service-Accounts. Alles andere gibt `400`.

Antwort enthält zusätzlich den **zurückgelesenen** Zustand:

```jsonc
{
  "success": true,
  "nodeId": "…",
  "steps": [{ "status": "150_PUBLISH_IN_SEARCH", "success": true }],
  "current_status": "150_PUBLISH_IN_SEARCH",   // aus ccm:wf_status
  "history": [ /* wer wann welchen Status gesetzt hat */ ],
  "repositoryUrl": "…/components/render/…"
}
```

### Erlaubte Status

Unbekannte Status werden mit `422` abgelehnt, **bevor** etwas ins Repository
geht — ein Tippfehler landet nicht in den Daten.

| Status | Bedeutung |
|---|---|
| `100_unchecked` | Ungeprüft |
| `110_METADATA_RECORD_REQUESTED` | Metadaten-Erfassung angefordert |
| `120_METADATA_QUALITY_CONFIRMED` | Metadaten-Qualität bestätigt |
| `125_METADATA_QUALITY_FOR_BUFFET` | Für Redaktionsbuffet qualifiziert |
| `130_ELEMENT_REJECTED` | Element abgelehnt |
| `140_ELEMENT_LEGALLY_APPROVED` | Qualität bestätigt / freigegeben |
| `150_PUBLISH_IN_SEARCH` | In der Suche veröffentlicht |
| `160_REMOVE_FROM_SEARCH` | Aus der Suche entfernt |
| `200_tocheck` | Zur Prüfung übergeben (Standard nach `/upload`) |
| `TASK_CREATE_TREE` | Aufgaben-Status |
| `TASK_CHECK_COLLECTION_PROPOSAL` | Aufgaben-Status |
| `TASK_CHECK_QUALITY` | Aufgaben-Status |

Quelle: Repository-Konfiguration (`/rest/config/v1/values` →
`workflow.workflows`), ergänzt um `200_tocheck` und
`125_METADATA_QUALITY_FOR_BUFFET`, die in den Live-Daten vorkommen, dort aber
nicht gelistet sind.

---

## Minimalbeispiel: alles zusammen

```bash
# 1. Metadaten erzeugen
curl -X POST https://<host>/generate \
  -H 'Content-Type: application/json' \
  -d '{"input_source":"url","source_url":"https://example.org/arbeitsblatt"}' \
  > generated.json

# 2. Unverändert hochladen, in eine Sammlung legen, bis zur Freigabe schalten
jq '{metadata: ., collection_id: ["3039bdb2-f51f-4cc8-b1d9-3fb6b0ffc1d9"],
     workflow_steps: ["200_tocheck","120_METADATA_QUALITY_CONFIRMED"]}' generated.json \
| curl -X POST https://<host>/upload -H 'Content-Type: application/json' -d @-
```

---

## Fehlerfälle, die man kennen sollte

| Situation | Verhalten |
|---|---|
| Falsches oder fehlendes `metadataset` | Es gilt nur `core.json`; typspezifische Felder fallen weg. **Sichtbar an `schema_used` und `repo_fields_available` in der Antwort** |
| Upload bricht nach dem Anlegen ab | Node wird zurückgenommen (Papierkorb, wiederherstellbar); die ID steht in `discarded_node` |
| Rücknahme scheitert ebenfalls | `discarded_node` bleibt gesetzt — der Node existiert und muss von Hand weg |
| Einzelnes Feld wird abgelehnt | Bulk-Schreiben fällt auf Feld-für-Feld zurück; `field_errors` nennt die Schuldigen, der Upload gilt trotzdem als erfolgreich |
| Keine Lizenz erkannt | `ccm:commonlicense_key` bleibt **leer**. Kein Default — „unbekannt" wird nicht zu „urheberrechtsfrei" gemacht |
| URL existiert bereits | `duplicate: true`, kein neuer Node (abschaltbar mit `check_duplicates: false`) |
