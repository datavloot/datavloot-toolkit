"""
Data quality route — reads Elementary's metadata tables from the warehouse.
"""

import json

from fastapi import APIRouter, HTTPException

from datavloot_platform.crowsnest.config import get_config
from datavloot_platform.crowsnest.db import get_conn

router = APIRouter()

_DB_UNAVAILABLE = "Database unavailable — another process may be using the DuckDB file"
_ELEMENTARY_MISSING = "Elementary tables not found — have you run dbt with the Elementary package?"


def _schema() -> str:
    return get_config().elementary_schema


def _records(df) -> list:
    """Convert a DataFrame to a JSON-safe list of dicts."""
    return json.loads(df.to_json(orient="records", date_format="iso", default_handler=str))


@router.get("/test-results")
async def get_test_results(limit: int = 100):
    conn = None
    try:
        conn = get_conn(read_only=True)
        df = conn.execute(
            f"""
            SELECT
                test_unique_id,
                model_unique_id,
                test_name,
                test_type,
                status,
                detected_at AS test_timestamp,
                test_params,
                severity,
                table_name,
                column_name
            FROM {_schema()}.elementary_test_results
            ORDER BY detected_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchdf()
        return {"test_results": _records(df), "total": len(df)}
    except HTTPException as e:
        return {"test_results": [], "total": 0, "error": f"{_DB_UNAVAILABLE}: {e.detail}"}
    except Exception:
        return {"test_results": [], "total": 0, "error": _ELEMENTARY_MISSING}
    finally:
        if conn is not None:
            conn.close()


@router.get("/summary")
async def quality_summary():
    conn = None
    try:
        conn = get_conn(read_only=True)
        df = conn.execute(
            f"""
            SELECT status, COUNT(*) as count
            FROM {_schema()}.elementary_test_results
            WHERE detected_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY status
            """
        ).fetchdf()

        by_status: dict = {}
        for _, row in df.iterrows():
            by_status[row["status"].lower()] = int(row["count"])

        total = sum(by_status.values())
        return {
            "period": "last_7_days",
            "total_tests": total,
            "by_status": by_status,
            "health_score": _calc_health_score(by_status),
        }
    except HTTPException as e:
        return {"total_tests": 0, "by_status": {}, "health_score": None, "error": f"{_DB_UNAVAILABLE}: {e.detail}"}
    except Exception:
        return {"total_tests": 0, "by_status": {}, "health_score": None, "error": _ELEMENTARY_MISSING}
    finally:
        if conn is not None:
            conn.close()


@router.get("/by-model")
async def quality_by_model():
    conn = None
    try:
        conn = get_conn(read_only=True)
        df = conn.execute(
            f"""
            SELECT table_name, status, COUNT(*) as count
            FROM {_schema()}.elementary_test_results
            WHERE detected_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY table_name, status
            ORDER BY table_name
            """
        ).fetchdf()

        models: dict = {}
        for _, row in df.iterrows():
            name = row["table_name"]
            if name not in models:
                models[name] = {"model": name, "pass": 0, "fail": 0, "warn": 0, "error": 0}
            status = row["status"].lower()
            if status in models[name]:
                models[name][status] = int(row["count"])

        return {"models": list(models.values())}
    except HTTPException as e:
        return {"models": [], "error": f"{_DB_UNAVAILABLE}: {e.detail}"}
    except Exception:
        return {"models": [], "error": _ELEMENTARY_MISSING}
    finally:
        if conn is not None:
            conn.close()


@router.get("/anomalies")
async def get_anomalies(limit: int = 50):
    conn = None
    try:
        conn = get_conn(read_only=True)
        df = conn.execute(
            f"""
            SELECT
                test_unique_id,
                table_name,
                column_name,
                test_name,
                test_type,
                status,
                detected_at AS test_timestamp
            FROM {_schema()}.elementary_test_results
            WHERE test_type = 'anomaly_detection'
            ORDER BY detected_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchdf()
        return {"anomalies": _records(df)}
    except HTTPException as e:
        return {"anomalies": [], "error": f"{_DB_UNAVAILABLE}: {e.detail}"}
    except Exception:
        return {"anomalies": [], "error": _ELEMENTARY_MISSING}
    finally:
        if conn is not None:
            conn.close()


@router.get("/by-test")
async def quality_by_test(model: str):
    conn = None
    try:
        conn = get_conn(read_only=True)
        df = conn.execute(
            f"""
            SELECT
                test_name,
                MIN(column_name) AS column_name,
                MIN(test_type) AS test_type,
                COUNT(*) FILTER (WHERE status = 'pass') AS pass,
                COUNT(*) FILTER (WHERE status = 'fail') AS fail,
                COUNT(*) FILTER (WHERE status = 'warn') AS warn,
                COUNT(*) FILTER (WHERE status = 'error') AS error,
                MAX(detected_at) AS last_run
            FROM {_schema()}.elementary_test_results
            WHERE table_name = ?
            GROUP BY test_name
            ORDER BY test_name
            """,
            [model],
        ).fetchdf()
        return {"model": model, "tests": _records(df)}
    except HTTPException as e:
        return {"model": model, "tests": [], "error": f"{_DB_UNAVAILABLE}: {e.detail}"}
    except Exception:
        return {"model": model, "tests": [], "error": _ELEMENTARY_MISSING}
    finally:
        if conn is not None:
            conn.close()


def _calc_health_score(by_status: dict) -> float | None:
    total = sum(by_status.values())
    if total == 0:
        return None
    passed = by_status.get("pass", 0)
    return round((passed / total) * 100, 1)
