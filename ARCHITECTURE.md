# Kalnur backend architecture

Kalnur is a backend for authenticated nutrition tracking. It treats food-image
analysis as an explicit pipeline and keeps personalised coaching separate from
the deterministic storage and nutrition-calculation work.

```text
Native or web client
        |
        v
FastAPI API  -- verifies Supabase access tokens
        |
        +-- Food logging orchestration
        |     |
        |     +-- vision detection (default: GPT-4o)
        |     +-- segmentation (default: SAM 2 service)
        |     +-- depth / portion service (Depth Anything V2)
        |     +-- Nigerian-food matching and nutrient scaling
        |
        +-- Kally coaching
        |     +-- meal history and nutrition trends
        |     +-- structured tools for food and progress questions
        |
        +-- Supabase
              +-- Auth
              +-- PostgreSQL meal and user data
              +-- food knowledge base and vector search
```

## Boundaries

### Client to API

Clients send bearer tokens to the FastAPI API. They must never receive a
Supabase service-role key, model-provider key, or operations key.

### API to Supabase

The API uses a server-only service-role key. The supplied
`db/enable_rls.sql` enables RLS and revokes direct Data API access for client
roles so that the API remains the policy enforcement boundary.

### API to model and GPU services

Provider keys and Modal URLs are deployment secrets. The API invokes them from
the server; a client should not be able to invoke a paid model or GPU worker
directly.

## Orchestration, not a black box

The system has specialised AI-assisted stages:

- vision recognises foods and cooking context;
- segmentation and depth supply geometry for portion estimates;
- nutrition retrieval maps food names to structured nutrient records;
- Kally uses saved, user-scoped results for coaching.

Each stage has a defined contract, which makes it possible to evaluate changes
across accuracy, latency, and cost. Experimental comparisons of Claude/SAM 3
against the default GPT-4o/SAM 2 path are intentionally kept separate from the
stable runtime contract until validated with labelled, weighed meal data.

## Deployment notes

- Set explicit `ALLOWED_ORIGINS` for browser clients.
- Keep `OPERATIONS_API_KEY` set before enabling benchmark routes.
- Apply all schema migrations followed by `db/enable_rls.sql` to every new
  Supabase project.
- Store provider credentials in the deployment platform's secret manager, not
  in repository files or client builds.
