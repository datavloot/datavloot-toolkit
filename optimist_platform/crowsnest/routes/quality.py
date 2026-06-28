"""
Data quality route — reads Elementary's metadata tables from the warehouse.
"""

from fastapi import APIRouter, HTTPException
import duckdb

from optimist_platform.crowsnest.config import get_config
from optimist_platform.crowsnest.db import get_conn

router = APIRouter()


def _schema() -> str:
    return get_config().elementary_schema


@router.get("/test-results")
async def get_test_results(limit: int = 100):
    """Recent test results from Elementary's test results table."""
    conn = get_conn(read_only=True)
    try:
        results = conn.execute(
            f"""
            SELECT
                test_unique_id,
                model_unique_id,
                test_name,
                test_type,
                status,
                test_timestamp,
                test_params,
                severity,
                table_name,
                column_name
            FROM {_schema()}.elementary_test_results
            ORDER BY test_timestamp DESC
            LIMIT ?
            """,
            [limit],
        ).fetchdf()

        return {"test_results": results.to_dict(orient="records"), "total": len(results)}

    except duckdb.CatalogException:
        return {
            "test_results": [],
            "total": 0,
            "error": "Elementary tables not found — have you run dbt with the Elementary package?",
        }
    finally:
        conn.close()


@router.get("/summary")
async def quality_summary():
    """Aggregate quality metrics for the banner."""
    conn = get_conn(read_only=True)
    try:
        summary = conn.execute(
            f"""
            SELECT status, COUNT(*) as count
            FROM {_schema()}.elementary_test_results
            WHERE test_timestamp >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY status
            """
        ).fetchdf()

        by_status: dict = {}
        for _, row in summary.iterrows():
            by_status[row["status"].lower()] = int(row["count"])

        total = sum(by_status.values())

        return {
            "period": "last_7_days",
            "total_tests": total,
            "by_status": by_status,
            "health_score": _calc_health_score(by_status),
        }

    except duckdb.CatalogException:
        return {
            "total_tests": 0,
            "by_status": {},
            "health_score": None,
            "error": "Elementary tables not found",
        }
    finally:
        conn.close()


@router.get("/by-model")
async def quality_by_model():
    """Test results grouped by model."""
    conn = get_conn(read_only=True)
    try:
        results = conn.execute(
            f"""
            SELECT table_name, status, COUNT(*) as count
            FROM {_schema()}.elementary_test_results
            WHERE test_timestamp >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY table_name, status
            ORDER BY table_name
            """
        ).fetchdf()

        models: dict = {}
        for _, row in results.iterrows():
            name = row["table_name"]
            if name not in models:
                models[name] = {"model": name, "pass": 0, "fail": 0, "warn": 0, "error": 0}
            status = row["status"].lower()
            if status in models[name]:
                models[name][status] = int(row["count"])

        return {"models": list(models.values())}

    except duckdb.CatalogException:
        return {"models": [], "error": "Elementary tables not found"}
    finally:
        conn.close()


@router.get("/anomalies")
async def get_anomalies(limit: int = 50):
    """Recent anomaly detection results from Elementary."""
    conn = get_conn(read_only=True)
    try:
        results = conn.execute(
            f"""
            SELECT
                test_unique_id,
                table_name,
                column_name,
                test_name,
                test_type,
                status,
                test_timestamp
            FROM {_schema()}.elementary_test_results
            WHERE test_type = 'anomaly_detection'
            ORDER BY test_timestamp DESC
            LIMIT ?
            """,
            [limit],
        ).fetchdf()

        return {"anomalies": results.to_dict(orient="records")}

    except duckdb.CatalogException:
        return {"anomalies": [], "error": "Elementary tables not found"}
    finally:
        conn.close()


def _calc_health_score(by_status: dict) -> float | None:
    total = sum(by_status.values())
    if total == 0:
        return None
    passed = by_status.get("pass", 0)
    return round((passed / total) * 100, 1)
