# Security policy

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability or exposed
credential. Contact the maintainer privately with a concise reproduction and
the affected component.

## Deployment requirements

- Keep `.env` files, service-role keys, provider keys, VAPID private keys, and
  Modal endpoint credentials out of version control.
- Use a separate Supabase project for each environment.
- Apply `db/enable_rls.sql` before connecting an untrusted client to Supabase.
- Keep `SUPABASE_SERVICE_ROLE_KEY` on the server only. Never ship it in a
  mobile app, browser bundle, or public repository.
- Set a narrow `ALLOWED_ORIGINS` list for browser deployments.
- Keep `OPERATIONS_API_KEY` set if benchmark endpoints are enabled; those
  routes can invoke paid model providers.
- Rotate credentials immediately if they are ever committed or logged.
