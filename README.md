# RAG Evaluator

RAG Evaluator calls a retrieval system, stores each answer as a trace, and scores that trace. A judge checks correctness and faithfulness. Retrieval, chunking, and chat-history checks run from the stored rows. A setup report names the likely cause and the setting to try next.

The API serves HTTP and progress events. A worker claims jobs and calls the target and the judge. By default the worker runs as a thread inside the API process. Set `EVAL_EMBEDDED_WORKER=0` to run it as a separate process that shares the same SQLite file.

The design decisions are in [docs/PLAN.md](docs/PLAN.md). The screen layout used by the React app is in [docs/rag-eval-ui.html](docs/rag-eval-ui.html).

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Node.js 20 for the frontend
- An OpenAI API key when a run uses the live judge

## Setup

From the repository root:

```bash
uv sync --all-groups
```

That creates `.venv` in the project root. Activate it in each terminal before you run the API or the worker:

```bash
source .venv/bin/activate
```

On Windows:

```cmd
.venv\Scripts\activate
```

The prompt shows `(.venv)` while it is active. In that terminal, `python` and `eval-worker` come from this environment.

Create a `.env` file in the repository root. `uv run main.py` loads it and does not override variables that are already set. `.env` is gitignored.

```bash
EVAL_SECRET_KEY=replace-with-a-secret-only-you-know
EVAL_DATABASE_URL=sqlite:///./data/eval.db
EVAL_ALLOW_PYTHON_ADAPTERS=0
EVAL_ALLOW_LOOPBACK=0
EVAL_EMBEDDED_WORKER=1
EVAL_JUDGE_PROVIDER=openai_chat
EVAL_JUDGE_MODEL=gpt-5.4-mini
OPENAI_API_KEY=sk-...
```

`EVAL_SECRET_KEY` encrypts adapter credentials. Saving a secret fails when the key is missing. `EVAL_ALLOW_PYTHON_ADAPTERS=1` turns on the Python-object adapter, which imports and runs the path you supply. Leave it at `0` unless you intend that. `EVAL_ALLOW_LOOPBACK=1` allows a target URL on `127.0.0.1` or `localhost`. Private and link-local addresses stay blocked. Leave it at `0` unless the target runs on this machine. `EVAL_EMBEDDED_WORKER=0` stops the API from running jobs. Use it only when you start `eval-worker` yourself.

`EVAL_JUDGE_MODEL` is the judge model used when a run does not name one. `EVAL_JUDGE_PROVIDER` is `openai_chat` or `openai_responses`. A model id sent with the run request wins over the environment.

`OPENAI_API_KEY` is read by the judge and by adapters that have no stored secret. The UI does not send the key.

Install the frontend once:

```bash
cd frontend
npm install
```

PDF reports need the optional extra: `uv sync --extra pdf`. Without WeasyPrint, the PDF download fails closed and HTML and JSON reports still work.

## Run

Start the API from the repository root so it uses `./data/eval.db`. Activate `.venv` in that terminal first. Use a second terminal for the UI.

```bash
source .venv/bin/activate
python main.py
```

`uv run main.py` starts the same process and uses `.venv` for you.

The API listens on `http://127.0.0.1:27463` and runs queued jobs one run at a time. On start it puts jobs left `running` by an earlier process back in the queue.

To run jobs in a separate process instead, set `EVAL_EMBEDDED_WORKER=0` for the API and start the worker in another terminal:

```bash
source .venv/bin/activate
uv run --env-file .env eval-worker
```

The worker does not read `.env` on its own. `--env-file` gives it the same database URL, secret key, `OPENAI_API_KEY`, and judge model as the API. Run either the embedded worker or `eval-worker`, not both.

```bash
cd frontend
npm run dev
```

The UI is at `http://localhost:27464/`. Vite proxies `/api` to `http://127.0.0.1:27463`.

The bench has five steps: connect a system, upload a dataset, choose the judge and start a run, read results, and open the setup report.

Connect saves each endpoint as a new version of a system and lists saved connections with their last test. The one marked In use is the endpoint every run calls. The query box is plain text: that text is sent once to check the endpoint. A run sends each dataset question the same way. Body format chooses the shape. Form fields send `message` and `stream=false`, which is what an Agno AgentOS `/agents/{id}/runs` endpoint expects. JSON sends `{"question": "..."}`. A saved body that cannot carry each question is rejected.

Judge and run shows the endpoint and dataset the run will use. While a run is going, it shows the question being sent now, how long the endpoint has taken, the questions next in the queue, how many are computed, and how many are left. A queued run says what it is waiting for: another run ahead of it, or a stopped worker.

Supported target adapters are `http`, `openai_chat`, and `python` when the Python adapter is enabled. The judge providers are `openai_chat` and `openai_responses`. Judge temperature is fixed at 0.

## Checks

```bash
uv run lint-imports
uv run pytest
cd frontend && npm run lint && npm test && npm run build
```

`pytest` skips tests marked `live`. Those call a real model. Run them with `uv run pytest -m live` when `OPENAI_API_KEY` is set.

## Layout

| Path | Role |
| --- | --- |
| `main.py` | Loads `.env` and starts the API |
| `backend/app/main.py` | Composition root: database, adapters, judge, services |
| `backend/app/worker.py` | Claims jobs and calls `create_container()` |
| `frontend/src/main.tsx` | Builds the HTTP client and feature services |
| `docs/PLAN.md` | Architecture and metric rules |
