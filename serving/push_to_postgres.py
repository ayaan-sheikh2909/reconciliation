"""Pushes gold.gold_reconciliation_daily from the local DuckDB warehouse into a
single Postgres table, gold_reconciliation, serving both future agents from one
row identity:

- The structured columns (sku, warehouse_code, day, erp_qty, wms_qty, variance,
  has_discrepancy) serve a future Analytics agent doing direct SQL aggregation
  and exact filtering over the full 550,915-row table. SQL owns every question
  that's really a count, a sum, or an exact filter; no vectors involved there.

- case_description and embedding, populated only where has_discrepancy = true,
  serve a future Investigator agent's analogical similarity search over the
  56,523 actual discrepancy cases: "has something like this happened before,"
  a pattern-level question SQL cannot answer. This is never a substitute for
  a query SQL could already answer precisely, only a genuinely different
  capability (case retrieval) layered on top of the same table.

- The surrogate id column anticipates a future investigation_proposals table,
  which will reference a specific case here by this single integer rather than
  a three-column composite key, once a human-approval workflow is built on top.
"""

import os
import time

import duckdb
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from pgvector.psycopg2 import register_vector
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

load_dotenv()

WAREHOUSE_PATH = "data/warehouse/reconciliation.duckdb"
GOLD_TABLE = "gold.gold_reconciliation_daily"

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_BATCH_SIZE = 200

CREATE_TABLE_SQL = """
CREATE TABLE gold_reconciliation (
    id BIGSERIAL PRIMARY KEY,
    sku TEXT NOT NULL,
    warehouse_code TEXT NOT NULL,
    day DATE NOT NULL,
    erp_qty BIGINT NOT NULL,
    wms_qty BIGINT NOT NULL,
    variance BIGINT NOT NULL,
    has_discrepancy BOOLEAN NOT NULL,
    case_description TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (sku, warehouse_code, day)
);
"""


def build_case_description(row) -> str:
    direction = "WMS over-reported" if row["variance"] > 0 else "WMS under-reported"
    return (
        f"SKU {row['sku']} at warehouse {row['warehouse_code']} on {row['day']}: "
        f"ERP recorded {row['erp_qty']} units, WMS recorded {row['wms_qty']} units, "
        f"a variance of {row['variance']} units ({direction} relative to ERP)."
    )


@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_random_exponential(min=1, max=20),
    stop=stop_after_attempt(5),
)
def embed_batch(client: OpenAI, batch: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch, dimensions=EMBEDDING_DIMENSIONS)
    return [item.embedding for item in response.data]


def generate_embeddings(client: OpenAI, descriptions: list[str]) -> list[list[float]]:
    embeddings = []
    for start in range(0, len(descriptions), EMBEDDING_BATCH_SIZE):
        batch = descriptions[start : start + EMBEDDING_BATCH_SIZE]
        embeddings.extend(embed_batch(client, batch))
    return embeddings


def main():
    client = OpenAI()

    with duckdb.connect(WAREHOUSE_PATH, read_only=True) as con:
        df = con.sql(f"SELECT * FROM {GOLD_TABLE}").df()

    total_rows = len(df)
    df["day"] = pd.to_datetime(df["day"]).dt.date

    discrepancy_mask = df["has_discrepancy"] == True  # noqa: E712 - explicit bool compare for clarity
    discrepancy_df = df.loc[discrepancy_mask]
    print(f"Read {total_rows} rows from {GOLD_TABLE}; {len(discrepancy_df)} have has_discrepancy = true")

    df["case_description"] = None
    descriptions = discrepancy_df.apply(build_case_description, axis=1)
    df.loc[discrepancy_mask, "case_description"] = descriptions

    print(f"Generating embeddings for {len(descriptions)} discrepancy cases "
          f"in batches of {EMBEDDING_BATCH_SIZE}...")
    start_time = time.monotonic()
    embeddings = generate_embeddings(client, descriptions.tolist())
    elapsed = time.monotonic() - start_time
    print(f"Generated {len(embeddings)} embeddings in {elapsed:.1f}s")

    embedding_by_index = dict(zip(descriptions.index, embeddings))
    df["embedding"] = df.index.map(embedding_by_index.get)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS gold_reconciliation;")
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()
    print("Dropped and recreated gold_reconciliation")

    rows = [
        (
            str(r.sku),
            str(r.warehouse_code),
            r.day,
            int(r.erp_qty),
            int(r.wms_qty),
            int(r.variance),
            bool(r.has_discrepancy),
            r.case_description,
            r.embedding,
        )
        for r in df.itertuples(index=False)
    ]

    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO gold_reconciliation
            (sku, warehouse_code, day, erp_qty, wms_qty, variance, has_discrepancy, case_description, embedding)
        VALUES %s
        """,
        rows,
        page_size=1000,
    )
    conn.commit()
    print(f"Bulk-inserted {len(rows)} rows")

    # build the HNSW index only after all rows are loaded - indexing a streaming
    # bulk load is wasted overhead for a one-shot batch job like this
    cur.execute("CREATE INDEX ON gold_reconciliation USING hnsw (embedding vector_cosine_ops);")
    conn.commit()
    print("Created HNSW index on embedding (vector_cosine_ops)")

    cur.execute("SELECT COUNT(*) FROM gold_reconciliation;")
    inserted_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM gold_reconciliation WHERE embedding IS NOT NULL;")
    embedded_count = cur.fetchone()[0]

    cur.execute(
        "SELECT case_description, embedding FROM gold_reconciliation WHERE embedding IS NOT NULL LIMIT 1;"
    )
    sample_description, sample_embedding = cur.fetchone()

    cur.close()
    conn.close()

    print("\n--- Final report ---")
    print(f"Total rows inserted: {inserted_count}")
    print(f"Rows with non-null embedding: {embedded_count}")
    print("HNSW index created: yes")
    print(f"\nSample case_description: {sample_description}")
    print(f"Sample embedding (first 5 values): {sample_embedding.to_list()[:5]}")


if __name__ == "__main__":
    main()
