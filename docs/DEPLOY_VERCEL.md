# Deploy LearnLens AI for judges (Vercel)

This repo is a small monorepo with two deployable projects: a Next.js frontend in `web/` and a FastAPI service in `backend/`. Deploy them as **two Vercel projects connected to the same Git repository**. The browser talks only to the frontend; the frontend's `/api/*` route proxies to the private backend URL held in a server-side environment variable.

> **Important limitations:** Vercel Functions cap request/response bodies at 4.5 MB. LearnLens therefore defaults to a 3.5 MB *combined upload* limit for the hosted demo to leave room for multipart overhead. SQLite and Python in-memory state are not durable across serverless instances. Supabase is required for hosted teacher classes and real student records; without a healthy Supabase connection, classroom creation and student joining fail closed. The app remains a hackathon prototype, not a production school information system.

## Runtime safety for work analysis

The **Use bundled demo** worksheet uses a deterministic, clearly labelled sample result; it skips PDF rendering and live AI calls, and does not persist synthetic work rows. Real work analysis has a shared 36-second AI budget (the setting is capped at 38 seconds), and optional work-analysis persistence is bounded to 6 seconds. PDF/image preprocessing is capped at 12 seconds per request, with PDFs limited to 12 pages by default (`MAX_PDF_PAGES` can be set from 1 to 20). These limits are intended to leave headroom before Vercel's 60-second function cap.

## 0. Before starting

- Push the updated source folder to the Git repository you control. Do not commit `.env` files, API keys, database passwords, local caches, or real student data.
- **Configure Supabase before deploying any real teacher classroom.** Vercel may execute requests in different function instances, so in-memory state is not reliable or durable. For a fresh database, run `supabase/schema.sql` in the Supabase SQL Editor. For an existing LearnLens database, review and run `supabase/migration_hackathon.sql` instead; don't blindly run both. The synthetic `CSE-A` class is only available from a clean local checkout with no `.env` file; it is not served on Vercel Preview or Production.
- If you want live AI analysis, create an API key with the provider you choose. The sample worksheet is available without AI credentials, but broader live analysis/reteaching may fall back or return a clear unavailable response if no provider is configured.

## 1. Deploy the backend first

1. In Vercel, choose **Add New → Project** and import the Git repository.
2. Set **Root Directory** to `backend` and enable the option to include files from that root directory only. Vercel detects the FastAPI entrypoint at `index.py`; `requirements.txt` is already in this directory.
3. Add backend environment variables in Vercel → Project Settings → Environment Variables. Keep all keys server-side.

| Variable | Value / notes |
|---|---|
| `FRONTEND_ORIGINS` | `https://YOUR-FRONTEND-PROJECT.vercel.app` after frontend is deployed. The Next.js proxy is server-to-server, but this keeps CORS configuration explicit. |
| `MAX_UPLOAD_MB` | `3.5` |
| `LEARNLENS_CACHE_PATH` | `/tmp/learnlens_ai_cache.sqlite3` (best-effort instance cache only) |
| `AI_ENABLED` | `true` |
| `DEMO_MODE` | `false` to allow configured providers; `true` disables live providers. |
| `RAG_ENABLED` | `true` |
| `OPENROUTER_API_KEY` | Optional. Add a real provider key privately in Vercel, never in source code. |
| `OPENROUTER_MODEL` | `openrouter/free` (or an eligible provider-supported `:free` model). |
| `GEMINI_API_KEY` | Optional second provider; keep it server-side. |
| `GEMINI_MODEL` | `gemini-2.5-flash` or another model available to your account. |
| `SUPABASE_URL` | Required for durable saved class/student progress. |
| `SUPABASE_SECRET_KEY` | Required for the configured server-side Supabase persistence. Do not use it in frontend code. |

4. Deploy. Copy the backend's assigned URL, such as `https://learnlens-api-....vercel.app`.
5. Open `https://YOUR-BACKEND-URL/health`. Check for HTTP 200, `status: "ok"`, `notesCount: 45`, and `misconceptionCount: 22`. If Supabase is configured, `supabaseConfigured` should be true and `supabaseAvailable` should be true. Never publish environment variable values in screenshots.

## 2. Deploy the frontend

1. In Vercel, add another project from the **same** Git repository.
2. Set **Root Directory** to `web` and use the Next.js framework preset.
3. Add these environment variables for Preview and Production:

| Variable | Value / notes |
|---|---|
| `AI_SERVICE_URL` | The backend URL from step 1, with no trailing slash. This is server-side; do **not** use `NEXT_PUBLIC_` here. |
| `NEXT_PUBLIC_MAX_UPLOAD_MB` | `3.5` |

4. Deploy and copy the frontend URL. Update backend `FRONTEND_ORIGINS` with that URL if you haven't already, then redeploy the backend.
5. If you change environment variables in Vercel, redeploy the relevant project so the new settings take effect.

## 3. Production smoke test (must do before sending judges the link)

Open the **deployed frontend** in a private/incognito browser window. Run this sequence:

1. Open `/api/health` on the frontend URL; expect JSON and HTTP 200.
2. Open **I have work I got wrong → Use bundled demo**. Expect analysis to load without a provider key and the result to say it used the bundled sample/demo path.
3. Open the diagnosis/verification flow, continue to the targeted lesson, and confirm the source note references are shown.
4. Answer at least one practice question; verify mastery is described as provisional until the delayed retest.
5. Open Teacher view. The hosted site must **not** load `CSE-A` or any synthetic student rows. With Supabase configured, create a fresh class and save the teacher key; verify the roster starts empty and only real joined students and saved learning events appear. Without Supabase, the page should show a real-data setup warning and block class creation/student joining rather than showing sample records.
6. Join that class from a second browser with a nickname and explicit consent, complete a learning action, then confirm the student and saved evidence appear on the teacher heatmap after refresh and from a separate browser session.
7. Test a file upload just below 3.5 MB and one rejected above the combined limit. Check Vercel Function logs for 413/500/504 errors.
8. Confirm the mobile layout and check that no secret appears in page source, client JavaScript, console output, or screenshots.

The `CSE-A` sample class is intentionally fictional and is enabled only when judges run a clean local checkout without a `.env` file. It is never enabled on Vercel, including Preview deployments, and is disabled locally as soon as a `.env` file exists or real service credentials are supplied. Do not add `CSE-A` or `demo-teacher-key` to a deployed test script.

## 4. When Vercel is not the right choice

For a longer-term classroom pilot with larger PDFs, background jobs, or always-on in-memory sessions, host the FastAPI backend on a conventional Python web service and keep Next.js on Vercel. In either hosting setup, durable student state belongs in a database, not process memory or SQLite stored on an ephemeral filesystem.

## Official deployment references

- [Vercel: FastAPI deployment](https://vercel.com/docs/frameworks/backend/fastapi)
- [Vercel: Python runtime](https://vercel.com/docs/functions/runtimes/python)
- [Vercel: Function limitations and 4.5 MB request/response body limit](https://vercel.com/docs/functions/limitations)
- [Vercel: deployment environments](https://vercel.com/docs/deployments/environments)
