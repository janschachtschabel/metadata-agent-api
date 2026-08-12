# Vercel — Umgebungsvariablen

Einzutragen unter **Project → Settings → Environment Variables**. Nach jeder
Änderung ist ein **Redeploy nötig** — Vercel zieht Variablen nur beim Build.

Vollständige Referenz aller Variablen inklusive der hier nicht aufgeführten:
[ENV-PARAMETER.md](ENV-PARAMETER.md).

---

## 1. Pflicht — ohne diese läuft nichts

| Name | Wert | Environments |
|---|---|---|
| `B_API_KEY` | *(euer Key)* | Production, Preview, Development |

Als **Sensitive** markieren. Nur nötig, wenn `LLM_PROVIDER` auf einem der beiden
`b-api-*`-Werte steht (Standard).

## 2. Für `/upload` ins Repository

| Name | Wert | Environments |
|---|---|---|
| `WLO_GUEST_USERNAME` | *(Login)* | Production, Preview |
| `WLO_GUEST_PASSWORD` | *(Passwort)* | Production, Preview |

Beide **Sensitive**. Fehlen sie, antworten `/generate` und `/validate` weiterhin
normal; nur `/upload` scheitert.

## 3. Empfohlen — explizit setzen statt auf Defaults verlassen

| Name | Wert |
|---|---|
| `METADATA_AGENT_LLM_PROVIDER` | `b-api-academiccloud` |
| `METADATA_AGENT_B_API_BASE_URL` | `https://b-api.staging.openeduhub.net` |
| `METADATA_AGENT_B_API_ACADEMICCLOUD_MODEL` | `deepseek-v4-flash` |
| `METADATA_AGENT_LLM_VERBOSITY` | `low` |
| `METADATA_AGENT_LLM_REASONING_EFFORT` | `low` |
| `METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS` | `2` |
| `METADATA_AGENT_LLM_MAX_REQUESTS_PER_SECOND` | `2` |
| `METADATA_AGENT_REPOSITORY_URL` | `https://repository.staging.openeduhub.net/edu-sharing/rest` |
| `METADATA_AGENT_TEXT_EXTRACTION_API_URL` | `https://text-extraction.staging.openeduhub.net` |
| `METADATA_AGENT_SCREENSHOT_METHOD` | `pageshot` |
| `METADATA_AGENT_CORS_ORIGINS` | *(eure Origins, komma-getrennt)* |

**`SCREENSHOT_METHOD` muss auf Vercel `pageshot` bleiben** — `playwright`
braucht Chromium, das dort nicht vorhanden ist.

**Die beiden Durchsatzgrenzen** entsprechen den Defaults; explizit gesetzt sind
sie in der Vercel-Oberfläche sichtbar, statt im Code nachgeschlagen werden zu
müssen.

## 4. Von Staging auf Produktion umstellen

Drei Variablen, sonst nichts:

| Name | Produktionswert |
|---|---|
| `METADATA_AGENT_B_API_BASE_URL` | `https://b-api.prod.openeduhub.net` |
| `METADATA_AGENT_REPOSITORY_URL` | `https://redaktion.openeduhub.net/edu-sharing/rest` |
| `METADATA_AGENT_TEXT_EXTRACTION_API_URL` | `https://text-extraction.prod.openeduhub.net` |

Die B-API-Endpunktpfade werden aus `B_API_BASE_URL` abgeleitet und müssen nicht
einzeln gesetzt werden.

## 5. Auf B-API AcademicCloud umstellen

Vier Variablen, mehr braucht es nicht — Basis-URL und Endpunktpfad werden
abgeleitet:

```env
METADATA_AGENT_LLM_PROVIDER=b-api-academiccloud
METADATA_AGENT_B_API_ACADEMICCLOUD_MODEL=deepseek-v4-flash
METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS=2
METADATA_AGENT_LLM_MAX_REQUESTS_PER_SECOND=2
```

**Die Rate wird pro Sekunde gesetzt, nicht pro Minute.** `2` entspricht
120 Aufrufen pro Minute. Beide Werte sind zugleich die Defaults der
`b-api`-Gruppe — explizit gesetzt sind sie in der Vercel-Oberfläche sichtbar,
statt im Code nachgeschlagen werden zu müssen.

`METADATA_AGENT_DEFAULT_MAX_WORKERS` muss nicht angefasst werden: es wird
automatisch auf die Parallelitätsgrenze gedeckelt. Beim Start steht das im Log:

```
LLM Provider: b-api-academiccloud
LLM Model: deepseek-v4-flash
Default Workers: 10 → 2 (limit of b-api)
LLM Throughput: max 2 in flight, max 2 req/s
```

`LLM_VERBOSITY` und `LLM_REASONING_EFFORT` gehen nur an `gpt-5`/`o1`/`o3`/`o4`.
`deepseek-v4-flash` bekommt sie nicht — stehen lassen schadet nicht, wirkt
aber auch nicht.

> ⏱️ **Laufzeit beachten.** Gegen das laufende Deployment gemessen
> (2026-08-12): eine Erschließung mit 50 Feldern brauchte mit
> `deepseek-v4-flash` **32,4 s** im einen und **89,6 s** im anderen Lauf. Die
> Streuung kommt von der Warteschlange am Gateway. Siehe „Was Vercel nicht kann".

## 6. Nur bei nativem OpenAI statt B-API

| Name | Wert |
|---|---|
| `METADATA_AGENT_LLM_PROVIDER` | `openai` |
| `OPENAI_API_KEY` | *(Key, Sensitive)* |
| `METADATA_AGENT_OPENAI_MODEL` | `gpt-4o-mini` |
| `METADATA_AGENT_OPENAI_API_BASE` | `https://api.openai.com/v1` *(oder ein eigenes Gateway)* |
| `METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS` | `10` |
| `METADATA_AGENT_LLM_MAX_REQUESTS_PER_SECOND` | `0` |

`0` schaltet die Ratenbegrenzung ab — OpenAI vergibt weit höhere Kontingente pro
Konto und sagt in der 429-Antwort selbst, wie lange zu warten ist.

---

## Alles in einem Block

Zum Einfügen über **Import .env** in der Vercel-Oberfläche:

```env
B_API_KEY=
WLO_GUEST_USERNAME=
WLO_GUEST_PASSWORD=
METADATA_AGENT_LLM_PROVIDER=b-api-academiccloud
METADATA_AGENT_B_API_BASE_URL=https://b-api.staging.openeduhub.net
METADATA_AGENT_B_API_OPENAI_MODEL=gpt-5.6-luna
METADATA_AGENT_B_API_ACADEMICCLOUD_MODEL=deepseek-v4-flash
METADATA_AGENT_LLM_VERBOSITY=low
METADATA_AGENT_LLM_REASONING_EFFORT=low
METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS=2
METADATA_AGENT_LLM_MAX_REQUESTS_PER_SECOND=2
METADATA_AGENT_DEFAULT_MAX_WORKERS=10
METADATA_AGENT_REQUEST_TIMEOUT=60
METADATA_AGENT_REPOSITORY_URL=https://repository.staging.openeduhub.net/edu-sharing/rest
METADATA_AGENT_TEXT_EXTRACTION_API_URL=https://text-extraction.staging.openeduhub.net
METADATA_AGENT_TEXT_EXTRACTION_DEFAULT_METHOD=simple
METADATA_AGENT_SCREENSHOT_METHOD=pageshot
METADATA_AGENT_CORS_ORIGINS=*
```

Die drei leeren Werte oben müssen gefüllt werden, `CORS_ORIGINS` solltet ihr auf
eure Domains einschränken.

---

## Was Vercel nicht kann

| | |
|---|---|
| **Playwright-Screenshots** | Kein Chromium in der Laufzeit → nur `pageshot` |
| **Lange Requests** | `vercel.json` deklariert `maxDuration: 60` |

## Laufzeit

Mit `LLM_MAX_CONCURRENT_REQUESTS=2` laufen 50 Feld-Extraktionen zu zweit statt zu
zehnt. Am laufenden Deployment gemessen (2026-08-12), je zwei Läufe:

| Provider / Modell | Läufe |
|---|---|
| `b-api-academiccloud` / `deepseek-v4-flash` | **32,4 s** · **89,6 s** |
| `b-api-academiccloud` / `openai-gpt-oss-120b` | 53,1 s |

**Die Streuung ist das eigentliche Thema, nicht der Mittelwert.** Sie kommt von
der Warteschlange am Gateway: dasselbe Modell mit derselben Aufgabe braucht mal
32, mal 90 Sekunden, je nach Auslastung der AcademicCloud.

> **Zum `maxDuration: 60`:** der 89,6-Sekunden-Lauf kam mit `200` zurück. Die in
> `vercel.json` deklarierte Grenze wird auf diesem Deployment also offenbar nicht
> durchgesetzt — die Legacy-`builds`-Konfiguration und der Plan spielen da
> hinein. Verlasst euch nicht darauf, in beide Richtungen: geprüft ist nur, dass
> **ein** Lauf mit 89,6 s durchging.

Wer kürzere und vor allem gleichmäßigere Laufzeiten braucht:

1. **`b-api-openai` mit `gpt-5.6-luna`** — 25,2 s im Vergleichslauf, gleiche B-API
2. `METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS` erhöhen — die AcademicCloud weist
   ab 3 parallel mit `429` ab, hier ist wenig zu holen
3. `METADATA_AGENT_LLM_REASONING_EFFORT=none` — rund 40 % schneller, wirkt aber
   **nur** bei der GPT-5-Serie, nicht bei `deepseek-v4-flash`
4. Auf Docker/Kubernetes ausweichen (siehe [DEPLOYMENT.md](DEPLOYMENT.md))
