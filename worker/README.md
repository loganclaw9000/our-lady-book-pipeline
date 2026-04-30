# Reader feedback Worker

Cloudflare Worker that lets unauthenticated visitors of the gh-pages reader
site submit feedback. The Worker accepts a JSON POST and creates a labeled
GitHub Issue on this repo using a server-side PAT — visitors never need a
GitHub account.

## Deploy (one-time, ~5 minutes)

Prereqs: a Cloudflare account (free tier is fine), `node`, and `npm`.

```sh
cd worker
npm install -g wrangler
wrangler login                                 # opens browser to authenticate
wrangler secret put GITHUB_PAT                 # paste a fine-grained PAT
wrangler deploy
```

The deploy prints a URL like:

```
Deployed our-lady-feedback to https://our-lady-feedback.<your-cf-subdomain>.workers.dev
```

Copy that URL into `docs/_config.yml` under `feedback_worker_url:` (or set the
env var that `scripts/render_reader.sh` reads — see that script for the
current convention) and re-run `scripts/render_reader.sh` to inject the new
endpoint into all chapter / retrospective pages.

### PAT scope

A fine-grained PAT with these settings is sufficient:

- Resource owner: `loganclaw9000`
- Repository access: only `our-lady-book-pipeline`
- Permissions:
  - **Issues: Read and write** — required
  - All others: no access

Expire the PAT every 90 days; rotate via `wrangler secret put GITHUB_PAT`.

### Optional: rate-limit binding

To turn on per-IP rate limiting (1 submission / 30s):

```sh
wrangler kv namespace create FEEDBACK_KV
```

Paste the printed namespace id into the `[[kv_namespaces]]` block in
`wrangler.toml` and re-deploy.

## Smoke-test

```sh
curl -X POST https://our-lady-feedback.<...>.workers.dev/ \
  -H 'Content-Type: application/json' \
  -d '{"chapter":"Chapter 1","kind":"praise / what worked","body":"Worker smoke test."}'
```

Expected: `{"ok":true,"issue_number":N,"url":"https://github.com/.../issues/N"}`.

The created issue lands in the repo with labels `feedback` + `reader`. The
agent reads them via `scripts/read_feedback.sh` (writes
`.planning/feedback/FEEDBACK.md` digest grouped by chapter).

## Failure modes

| Status | Body | Meaning |
|--------|------|---------|
| 400 | `invalid_json` | request body wasn't JSON |
| 400 | `missing_body` | feedback `body` field empty |
| 403 | `origin_not_allowed` | request came from a host not in `ALLOWED_ORIGIN` |
| 413 | `body_too_large` | request exceeded `MAX_BODY_BYTES` |
| 429 | `rate_limited` | per-IP rate limit hit (only when KV bound) |
| 500 | `worker_misconfigured_no_pat` | `wrangler secret put GITHUB_PAT` not run |
| 502 | `github_create_issue_failed` | upstream GitHub call failed (rate limit, PAT expired, etc.) |
