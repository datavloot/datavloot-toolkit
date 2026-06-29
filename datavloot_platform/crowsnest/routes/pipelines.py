"""
Pipeline status route — pulls from Dagster's GraphQL API.
"""

from fastapi import APIRouter, HTTPException
import httpx

from datavloot_platform.crowsnest.config import get_config

router = APIRouter()

RUNS_QUERY = """
query RecentRuns($limit: Int!) {
  runsOrError(filter: {}, limit: $limit) {
    __typename
    ... on Runs {
      results {
        runId
        status
        jobName
        startTime
        endTime
        tags {
          key
          value
        }
      }
    }
    ... on InvalidPipelineRunsFilterError {
      message
    }
    ... on PythonError {
      message
    }
  }
}
"""

JOBS_QUERY = """
query Jobs {
  repositoriesOrError {
    __typename
    ... on RepositoryConnection {
      nodes {
        name
        jobs {
          name
          description
          isJob
        }
      }
    }
  }
}
"""


async def _dagster_query(query: str, variables: dict | None = None) -> dict:
    config = get_config()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            config.dagster_graphql_url,
            json={"query": query, "variables": variables or {}},
        )
        if resp.status_code != 200:
            raise HTTPException(502, f"Dagster returned {resp.status_code}")
        return resp.json()


@router.get("/runs")
async def get_recent_runs(limit: int = 20):
    """Return recent pipeline runs with normalized status."""
    try:
        data = await _dagster_query(RUNS_QUERY, {"limit": limit})
        runs_data = data.get("data", {}).get("runsOrError", {})

        if runs_data.get("__typename") != "Runs":
            raise HTTPException(502, runs_data.get("message", "Unknown Dagster error"))

        runs = []
        for r in runs_data.get("results", []):
            runs.append(
                {
                    "id": r["runId"],
                    "job": r["jobName"],
                    "status": _normalize_status(r["status"]),
                    "started_at": r.get("startTime"),
                    "ended_at": r.get("endTime"),
                    "duration_seconds": _calc_duration(
                        r.get("startTime"), r.get("endTime")
                    ),
                    "tags": {t["key"]: t["value"] for t in r.get("tags", [])},
                }
            )

        return {"runs": runs, "total": len(runs)}

    except httpx.ConnectError:
        raise HTTPException(503, "Cannot connect to Dagster — is it running?")


@router.get("/jobs")
async def get_jobs():
    """Return all registered jobs/pipelines."""
    try:
        data = await _dagster_query(JOBS_QUERY)
        repos = data.get("data", {}).get("repositoriesOrError", {})

        if repos.get("__typename") != "RepositoryConnection":
            return {"jobs": []}

        jobs = []
        for repo in repos.get("nodes", []):
            for job in repo.get("jobs", []):
                if job.get("isJob"):
                    jobs.append(
                        {
                            "name": job["name"],
                            "repository": repo["name"],
                            "description": job.get("description"),
                        }
                    )

        return {"jobs": jobs}

    except httpx.ConnectError:
        raise HTTPException(503, "Cannot connect to Dagster — is it running?")


@router.get("/summary")
async def pipeline_summary(limit: int = 50):
    """High-level pipeline health summary for the banner."""
    try:
        runs_resp = await get_recent_runs(limit=limit)
        runs = runs_resp["runs"]

        status_counts: dict = {}
        for r in runs:
            s = r["status"]
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "total_runs": len(runs),
            "by_status": status_counts,
            "latest_run": runs[0] if runs else None,
        }

    except HTTPException:
        return {
            "total_runs": 0,
            "by_status": {},
            "latest_run": None,
            "error": "Cannot connect to Dagster",
        }


def _normalize_status(dagster_status: str) -> str:
    mapping = {
        "SUCCESS": "success",
        "FAILURE": "failure",
        "CANCELED": "cancelled",
        "CANCELING": "cancelling",
        "STARTED": "running",
        "STARTING": "running",
        "QUEUED": "queued",
        "NOT_STARTED": "pending",
    }
    return mapping.get(dagster_status, dagster_status.lower())


def _calc_duration(start: float | None, end: float | None) -> float | None:
    if start and end:
        return round(end - start, 1)
    return None
