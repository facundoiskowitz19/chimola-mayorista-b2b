"""Cliente BigQuery readonly con tope de bytes por query."""
from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd
from google.cloud import bigquery

import config

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def client() -> bigquery.Client:
    return bigquery.Client(project=config.BQ_PROJECT)


def query(sql: str, params: list | None = None, max_bytes: int | None = None) -> pd.DataFrame:
    """Corre una query con `maximum_bytes_billed` y devuelve un DataFrame.
    `max_bytes` sube el tope para queries puntuales sobre tablas grandes sin
    partición (ej: central_raw.itemvensql ~1.5 GB por scan)."""
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=max_bytes or config.MAX_BYTES_BILLED,
        query_parameters=params or [],
    )
    job = client().query(sql, job_config=job_config)
    df = job.result().to_dataframe()
    log.info("BQ query ok: %d filas, %s bytes procesados", len(df), job.total_bytes_processed)
    return df
