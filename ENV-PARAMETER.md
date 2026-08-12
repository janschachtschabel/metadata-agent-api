# Umgebungsvariablen — vollständige Referenz

Alle Variablen, die `src/config.py` liest. Die Liste wird von
`tests/test_env_parameters.py` gegen das Settings-Modell geprüft — eine neue
Einstellung ohne Eintrag hier lässt den Test fehlschlagen.

**Zwei Namensschemata:** Secrets tragen ihren Namen unverändert
(`B_API_KEY`, `OPENAI_API_KEY`, `WLO_GUEST_USERNAME`, `WLO_GUEST_PASSWORD`),
alles andere das Präfix `METADATA_AGENT_`.

Unbekannte Variablen werden ignoriert (`extra: "ignore"`) — eine alte `.env`
bricht nichts, ein Tippfehler fällt aber auch nicht auf.

---

## Secrets

| Variable | Default | Benötigt für |
|---|---|---|
| `B_API_KEY` | — | `llm_provider=b-api-openai` oder `b-api-academiccloud` |
| `OPENAI_API_KEY` | — | `llm_provider=openai` |
| `WLO_GUEST_USERNAME` | — | `/upload` |
| `WLO_GUEST_PASSWORD` | — | `/upload` |

---

## LLM: Providerwahl

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_LLM_PROVIDER` | `b-api-openai` | `b-api-openai`, `b-api-academiccloud` oder `openai` |

Pro Request überschreibbar: `llm_provider` und `llm_model` im Body von
`/generate`, `/detect-content-type` und `/extract-field`.

## LLM: Durchsatzgrenzen

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS` | providerabhängig | Gleichzeitige Requests. Leer = gemessener Wert des Providers |
| `METADATA_AGENT_LLM_MAX_REQUESTS_PER_SECOND` | providerabhängig | Requests pro Sekunde. `0` schaltet die Ratenbegrenzung ab |

Die Defaults kommen aus Messungen, nicht aus Zusagen:

| Provider-Gruppe | gleichzeitig | pro Sekunde |
|---|---:|---:|
| `b-api` (beide B-API-Provider) | **2** | **2** |
| `openai` (nativ) | 10 | keine Grenze |

Beide Grenzen gelten **prozessweit**, nicht pro Request — die B-API zählt sie
am Key, nicht am Modell, und deshalb teilen sich `b-api-openai` und
`b-api-academiccloud` ein Budget. Ein dritter paralleler Request wird sofort
mit `429` abgewiesen, und zwar **ohne `retry-after`**: es gibt nichts, woran ein
Client die Wartezeit ablesen könnte, er muss unter der Grenze bleiben. Mehr Last
hilft nicht — bei 3 req/s fällt der effektive Durchsatz *unter* den Wert bei
2 req/s.

## LLM: Modelle und Endpunkte

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_B_API_BASE_URL` | `https://b-api.staging.openeduhub.net` | Basis; die beiden Endpunktpfade werden daraus abgeleitet |
| `METADATA_AGENT_B_API_OPENAI_BASE` | abgeleitet | Nur setzen, wenn der Pfad vom Schema abweicht |
| `METADATA_AGENT_B_API_OPENAI_MODEL` | `gpt-5.6-luna` | Modell für `b-api-openai` |
| `METADATA_AGENT_B_API_ACADEMICCLOUD_BASE` | abgeleitet | wie oben |
| `METADATA_AGENT_B_API_ACADEMICCLOUD_MODEL` | `openai-gpt-oss-120b` | Modell für `b-api-academiccloud` |
| `METADATA_AGENT_OPENAI_API_BASE` | `https://api.openai.com/v1` | Beliebiger OpenAI-kompatibler Endpunkt |
| `METADATA_AGENT_OPENAI_MODEL` | `gpt-4o-mini` | Modell für `openai` |

`METADATA_AGENT_OPENAI_API_BASE` muss nicht auf OpenAI zeigen. Alles, was
`/chat/completions` bedient und einen Bearer-Token annimmt, funktioniert —
Azure-Deployment, selbst gehostetes vLLM, ein Gateway davor. Prod-Basis der
B-API: `https://b-api.prod.openeduhub.net`.

## LLM: Generierung

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_LLM_TEMPERATURE` | `0.3` | Gilt für alle drei Provider |
| `METADATA_AGENT_OPENAI_TEMPERATURE` | folgt `LLM_TEMPERATURE` | Nur nötig, wenn nativ OpenAI abweichen soll |
| `METADATA_AGENT_LLM_MAX_TOKENS` | `2000` | Bei Reasoning-Modellen als `max_completion_tokens` gesendet |
| `METADATA_AGENT_LLM_VERBOSITY` | `low` | Nur GPT-5-Serie/o-Modelle. Leer = nicht senden |
| `METADATA_AGENT_LLM_REASONING_EFFORT` | `low` | Nur GPT-5-Serie/o-Modelle. `none`/`low`/`medium`/`high` |
| `METADATA_AGENT_LLM_MAX_RETRIES` | `3` | Wiederholungen bei `429`/`5xx` |
| `METADATA_AGENT_LLM_RETRY_DELAY` | `1.0` | Basiswert; der Abstand wächst linear mit dem Versuch |

`VERBOSITY` und `REASONING_EFFORT` werden nur an Modelle mit den Präfixen
`gpt-5`, `o1`, `o3`, `o4` gesendet — ältere Modelle antworten darauf mit `400`.
Dieselbe Erkennung stellt bei diesen Modellen `max_tokens` auf
`max_completion_tokens` um und lässt `temperature` weg. Das gilt providerunabhängig,
also auch bei nativem OpenAI.

## Worker und Zeitlimits

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_DEFAULT_MAX_WORKERS` | `10` | Breite des parallelen Feld-Fan-outs (1–20) |
| `METADATA_AGENT_REQUEST_TIMEOUT` | `60` | Sekunden |

`DEFAULT_MAX_WORKERS` wird auf `LLM_MAX_CONCURRENT_REQUESTS` gedeckelt. Bei der
B-API laufen also 2 Worker, egal was hier steht — mehr zu fordern erzeugt nur
Wartende. Beim Start wird das ausgewiesen:

```
Default Workers: 10 → 2 (limit of b-api)
LLM Throughput: max 2 in flight, max 2 req/s
```

## Schemata

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_DEFAULT_CONTEXT` | `default` | `default` oder `mds_oeh` |
| `METADATA_AGENT_DEFAULT_VERSION` | `1.8.1` | Nur für die Anzeige unter `/contexts` |

Die Endpunkte selbst nehmen `version` aus dem Request, Default `latest`, und das
löst über `isDefault` im Manifest auf **2.0.0** auf.

## Normalisierung

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_NORMALIZATION_ENABLED` | `true` | |
| `METADATA_AGENT_NORMALIZATION_TEMPERATURE` | `0.1` | |

## Repository und Eingabequellen

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_REPOSITORY_URL` | `https://repository.staging.openeduhub.net/edu-sharing/rest` | Ziel für Abruf **und** Upload |
| `METADATA_AGENT_WLO_INBOX_ID` | `21144164-30c0-4c01-ae16-264452197063` | Ordner, in dem neue Knoten entstehen |
| `METADATA_AGENT_TEXT_EXTRACTION_API_URL` | `https://text-extraction.staging.openeduhub.net` | |
| `METADATA_AGENT_TEXT_EXTRACTION_DEFAULT_METHOD` | `simple` | `simple` oder `browser` |

Prod-Repository: `https://redaktion.openeduhub.net/edu-sharing/rest`.
Es gibt **keinen** zweiten Schalter für das Ziel-Repository — der
`repository`-Parameter im Request wird ignoriert.

## Screenshots

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_SCREENSHOT_METHOD` | `pageshot` | `pageshot` (extern) oder `playwright` (im Container) |
| `METADATA_AGENT_PAGESHOT_API_URL` | `https://pageshot.site/v1/screenshot` | |
| `METADATA_AGENT_SCREENSHOT_WIDTH` | `800` | |
| `METADATA_AGENT_SCREENSHOT_HEIGHT` | `500` | |
| `METADATA_AGENT_SCREENSHOT_FORMAT` | `png` | |
| `METADATA_AGENT_SCREENSHOT_BLOCK_ADS` | `true` | |
| `METADATA_AGENT_SCREENSHOT_FULL_PAGE` | `false` | |
| `METADATA_AGENT_SCREENSHOT_DELAY` | `2000` | Millisekunden vor der Aufnahme |

Auf Vercel steht nur `pageshot` zur Verfügung.

## Anwendung

| Variable | Default | Beschreibung |
|---|---|---|
| `METADATA_AGENT_APP_NAME` | `Metadata Agent API` | |
| `METADATA_AGENT_APP_VERSION` | `2.0.0` | |
| `METADATA_AGENT_DEBUG` | `false` | |
| `METADATA_AGENT_CORS_ORIGINS` | `*` | Komma-getrennt oder `*` |

---

## Konfiguration je Betriebsart

**B-API AcademicCloud** — die Variante mit den engsten Grenzen:

```env
METADATA_AGENT_LLM_PROVIDER=b-api-academiccloud
B_API_KEY=...
METADATA_AGENT_B_API_ACADEMICCLOUD_MODEL=openai-gpt-oss-120b
# Die Defaults 2/2 passen bereits — hier nur zur Verdeutlichung:
METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS=2
METADATA_AGENT_LLM_MAX_REQUESTS_PER_SECOND=2
```

**Nativ OpenAI, ohne Ratenbegrenzung:**

```env
METADATA_AGENT_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
METADATA_AGENT_OPENAI_MODEL=gpt-4o-mini
METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS=10
METADATA_AGENT_LLM_MAX_REQUESTS_PER_SECOND=0
```

**Eigenes OpenAI-kompatibles Gateway:**

```env
METADATA_AGENT_LLM_PROVIDER=openai
OPENAI_API_KEY=egal-was-das-gateway-erwartet
METADATA_AGENT_OPENAI_API_BASE=https://mein-gateway.example/v1
METADATA_AGENT_OPENAI_MODEL=lokales-modell
METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS=4
```
