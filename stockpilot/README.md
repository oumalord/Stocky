# StockPilot — Inventory Foundation and Count/Variance Slice

**Status:** Django foundation and the stock-count/variance vertical slice are implemented. The generated migrations and SQLite development path have been exercised. This is not a production-ready or complete implementation of the broader product brief.

## Implemented
Multi-tenant organisations and branches, email/password session auth, roles and per-branch permissions,
products/categories/units, locations, the append-only stock ledger with cached balances, idempotent posting,
reversals, append-only audit trail, OpenAPI docs, Docker dev stack, stock-count snapshots, blind-count entry,
movement-aware count reconciliation, count submission, and a tenant-scoped variance register.

Count and variance design, the entity relationship diagram, and continuation checklist are in
[`docs/architecture-and-progress.md`](docs/architecture-and-progress.md).

Still not implemented: investigation cases/evidence, recount workflow, approval policies and adjustment posting,
dashboard analytics, exports, alerts, integrations, MFA, invitations, batch/serial tracking, offline counting,
supplier/purchasing/transfer/sales modules, billing, or production deployment/monitoring.

## Run with Docker
```bash
cp .env.example .env            # edit the secrets
docker compose run --rm backend python manage.py makemigrations core tenancy accounts catalog inventory audit
docker compose up --build       # migrates, then serves http://localhost:8000
docker compose exec backend python manage.py seed_demo      # DEMO data, dev only
```
Docs: http://localhost:8000/api/docs/ (login required). Health: /health/.

## Run tests (PostgreSQL, includes the concurrency tests)
```bash
docker compose up -d db
docker compose run --rm backend python manage.py test tests -v 2
```
Without PostgreSQL: `USE_SQLITE=1 python manage.py test tests` (concurrency tests are skipped).
The count/variance tests also run under SQLite, but SQLite does not prove PostgreSQL row-lock behavior.

## Local without Docker
```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip freeze > requirements.lock
python manage.py makemigrations core tenancy accounts catalog inventory audit && python manage.py migrate
python manage.py runserver
```

On Windows PowerShell, from the workspace root:
```powershell
$env:USE_SQLITE = "1"
Set-Location stockpilot\backend
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```
In a second terminal:
```powershell
Set-Location stockpilot\frontend
npm run start -- --host 127.0.0.1 --proxy-config proxy.conf.json
```
Commit generated migration files with the model changes that require them.

## Deploy to Vercel with Neon
One Vercel project, **Root Directory = `stockpilot`**. [`vercel.json`](vercel.json) builds Angular to static files and serves Django from [`api/index.py`](api/index.py); the browser calls `/api/...` on the same origin, so no CORS is needed.

1. In Neon, copy both connection strings and keep them out of the repo: **direct** (host without `-pooler`) for migrations, **pooled** for Vercel at runtime. Migrating through the pooler drops the connection mid-DDL.
2. Create the schema and the first admin from your machine, with the direct `DATABASE_URL` set for that shell only:
   ```powershell
   $env:DATABASE_URL = "<neon connection string>"; $env:DJANGO_SECRET_KEY = "<any value>"
   $env:DJANGO_SETTINGS_MODULE = "config.settings.prod"; $env:SECURE_SSL_REDIRECT = "false"
   Set-Location backend
   .\.venv\Scripts\python.exe manage.py migrate
   $env:STOCKPILOT_ADMIN_PASSWORD = "<password>"
   .\.venv\Scripts\python.exe manage.py create_org_admin you@example.com --organisation "Your Company"
   ```
3. In Vercel project settings, set `DATABASE_URL` (pooled), a long random `DJANGO_SECRET_KEY`, and `DJANGO_ALLOWED_HOSTS` (your custom domain, if any). `VERCEL_URL` hosts are trusted automatically.
4. Deploy. Check `/health/`, then sign in.

Not verified on Vercel or Neon yet. Login throttling uses per-instance memory, so it is weak on serverless. Celery workers and beat do not run on Vercel. Never run `seed_demo` against Neon.

## Key rules
- Every write to stock goes through `apps/inventory/services/ledger.py::post_movement`.
- `POST /api/v1/movements/` requires an `Idempotency-Key` header; replays return the original (HTTP 200).
- ADJUSTMENT and REVERSAL cannot be posted directly; adjustments will need approvals (Slice C).
- Audit events and ledger rows are append-only (ORM guard plus PostgreSQL trigger).
- Count quantities are reconciled against ledger rows committed after the count snapshot and no later than each line's recorded count time.
- Submitted counts are immutable through the API; variance values preserve snapshot, counted quantity, cost, retail, and count timestamps.

## Known limitations
No batch/serial tracking, FIFO costing, stock valuation, invitations, password reset, MFA or file uploads yet.
`seed_demo` uses a fixed dev-only password and refuses to run unless DEBUG is on.
# Frontend (Angular) — Slice A files

Angular could not be scaffolded or built in the authoring environment (no network), so these are source files to drop into a fresh project:
```bash
npm i -g @angular/cli
ng new frontend --standalone --routing --style=css   # accept defaults
# add Tailwind following the current Angular guide at tailwindcss.com/docs/installation/framework-guides/angular
# copy src/app/** and proxy.conf.json from this folder over the generated project (merge app.config.ts)
ng serve --proxy-config proxy.conf.json
```
Included: AuthService (session login, CSRF, active organisation), HTTP interceptor, route guard, login form.
Not yet built: app shell, dashboard, products and movements pages (next batch).
