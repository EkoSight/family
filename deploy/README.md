# Deploying the Ekosight CEO Agent to Google Cloud Run

This gives your whole team a real `https://…run.app` URL, and is the foundation
for the live Google Workspace integrations (Gmail / Calendar / Drive) and a
native Android build.

There are two paths. Start with **A** to see it live in ~5 minutes; move to **B**
when you want durable, multi-user data.

---

## Prerequisites (once)

1. **Install the gcloud CLI** → https://cloud.google.com/sdk/docs/install
2. `gcloud auth login`
3. A **GCP project with billing enabled**. Note its **Project ID** (not the name).

---

## Path A — Quick public deploy (SQLite, single instance)

Good for a first look and demos. The database lives inside the container, so it
**resets whenever you redeploy** and can't scale past one instance. The deploy
script handles that by pinning to one warm instance.

```bash
# from the repo root
PROJECT_ID=your-project-id ./deploy/deploy.sh
```

It enables the needed APIs, builds the image with Cloud Build, deploys to Cloud
Run, and prints your URL. Open it, sign in with `dhiraj@ekosight.com`, done.

Change region with `REGION=asia-south1` (Mumbai, the default) or any other.

---

## Path B — Production deploy (Cloud SQL Postgres)

Durable, multi-user, autoscaling. ~10 minutes of one-time setup.

### 1. Create a Postgres instance + database

```bash
gcloud sql instances create ceo-agent-db \
  --database-version=POSTGRES_15 --tier=db-f1-micro --region=asia-south1

gcloud sql databases create ceoagent --instance=ceo-agent-db
gcloud sql users set-password postgres --instance=ceo-agent-db --password='CHOOSE_A_STRONG_PASSWORD'

# Grab the instance connection name (looks like project:region:ceo-agent-db)
gcloud sql instances describe ceo-agent-db --format='value(connectionName)'
```

### 2. Deploy, wired to Cloud SQL

Cloud Run connects to Cloud SQL over a unix socket at
`/cloudsql/<CONNECTION_NAME>`. Use that host in the URL:

```bash
CONN="$(gcloud sql instances describe ceo-agent-db --format='value(connectionName)')"

PROJECT_ID=your-project-id \
CLOUDSQL_INSTANCE="$CONN" \
DATABASE_URL="postgresql+psycopg://postgres:CHOOSE_A_STRONG_PASSWORD@/ceoagent?host=/cloudsql/${CONN}" \
./deploy/deploy.sh
```

That's it — tables are auto-created and seeded on first boot.

> Store the password in **Secret Manager** for real use and pass it with
> `--set-secrets` instead of inline; see the gcloud docs. The script keeps it
> inline for brevity.

---

## Optional: turn on the Gemini brain

By default the agent uses the offline rule parser. To use Gemini via Vertex AI,
redeploy with:

```bash
LLM_PROVIDER=gemini GEMINI_API_KEY=your-key   # ...plus the flags above
```

(Or `LLM_PROVIDER=claude` + `ANTHROPIC_API_KEY`.) The app falls back to the rule
parser automatically if the key is missing or a call fails.

---

## Updating

Just re-run the same `./deploy/deploy.sh` command — Cloud Run ships a new
revision with zero downtime. With Path B your data persists across deploys.

## Custom domain

`gcloud run domain-mappings create --service ceo-agent --domain agent.ekosight.com`
then add the printed DNS records at your registrar.

## Costs

Cloud Run scales to zero and bills per request (a small team is typically a few
dollars/month). Path A pins one warm instance so it costs a bit more but keeps
the SQLite data alive. `db-f1-micro` Cloud SQL is the cheapest tier.

---

## What this unlocks next

- **Google Workspace login** — replace the email identify step with OAuth once
  there's a stable HTTPS redirect URL (this deployment provides it).
- **Live Gmail / Calendar / Drive** — the agent's `read_calendar`,
  `search_drive`, `draft_email`, `send_approved_email` tools become real API
  calls, gated by the existing approval engine.
- **Native Android** — wrap this PWA with Bubblewrap/TWA into an installable
  APK / Play Store listing, pointing at the Cloud Run URL.
