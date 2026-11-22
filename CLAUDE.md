# Reconciliation

A case-study project built to demonstrate real architectural understanding, not blind prompting: a UK retailer's ERP and WMS disagree on stock, and this repo answers it with a reconciliation pipeline, two deliberately different agents, a deployed API, and an evaluation that proves it works.

## Working rules

- Do not commit, push, or apply a change without describing the plan and the files it touches first, and waiting for explicit go-ahead. This applies to every step, not just the first one.
- The only exception is if I say, in those words or clearly equivalent ones, to proceed without review. Absent that, always stop and show me what you're about to do before doing it.
- Never accept or explain away a file I could not defend line by line if asked about it.
- If something in this file conflicts with what a package's current docs say, trust the docs and tell me what changed.

## The case

A UK multichannel retailer is overselling. Orders are cancelled after payment, and the buying team is expediting stock to cover shortages the system never flagged. Two systems hold the stock position: the ERP holds the financial view, the WMS holds the physical one. They disagree, and nobody can say which is right for a given SKU at a given location. The client isn't asking for a dashboard, they're asking which number to trust, and why.

## What we're building

Two halves, deliberately kept distinct.

**Data layer.** One real dataset, UCI Online Retail II, split into two synthetic feeds, an ERP view and a WMS view, deliberately corrupted against each other using six named, documented failure modes (unit-of-measure divergence, posting lag, dropped cancellation flags, duplicate retried movements, SKU case variants, untraceable manual edits). dlt loads both feeds into a bronze schema. dbt builds bronze to silver to gold, with gold being the single reconciled view at the grain of SKU, location, and day. Gold lands in Neon Postgres.

SQL owns every question that's really a count, a sum, or an exact filter, always: `gold_reconciliation`'s structured columns (sku, warehouse_code, day, erp_qty, wms_qty, variance, has_discrepancy) exist for exactly that, queried directly by the analytics agent, no vectors involved. pgvector is scoped to one different job: analogical similarity, "has something like this happened before," a pattern-level question SQL cannot answer (not "find the exact same SKU and warehouse," which SQL already does precisely, but "find a case that resembles this one in kind"). That's a genuinely different capability from aggregation, not a weaker substitute for it. Concretely, pgvector holds embeddings of schema descriptions and runbook text, plus deterministic case-description embeddings for the subset of gold rows where `has_discrepancy = true` (for the investigator agent's case-retrieval), and nothing else — never used as a substitute for a query SQL could already answer precisely, and never chunked warehouse rows standing in for the full table.

**Agent layer.** A deterministic router, not a model call, decides which of two differently-shaped agents handles a request. The analytics agent is a bounded `create_agent` tool loop: list tables, get schema, write and validate SQL, execute read-only. The investigator agent is a hand-built LangGraph `StateGraph`: detect, gather context, diagnose a likely failure mode, propose a typed fix action, and `interrupt()` before anything is allowed to write. Nothing touches the warehouse without a human approving it first. FastAPI exposes both agents and streams responses over SSE.

Deployment is a single Docker container on Cloud Run via GitHub Actions with OIDC. Evaluation is a hand-verified golden query set, execution accuracy compared on result sets, never on matching SQL text, with a committed baseline that fails CI on regression.

## Environment

- Python 3.12, managed with `uv`. This is homebrew-installed uv, no install step needed.
- Use `uv init --no-package` for any new project or subproject in this repo. Current `uv init` defaults to a packaged src-layout with a build system (changed in uv 0.12); we want the flat layout, a single `main.py`-style entry point, no `[build-system]`, no `src/<name>/__init__.py`. If `--no-package` stops working as described, it's because uv moved again, check `uv init --help` and the current docs at docs.astral.sh before assuming the old flag name still applies.

## Stale API watchlist

Every line here is something a model will confidently emit wrong, because this stack moved fast in 2026 and training data hasn't caught up. Trust this file over memory. If unsure, check current docs before writing the line.

langgraph 1.2.x, langchain 1.5.x, fastapi 0.163.x, pydantic 2.14.x.

### LangChain / LangGraph
- create_react_agent is DEPRECATED. Use: from langchain.agents import create_agent
- langchain.chains / .retrievers / hub -> langchain_classic.*
- SQLDatabase / SQLDatabaseToolkit -> langchain-classic, deprecated. Hand-write @tool fns.
- NodeInterrupt -> interrupt() from langgraph.types
- interrupt_before/after is for DEBUGGING only, not HITL. Use interrupt().
- config_schema= / configurable for app config -> context_schema= + context= + Runtime.
  ({"configurable": {"thread_id": ...}} is STILL correct, for checkpointing only.)
- checkpoint_during= -> durability="exit"|"async"|"sync"
- astream_events(version="v1") -> version="v3" typed projections (stream.messages/.values)
- graph.stream(..., version="v2") for the uniform {"type","ns","data"} StreamPart dict
- InjectedState/InjectedStore/InjectedToolCallId -> a single `runtime: ToolRuntime` param
- MemorySaver -> InMemorySaver
- subgraphs=True required to stream tokens out of a compiled-agent node
- Docs: docs.langchain.com/oss/python/... NOT python.langchain.com.
- Set LANGGRAPH_STRICT_MSGPACK=true. Never downgrade langgraph-checkpoint below 4.3.0.

### FastAPI / Pydantic
- No pydantic.v1 (dropped in fastapi 0.128.0). No class Config / @validator / .dict().
  Use ConfigDict / @field_validator / @model_validator / .model_dump().
- @app.on_event deprecated -> lifespan=asynccontextmanager
- ORJSONResponse / UJSONResponse deprecated (0.131.0)
- FastAPI(root_path=...) deprecated (0.146.0)
- Native OpenTelemetry: FastAPI(telemetry={...}) + FASTAPI_OTEL_AUTO_CONFIGURE.
  Do NOT add prometheus-fastapi-instrumentator.
- Depends(max_concurrency=N) exists as of 0.163.0
- Never a blocking call inside async def. DuckDB is sync: anyio.to_thread.run_sync.

### OpenTelemetry GenAI semantic conventions (all still Development, nothing stable)
- gen_ai.system -> gen_ai.provider.name
- gen_ai.usage.prompt_tokens -> gen_ai.usage.input_tokens
- gen_ai.usage.completion_tokens -> gen_ai.usage.output_tokens
- gen_ai.prompt / gen_ai.completion -> REMOVED. Content capture is opt-in via
  gen_ai.input.messages / gen_ai.output.messages, off by default (prompts carry PII).

## Project structure

Flat, no `src/` layout, each pipeline stage as its own top-level namespace-package
folder (no `__init__.py`, run with `uv run python -m <folder>.<script>`):

```
build_movement_ledger step:
  data_preprocessing/build_movement_ledger.py

feed generation step:
  feeds/
    locations.py        deterministic warehouse/bin assignment
    failure_modes.py     six WMS corruption functions + orchestrator
    build_erp_feed.py
    build_wms_feed.py

data/
  raw/online_retail_II.xlsx            source dataset, not generated
  processed/
    movement_ledger.parquet            canonical ledger, stays flat here
    feeds/
      erp_feed.parquet
      wms_feed.parquet
    evaluation/
      exclusions_report.csv
      drift_ground_truth.parquet
```

Run order: `data_preprocessing.build_movement_ledger` ->
`feeds.build_erp_feed` and `feeds.build_wms_feed` (either order, both only
depend on the ledger).

## Initial scaffold (run once)

Set up the project exactly as follows, and show me the plan before running anything:

1. `uv init --no-package` in this directory, Python 3.12.
2. Git init, if not already a repo.
3. `.gitignore` covering: `.venv/`, `__pycache__/`, `*.duckdb`, `.env`, `*.egg-info/`, `.DS_Store`.
4. A short `README.md` stating what this project is, matching the summary at the top of this file.
5. Commit everything, message: "Initial scaffold: CLAUDE.md, gitignore, readme".
6. Create a new public GitHub repository named `reconciliation` under my account and push.