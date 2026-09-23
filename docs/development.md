# Development and troubleshooting

## Local setup

Create a Python virtual environment, install the locked backend requirements and development extras, then install the locked frontend dependencies:

```bash
python -m venv .venv
# Activate .venv for your shell first.
pip install -r backend/requirements.lock -e './backend[dev]'
cd frontend
npm ci
```

For a complete local stack, run `python scripts/dev-env.py` and `docker compose up --build -d`. The generated development environment uses unique local secrets and explicitly enables the mock provider.

## Checks

```bash
pytest tests -q
ruff check backend cli scripts tests
cd frontend
npm run lint
npm run typecheck
npm run build
```

Tests use SQLite unless `TEST_DATABASE_URL` points to an empty dedicated PostgreSQL database. The suite clears application tables in that database; do not reuse a production database.

## Troubleshooting

Use `docker compose logs api worker migrate` for container diagnostics and `sudo farstarnexa doctor` on an installed host. If a delivery is marked `unknown`, reconcile the provider before taking any resend action. If an update has migrated the database and failed, follow the recovery procedure in `docs/operations.md` rather than starting old code against an incompatible schema.

Do not add generated `frontend/dist`, `frontend/node_modules`, `.venv`, runtime state, logs, database dumps or `.env` files to Git. Keep test credentials local and disposable.
