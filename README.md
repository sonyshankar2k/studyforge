# StudyForge

**A collaborative clinical study design editor.** Teams build a clinical trial protocol together (study details, arms, objectives and endpoints) with live updates, conflict detection and a full audit trail.

Built with **Angular 22 · Python · FastAPI · PostgreSQL · WebSockets · Docker**.

---

## Features

| Feature | How it works |
|---|---|
| **Real-time collaboration** | WebSocket per study; when anyone saves, everyone viewing sees a notification and the latest data |
| **Optimistic concurrency** | Every record has a `version`. Saves send the version they read; the API returns **409 Conflict** if someone saved first |
| **Conflict resolution UI** | On 409 the user sees *yours vs theirs* side by side and chooses **Keep mine** or **Use theirs** |
| **Field-level saves** | Only changed fields are sent, so two people editing different fields never overwrite each other |
| **Stale-state recovery** | Unsaved edits are never silently overwritten; a banner warns when the data changed underneath you. After a dropped connection, the app reconnects with backoff and resyncs |
| **Audit trail** | Every create/update/delete is recorded: who, when, old → new value (ALCOA+ style) |
| **Safe undo** | Deleting shows an **Undo** action that re-creates the item as a new, audited change |
| **Typed Reactive Forms** | Conditional validation (dose required for experimental arms) and async validation (acronym uniqueness checked against the API) |
| **Shared validation rules** | The same rules are enforced by Pydantic on the server, so UI and API never disagree |

## Tech stack

- **Frontend:** Angular 22, standalone components, Signals, RxJS, typed Reactive Forms, Angular Material 3, Vitest
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), asyncpg, pytest
- **Data:** PostgreSQL 17 (Redis 8 ready for background jobs)
- **Ops:** Docker Compose, nginx, GitHub Actions CI, Ruff, Prettier

---

## Quick start (Docker, one command)

Requires Docker Desktop running.

```bash
docker compose up --build
```

- App: http://localhost:8080
- API docs (Swagger): http://localhost:8000/docs

Stop with `Ctrl + C`. Remove the database with `docker compose down -v`.

### Try the collaboration demo

1. Open http://localhost:8080 in **two browser windows** side by side.
2. In the top-right **Editing as** menu, pick **Alice** in one window and **Bob** in the other.
3. Open the same study in both.
4. Bob changes a field and saves → Alice gets a live notification.
5. Alice edits the title *before* refreshing, then saves → the conflict dialog appears.
6. Open the **Audit trail** tab to see every change.

---

## Development setup (hot reload)

Run the database in Docker and the code on your machine. Commands are the same on **Mac (Terminal)** and **Windows (PowerShell)**.

**1. Start PostgreSQL and Redis**

```bash
docker compose up -d db redis
```

**2. Start the API** (new terminal)

```bash
cd api
uv sync
uv run fastapi dev app/main.py
```

API runs on http://localhost:8000 and reloads when you save a `.py` file.

**3. Start the Angular app** (new terminal)

```bash
cd web
npm install
npm start
```

Open http://localhost:4200. `proxy.conf.json` forwards `/api` and `/ws` to the API.

---

## Tests

```bash
# Backend (13 tests: CRUD, 409 conflicts, conditional validation, audit trail)
cd api
uv run pytest -v
uv run ruff check .

# Frontend (Vitest)
cd web
npx ng test --watch=false
```

CI runs both on every push (`.github/workflows/ci.yml`).

---

## Project structure

```
studyforge/
├── api/                      FastAPI backend
│   ├── app/
│   │   ├── main.py           App setup, WebSocket endpoint
│   │   ├── models.py         SQLAlchemy tables (version columns, audit_log)
│   │   ├── schemas.py        Pydantic contracts (request/response)
│   │   ├── editing.py        Version check, change diff, audit, broadcast
│   │   ├── realtime.py       WebSocket hub
│   │   ├── routers/studies.py  REST endpoints
│   │   └── seed.py           Demo study
│   └── tests/                pytest
├── web/                      Angular frontend
│   └── src/app/
│       ├── core/             API client, WebSocket (reconnect), validators, models
│       └── studies/          List page, detail page, dialogs (arm, objective, conflict)
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## API overview

| Method | Path | Notes |
|---|---|---|
| GET | `/api/studies` | List studies |
| POST | `/api/studies` | Create a study |
| GET | `/api/studies/{id}` | Study with arms and objectives |
| PATCH | `/api/studies/{id}` | Body must include `version`; 409 on conflict |
| GET | `/api/studies/acronym-available?acronym=` | Async validator check |
| GET | `/api/studies/{id}/audit` | Audit trail, newest first |
| POST / PATCH / DELETE | `/api/studies/{id}/arms`, `/api/arms/{id}` | Delete takes `?version=` |
| POST / PATCH / DELETE | `/api/studies/{id}/objectives`, `/api/objectives/{id}` | Same pattern |
| WS | `/ws/studies/{id}` | Change events for one study |

---

## Roadmap

- [ ] **Week 1:** JWT authentication (replace the demo `X-User` header) · Alembic migrations
- [ ] **Week 2:** AI protocol digitization — upload a protocol PDF to S3; a background job (arq + Redis) extracts arms, objectives and endpoints with an LLM, with progress events, retries, idempotency keys and cancellation
- [ ] **Week 2:** Redis pub/sub for WebSocket events so the API can scale to multiple instances
- [ ] **Week 3:** Eligibility criteria and Schedule of Activities, aligned to the CDISC USDM model · Playwright end-to-end tests · contract tests against the OpenAPI spec
- [ ] **Week 4:** Terraform (S3, ECR) · Kubernetes manifests · OpenTelemetry tracing · SonarCloud quality gate

*Demo data is fictional and for illustration only.*
