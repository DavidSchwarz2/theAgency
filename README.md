# theAgency

**AI Development Pipeline Orchestrator** — koordiniert mehrere KI-Agenten in konfigurierbaren Pipelines und liefert strukturierte Handoffs zwischen den Schritten.

Ein Pipeline-Run startet OpenCode-Agenten sequenziell: jeder Agent bekommt den Output seines Vorgängers als Kontext, erledigt seinen Teil und übergibt das Ergebnis weiter.

## Features

- **Pipeline Engine** — sequentielle Multi-Agent-Pipelines mit strukturierten Handoffs
- **Agenten-Registry** — YAML-konfigurierte Agenten, hot-reloaded
- **Approval Gates** — optionale manuelle Freigabe-Schritte mit Erinnerungsfunktion
- **Conflict Detection** — verhindert gleichzeitige Pipeline-Runs im selben Arbeitsverzeichnis
- **Audit Trail** — vollständiges Log aller Events pro Pipeline
- **Web Dashboard** — Echtzeit-Übersicht aller Pipelines, Approvals und Agenten-Output
- **Pipeline-Templates** — im UI verwaltbar, YAML-basiert
- **Arbeitsverzeichnis** — pro Run konfigurierbar, lokale Agenten werden automatisch erkannt
- **GitHub-Issue-Kontext** — Issue-URL als Kontext für einen Pipeline-Run nutzbar
- **Freie Agenten-Komposition** — eigene Schritt-Sequenz direkt im UI zusammenstellen
- **Pro-Schritt Modellauswahl** — jeder Agent kann ein eigenes LLM verwenden

## Stack

| Schicht | Technologie |
|---------|-------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy async, SQLite, Alembic |
| Frontend | React 19, TypeScript, Vite, TanStack Query, Tailwind CSS |
| Toolchain | mise, uv, npm, NX |

---

## Voraussetzungen

- [mise](https://mise.jdx.dev/) — `brew install mise`
- Node.js und Python werden automatisch von mise verwaltet

---

## Setup

```bash
git clone https://github.com/DavidSchwarz2/theAgency.git
cd theAgency

# Toolchain + alle Dependencies installieren
mise install && mise run deps

# Backend .env anlegen und LLM-Provider konfigurieren
cp backend/.env.example backend/.env
```

In `backend/.env` den LLM-Provider setzen:

```env
LLM=gemini        # gemini | openai | anthropic | gcp_gemini
```

---

## Starten

```bash
# Backend + Frontend parallel (empfohlen)
mise run dev

# Einzeln
mise run dev-backend   # http://localhost:8000
mise run dev-frontend  # http://localhost:5173
```

| URL | Beschreibung |
|-----|-------------|
| `http://localhost:5173` | Web Dashboard |
| `http://localhost:5173/audit` | Audit Trail |
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/redoc` | ReDoc |

---

## Konfiguration

Alle Konfiguration liegt in `backend/config/` und wird **hot-reloaded** — kein Neustart nötig.

### `agents.yaml` — verfügbare Agenten

```yaml
agents:
  - name: developer
    description: Implements features following TDD.
    opencode_agent: developer
```

### `pipelines.yaml` — Pipeline-Templates

```yaml
pipelines:
  - name: quick_fix
    description: Developer implements, reviewer validates.
    steps:
      - agent: developer
        description: Implement the fix.
      - agent: senior_reviewer
        description: Review the fix.
```

Approval Gates werden direkt im Template als Schritt-Typ `approval` definiert.

### Mitgelieferte Pipelines

| Name | Schritte |
|------|---------|
| `full_feature` | Product Owner → Architect → Designer → Developer → Reviewer → QA → Issue Creator |
| `quick_fix` | Developer → Senior Reviewer |
| `issue_only` | Issue Creator |

### Mitgelieferte Agenten

`product_owner`, `architect`, `designer`, `developer`, `senior_reviewer`, `qa`, `issue_creator`

---

## Pipeline starten (REST API)

```bash
curl -X POST http://localhost:8000/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "quick_fix",
    "prompt": "Fix the login button not responding on mobile"
  }'
```

Optional: Arbeitsverzeichnis und GitHub-Issue-Kontext angeben:

```bash
curl -X POST http://localhost:8000/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "full_feature",
    "prompt": "Add dark mode",
    "working_dir": "/path/to/my/project",
    "github_issue_url": "https://github.com/org/repo/issues/42"
  }'
```

---

## Tests

```bash
# Backend-Tests (pytest)
npx nx run backend:test

# Frontend-Typecheck
npx nx run frontend:type-check

# Lint + Typecheck + Tests für alle Projekte
npx nx run-many -t lint type-check test
```
