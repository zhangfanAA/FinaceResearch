# micro-quant-pipeline backend

Phase 1 is strictly PAPER / DRY-RUN ONLY.

## Run locally

```bash
python -m pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Endpoints

- `GET /health`
- `POST /api/run-once`
- `GET /api/status`
- `GET /dashboard`

No real broker, fund distributor, or exchange execution APIs are implemented in this phase.
