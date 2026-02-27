# theAgency

**AI Development Pipeline Orchestrator** — koordiniert mehrere KI-Agenten (Product Owner, Architect, Developer, Reviewer, QA, ...) in konfigurierbaren Pipelines und liefert strukturierte Handoffs zwischen den Schritten.

## Stack

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy async (SQLite)
- **Frontend**: React 19 + TypeScript + Vite + TanStack Query + Tailwind CSS
- **Toolchain**: mise, uv (Python), npm (Frontend), NX (Monorepo)

---

## Voraussetzungen

- [mise](https://mise.jdx.dev/) installiert (`brew install mise` oder [mise.jdx.dev](https://mise.jdx.dev/))
- Node.js und Python werden automatisch von mise verwaltet

---

## Setup

```bash
# 1. Repo klonen
git clone https://github.com/DavidSchwarz2/theAgency.git
cd theAgency

# 2. Toolchain + alle Dependencies installieren (Node, Python, uv, npm)
mise install && mise run deps

# 3. Backend .env anlegen
cp backend/.env.example backend/.env
```

---

## Starten

```bash
# Backend + Frontend parallel starten (empfohlen)
mise run dev

# Oder einzeln
mise run dev-backend   # Backend  (Port 8000)
mise run dev-frontend  # Frontend (Port 5173)
```

Dann im Browser öffnen:

| URL | Beschreibung |
|-----|-------------|
| `http://localhost:5173` | Web Dashboard (Pipeline-Übersicht + Approvals) |
| `http://localhost:5173/audit` | Audit Trail |
| `http://localhost:8000/docs` | FastAPI Swagger UI |
| `http://localhost:8000/redoc` | FastAPI ReDoc |

---

## Pipelines & Agenten konfigurieren

Die Konfiguration liegt in `backend/config/`:

- **`agents.yaml`** — definiert die verfügbaren Agenten (Name, Beschreibung, OpenCode-Agent-ID)
- **`pipelines.yaml`** — definiert Pipeline-Templates mit geordneten Schritten

Änderungen werden **hot-reloaded** — kein Neustart nötig.

### Beispiel: Pipeline starten (REST API)

```bash
curl -X POST http://localhost:8000/pipelines \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name": "quick_fix", "prompt": "Fix the login button not responding on mobile"}'
```

Vordefinierte Pipelines:

| Name | Beschreibung |
|------|-------------|
| `full_feature` | Product Owner → Architect → Designer → Developer → Reviewer → QA → Issue Creator |
| `quick_fix` | Developer → Senior Reviewer |
| `issue_only` | Issue Creator |

---

## Tests

```bash
# Backend-Tests
npx nx run backend:test

# Frontend-Typecheck
npx nx run frontend:type-check

# Alles auf einmal
npx nx run-many -t lint type-check test
```
