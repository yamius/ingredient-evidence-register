# Vallydia Ingredient-Evidence Register — read-only API

A small, read-only HTTP API over the dataset. No database, no writes, no auth: it loads the
generated `data/` files into memory and serves them. Every response carries an `attribution`
string and a `source_url` back to [vallydia.com](https://vallydia.com) — reuse is CC-BY-4.0.

**Scope firewall:** the API exposes only what is in the dataset — appearance/evidence fields
and neutral chemical identifiers. No dosing, administration or commerce data, anywhere.

## Run locally

```bash
pip install -r api/requirements.txt
uvicorn api.app:app --reload
# interactive docs: http://127.0.0.1:8000/docs
```

Or with Docker:

```bash
docker build -t vallydia-register-api -f api/Dockerfile .
docker run -p 8000:8000 vallydia-register-api
```

## Endpoints

| Method & path | What it returns |
|---|---|
| `GET /` | Service metadata + endpoint index |
| `GET /compounds?class=&is_cosmetic=&limit=&offset=` | List of compounds (full records), paginated |
| `GET /compounds/{slug}` | One compound (404 if unknown) |
| `GET /grades?slug=&grade=` | Per-outcome grade rows |
| `GET /citations?slug=` | DOI-verified citations with scholarly cross-links |
| `GET /cosmetic-claims?slug=&claim_type=` | Permitted / forbidden claim wordings |
| `GET /identifiers?slug=` | Neutral chemical identifiers |
| `GET /search?q=` | Free-text search over name, slug, synonyms, class, tags |

Every payload:

```json
{
  "attribution": "Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0.",
  "source_url": "https://vallydia.com",
  "count": 1,
  "data": [ ... ]
}
```

The full contract is in [`openapi.yaml`](openapi.yaml) (OpenAPI 3.1); FastAPI also serves it
live at `/openapi.json` with Swagger UI at `/docs`.

## Deploy

Deployment is a manual operator step (accounts/tokens) — see [PUBLISHING.md](../PUBLISHING.md).
The service is stateless and safe to run serverless or scale horizontally; CORS is open for
read. Later it can be listed on RapidAPI for persistent developer integrations.
