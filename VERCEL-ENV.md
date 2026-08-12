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
| `METADATA_AGENT_LLM_PROVIDER` | `b-api-openai` |
| `METADATA_AGENT_B_API_BASE_URL` | `https://b-api.staging.openeduhub.net` |
| `METADATA_AGENT_B_API_OPENAI_MODEL` | `gpt-5.6-luna` |
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

## 5. Nur bei nativem OpenAI statt B-API

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
METADATA_AGENT_LLM_PROVIDER=b-api-openai
METADATA_AGENT_B_API_BASE_URL=https://b-api.staging.openeduhub.net
METADATA_AGENT_B_API_OPENAI_MODEL=gpt-5.6-luna
METADATA_AGENT_B_API_ACADEMICCLOUD_MODEL=openai-gpt-oss-120b
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
| **Laufzeit über 60 s** | Harte Grenze der Function |

Der zweite Punkt hat mit den Durchsatzgrenzen zu tun: mit
`LLM_MAX_CONCURRENT_REQUESTS=2` dauert eine vollständige Erschließung mit
50 Feldern **25–60 s** und liegt damit nah an der 60-Sekunden-Grenze. Wer
regelmäßig Zeitüberschreitungen sieht, hat drei Möglichkeiten:

1. `METADATA_AGENT_LLM_MAX_CONCURRENT_REQUESTS` erhöhen — reizt die B-API stärker aus
2. `METADATA_AGENT_LLM_REASONING_EFFORT=none` — rund 40 % schneller, verlor im
   Test aber in 2 von 5 Läufen `ccm:oeh_event_begin`
3. Auf Docker/Kubernetes ausweichen, wo es kein Zeitlimit gibt
   (siehe [DEPLOYMENT.md](DEPLOYMENT.md))
