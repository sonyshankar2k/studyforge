# StudyForge

**A collaborative clinical study design editor.** Teams build a clinical trial protocol together (study details, arms, objectives and endpoints) with live updates, conflict detection and a full audit trail. Upload a protocol PDF and AI proposes its arms, objectives and endpoints for you to review. Define eligibility criteria and the Schedule of Activities, and export the design as CDISC USDM-shaped JSON.

Built with **Angular 22 · Python · FastAPI · PostgreSQL · Redis · arq · Claude · WebSockets · Docker**.

---

## Features

| Feature | How it works |
|---|---|
| **Authentication** | Sign up / sign in with email and password. Passwords are hashed with Argon2; the API issues signed JWTs; every REST endpoint and the WebSocket require a valid token |
| **Real-time collaboration** | WebSocket per study; when anyone saves, everyone viewing sees a notification and the latest data |
| **Optimistic concurrency** | Every record has a `version`. Saves send the version they read; the API returns **409 Conflict** if someone saved first |
| **Conflict resolution UI** | On 409 the user sees *yours vs theirs* side by side and chooses **Keep mine** or **Use theirs** |
| **Field-level saves** | Only changed fields are sent, so two people editing different fields never overwrite each other |
| **Stale-state recovery** | Unsaved edits are never silently overwritten; a banner warns when the data changed underneath you. After a dropped connection, the app reconnects with backoff and resyncs |
| **Audit trail** | Every create/update/delete is recorded: who (the signed-in user's email), when, old → new value (ALCOA+ style) |
| **Safe undo** | Deleting shows an **Undo** action that re-creates the item as a new, audited change |
| **Typed Reactive Forms** | Conditional validation (dose required for experimental arms) and async validation (acronym uniqueness checked against the API) |
| **Shared validation rules** | The same rules are enforced by Pydantic on the server, so UI and API never disagree |
| **AI protocol digitization** | Upload a protocol PDF; a background job extracts arms (type, dose, planned size), objectives and endpoints with **Claude** (structured tool output validated by Pydantic), or with a free rule-based parser when no API key is set |
| **Long-running jobs** | Jobs run in a separate **arq** worker over **Redis**, with live progress on a progress bar, **cancel** (cooperative checkpoints plus task abort), automatic **retries with exponential backoff** for transient errors, immediate failure with a clear message for permanent ones, and a manual **Try again** |
| **Idempotent uploads** | Each upload carries an `Idempotency-Key`; retrying after a network error returns the original job instead of starting (and paying for) a duplicate |
| **Human in the loop** | AI output is only a proposal: a person reviews it, unticks anything wrong, and adds the rest. Each added item's audit entry records which file and job it came from |
| **Eligibility criteria** | Inclusion / exclusion lists numbered I1, I2… / E1, E2…, kept gapless after deletes. Reorder by drag and drop (Angular CDK) or with move buttons that work from the keyboard; the new order shows at once and rolls back if the save fails |
| **Schedule of Activities** | Visits (study day and visit window) across the top, activities down the side; click a cell to plan it. Optimistic updates with rollback, and the API takes the wanted state (`"planned": true`) rather than "toggle", so repeats are harmless. Other users' grids update live |
| **USDM export** | Download the whole design as JSON using CDISC USDM entity names (StudyDesign, StudyArm, Objective, Endpoint, EligibilityCriterion, Encounter, Activity, ScheduleTimeline, ScheduledActivityInstance) |
| **Scales across instances** | Live events go through Redis pub/sub, so the worker and any number of API instances can push updates to every open browser |

## Tech stack

- **Frontend:** Angular 22, standalone components, Signals, RxJS, typed Reactive Forms, functional guards and interceptors, Angular Material 3, Vitest
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic, asyncpg, PyJWT, Argon2 (pwdlib), pytest
- **Data and jobs:** PostgreSQL 17, Redis 8 (job queue + pub/sub), arq worker, pypdf, Anthropic SDK
- **Testing:** pytest, Schemathesis (OpenAPI contract tests), Vitest, Playwright (end-to-end)
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

Demo accounts (created automatically for local runs): `alice@studyforge.dev`, `bob@studyforge.dev`, `carol@studyforge.dev`, password `studyforge`.

1. Open http://localhost:8080 in **two browser tabs** side by side. Each tab keeps its own sign-in.
2. On the sign-in page, click **Alice** in one tab and **Bob** in the other.
3. Open the same study in both.
4. Bob changes a field and saves → Alice gets a live notification.
5. Alice edits the title *before* refreshing, then saves → the conflict dialog appears.
6. Open the **Audit trail** tab to see every change.

### Try AI protocol digitization

1. Open a study and go to the **AI digitize** tab.
2. Upload [`samples/BREATHE-2_protocol_synopsis.pdf`](samples/BREATHE-2_protocol_synopsis.pdf), a short fictional protocol.
3. Watch the progress bar (open the same study in a second tab: it updates there too).
4. Click **Review results**, untick anything you don't want, and click **Add … selected to the study**.
5. Try **Cancel** while a job runs, then **Try again**.

### Try the study design tools

1. Open **BREATHE-1**. The demo study comes with criteria and a schedule.
2. **Eligibility** tab: add a criterion, drag one to a new position, and watch the numbers update.
3. **Schedule** tab: add a visit (e.g. *Week 16*, day *113*), tick some cells. Open the same study as Bob in another tab: his grid updates live.
4. Click **Export USDM** to download the design as JSON.

**Using Claude:** create a file named `.env` next to `docker-compose.yml` containing `ANTHROPIC_API_KEY=your-key`, then `docker compose up --build`. Without a key the rule-based parser is used, which only understands simple `Arm A: …` / `Primary objective: …` layouts like the sample.

---

## Development setup (hot reload)

Run the database in Docker and the code on your machine. Commands are the same on **Mac (Terminal)** and **Windows (PowerShell)**.

**1. Start PostgreSQL and Redis**

```bash
docker compose up -d db redis
```

**2. Create the database tables and start the API** (new terminal)

```bash
cd api
uv sync
uv run alembic upgrade head
uv run fastapi dev app/main.py
```

API runs on http://localhost:8000 and reloads when you save a `.py` file.

**3. Start the background worker** (new terminal)

```bash
cd api
uv run arq app.worker.WorkerSettings
```

**4. Start the Angular app** (new terminal)

```bash
cd web
npm install
npm start
```

Open http://localhost:4200. `proxy.conf.json` forwards `/api` and `/ws` to the API.

---

## Tests

```bash
# Backend (61 tests: auth, CRUD, 409 conflicts, validation, audit trail, migrations,
#          digitization jobs, retries, idempotency, cancel, extractors)
cd api
uv run pytest -v
uv run ruff check .

# Frontend unit tests (Vitest)
cd web
npx ng test --watch=false

# End-to-end tests (Playwright): start the stack first with `docker compose up -d --build`
cd web
npx playwright install chromium   # once
npm run e2e
```

### What each kind of test catches

| Tests | Where | What they prove |
|---|---|---|
| Unit + integration (pytest, Vitest) | `api/tests`, `web/src/**/*.spec.ts` | Business rules: versions and 409s, numbering, idempotency, retries, optimistic UI with rollback |
| **Contract** (Schemathesis) | `api/tests/test_contract.py` | Generates hundreds of requests from `/openapi.json` (odd values, nulls, huge numbers…) and checks no request causes a 500 and every response matches the documented schema |
| **End-to-end** (Playwright) | `web/e2e` | Real browser, real stack: sign-in, two users editing live, the conflict dialog, AI digitization, criteria reorder, live schedule updates, USDM download |

The contract tests earned their place on day one. They found that timestamps lost their time zone on SQLite, that an id larger than 64 bits crashed the API, that `null` in a PATCH reached the database, and that some 422 errors didn't match the documented error shape. The end-to-end tests found two forms that reloaded the page instead of saving.

CI runs on every push (`.github/workflows/ci.yml`): backend lint and tests (including contract tests), frontend tests and build, an **e2e** job that starts the whole stack in Docker and runs Playwright, and a **migrations** job that applies the migrations to a real PostgreSQL, checks that the models and migrations match (`alembic check`), then downgrades and upgrades again.

---

## Database migrations

The schema is managed with **Alembic** (`api/migrations`). The Docker image runs `alembic upgrade head` before the API starts.

```bash
cd api
uv run alembic upgrade head                           # apply all migrations
uv run alembic revision --autogenerate -m "add x"     # after changing app/models.py
uv run alembic downgrade -1                           # undo the last migration
```

Always review an autogenerated migration before committing it. If you change a model and forget the migration, CI fails.

---

## Security notes

- **Passwords** are hashed with Argon2 and never returned by the API.
- **Login errors** are identical for "unknown email" and "wrong password", so the endpoint can't be used to discover accounts.
- **Tokens** are short-lived JWTs (8 hours) signed with `JWT_SECRET`. The default secret is for local development only; set a long random value anywhere real.
- **Token storage:** the Angular app keeps the token in `sessionStorage` (one sign-in per tab, cleared when the tab closes). Any script on the page could read it, so the production-grade option is an HttpOnly, Secure, SameSite cookie set by the API.
- **WebSockets** can't carry an `Authorization` header from the browser, so the token is passed as `?token=`; the server closes the connection with code 1008 if it's invalid.
- **Open redirects** are blocked: the `returnUrl` after login must be an in-app path.
- **Uploads** are checked by their content (a `.pdf` must start with `%PDF-`), limited to 10 MB, stored under generated names (never the user's filename), and read back only through a path check.
- **Prompt input:** protocol text is sent to Claude inside delimiters, and the answer must fit a strict schema, so instructions hidden in a document can't make the app do anything except propose study items for review.

---

## How a digitization job works

```
Browser ── POST /digitize (file + Idempotency-Key) ──> API ── saves file, creates job row ──> Redis queue
   ▲                                                                                              │
   │  WebSocket: job progress                                                                     ▼
   └──────── API ◀── Redis pub/sub ◀── progress events ◀── Worker: read PDF → Claude → validate ──┘
```

| Situation | What happens |
|---|---|
| Rate limit, timeout, network error, 5xx | Retried automatically after 5s, 10s… (up to 3 attempts); the stage text shows the countdown |
| Unreadable or image-only PDF, bad API key, 4xx | Fails at once with a message saying what to fix (retrying would fail the same way) |
| Model output doesn't match the schema | Treated as transient and retried |
| User clicks **Cancel** while queued | Cancelled immediately; if a worker picks it up later, it skips it |
| User clicks **Cancel** while running | Worker stops at the next checkpoint and discards the result |
| Same upload sent twice (same key) | Second request returns the first job; no duplicate work |
| Worker queue down | The job is marked failed with "queue unavailable"; **Try again** re-queues it |

---

## Project structure

```
studyforge/
├── api/                      FastAPI backend
│   ├── app/
│   │   ├── main.py           App setup, WebSocket endpoint (token-checked)
│   │   ├── security.py       Argon2 password hashing, JWT create/verify
│   │   ├── deps.py           current_user dependency (401 if no valid token)
│   │   ├── models.py         SQLAlchemy tables (version columns, audit_log)
│   │   ├── schemas.py        Pydantic contracts (request/response)
│   │   ├── editing.py        Version check, change diff, audit, broadcast
│   │   ├── realtime.py       WebSocket hub
│   │   ├── events.py         Event bus: Redis pub/sub -> WebSockets
│   │   ├── queue.py          Enqueue / abort background jobs (arq)
│   │   ├── worker.py         arq worker entry point
│   │   ├── storage.py        Uploaded file storage (local now, S3 later)
│   │   ├── digitize/         Job pipeline, PDF text, Claude + rule-based extractors
│   │   ├── routers/auth.py   Register, login, me
│   │   ├── routers/studies.py  REST endpoints (all require sign-in)
│   │   ├── routers/jobs.py   Upload, job status, cancel, retry, apply
│   │   ├── routers/design.py Criteria, visits, activities, schedule cells, USDM export
│   │   ├── errors.py         422 errors in FastAPI's documented shape
│   │   └── seed.py           Demo users and study
│   ├── migrations/           Alembic migrations
│   └── tests/                pytest
├── web/                      Angular frontend
│   └── src/app/
│       ├── auth/             Sign-in / create-account page
│       ├── core/             Auth service + guard + interceptor, API client, WebSocket, validators
│       └── studies/          List, detail, eligibility, schedule grid, AI digitize panel, dialogs
│   └── e2e/                  Playwright end-to-end tests
├── samples/                  Fictional protocol PDF for the demo (+ the script that makes it)
├── docker-compose.yml        db, redis, api, worker, web
└── .github/workflows/ci.yml
```

## API overview

All `/api/studies`, `/api/arms` and `/api/objectives` endpoints require `Authorization: Bearer <token>`. In Swagger (`/docs`), click **Authorize** and sign in with a demo account.

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/register` | Create an account, returns a token |
| POST | `/api/auth/login` | OAuth2 password form (`username` = email), returns a token |
| GET | `/api/auth/me` | The signed-in user |
| GET | `/api/studies` | List studies |
| POST | `/api/studies` | Create a study |
| GET | `/api/studies/{id}` | Study with arms and objectives |
| PATCH | `/api/studies/{id}` | Body must include `version`; 409 on conflict |
| GET | `/api/studies/acronym-available?acronym=` | Async validator check |
| GET | `/api/studies/{id}/audit` | Audit trail, newest first |
| POST / PATCH / DELETE | `/api/studies/{id}/arms`, `/api/arms/{id}` | Delete takes `?version=` |
| POST / PATCH / DELETE | `/api/studies/{id}/objectives`, `/api/objectives/{id}` | Same pattern |
| POST | `/api/studies/{id}/digitize` | Multipart `file` + `Idempotency-Key` header. 202 new job; 200 + `Idempotent-Replayed: true` for a repeat |
| GET | `/api/studies/{id}/jobs` | Recent digitization jobs |
| GET | `/api/jobs/{id}` | Status, progress, stage, error, result |
| POST | `/api/jobs/{id}/cancel` | Cancel a queued or running job |
| POST | `/api/jobs/{id}/retry` | Re-run a failed or cancelled job |
| POST | `/api/jobs/{id}/apply` | `{"arms": [0, 2], "objectives": [0]}`: add the reviewed items |
| GET / POST | `/api/studies/{id}/criteria` | Eligibility criteria (I1…, E1…) |
| PATCH / DELETE | `/api/criteria/{id}` | Delete renumbers the rest |
| PUT | `/api/studies/{id}/criteria/order` | `{"category": "inclusion", "ids": [3, 1, 2]}`; 409 if the list changed meanwhile |
| GET | `/api/studies/{id}/schedule` | Visits, activities and planned cells |
| POST / PATCH / DELETE | `/api/studies/{id}/encounters`, `/api/encounters/{id}` | Visits (study day, window) |
| POST / PATCH / DELETE | `/api/studies/{id}/activities`, `/api/activities/{id}` | Activities |
| PUT | `/api/studies/{id}/schedule/cells` | `{"encounter_id": 1, "activity_id": 2, "planned": true}` (idempotent) |
| GET | `/api/studies/{id}/usdm` | USDM-shaped JSON of the whole design |
| WS | `/ws/studies/{id}?token=` | Change events and job progress for one study |

---

## Roadmap

- [x] **Week 1:** JWT authentication · Alembic migrations
- [x] **Week 2:** AI protocol digitization: background jobs (arq + Redis) with progress, retries, idempotency keys and cancellation; Claude extraction; review-before-apply; Redis pub/sub for live events
- [x] **Week 3:** Eligibility criteria and Schedule of Activities (CDISC USDM entity names) · USDM export · Playwright end-to-end tests · Schemathesis contract tests
- [ ] **Week 4:** Uploaded files to S3 · Terraform (S3, ECR) · Kubernetes manifests · OpenTelemetry tracing · SonarCloud quality gate

*Demo data is fictional and for illustration only.*
