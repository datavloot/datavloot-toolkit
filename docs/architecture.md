# Optimist architecture (single node)

> **Status: proposed.** This describes the target architecture, not the current implementation: scaffolded projects currently write to a single DuckDB file, without a DuckLake catalog or maintenance jobs. The decision is recorded in an ADR (to be added).

The Optimist is the single-node tier, aimed at an organisation with a data team of one: technically multi-client, organisationally single-writer. Everything lives on one host; the full state is one directory.

## 1. Component overview

```mermaid
flowchart LR
    subgraph SRC["External sources"]
        S_API["APIs"]
        S_DB[("Databases")]
        S_FILES["Files"]
    end

    subgraph HOST["Single host: laptop or VM"]
        subgraph ORCH["Dagster (only production writer)"]
            DLT["dlt: ingest"]
            DBT["dbt: transform + test, Elementary: data quality"]
            MAINT["Maintenance: compaction, snapshot expiry"]
        end

        subgraph LAKE["DuckLake (one directory)"]
            CAT[("Catalog: metadata.sqlite")]
            PQ["Parquet files in DATA_PATH"]
        end

        DEV["dbt dev target (separate schema)"]
        MARIMO["Marimo (read-only)"]
        CROWSNEST["Crows Nest: dashboard + query API (read-only)"]
    end

    USERS["Organisation: consumers"]

    S_API --> DLT
    S_DB --> DLT
    S_FILES --> DLT
    DLT --> LAKE
    DBT --> LAKE
    MAINT --> LAKE
    DEV -.-> LAKE
    LAKE --> MARIMO
    LAKE --> CROWSNEST
    MARIMO --> USERS
    CROWSNEST --> USERS
```

## 2. How a write works

The heavy work (writing Parquet) happens outside the catalog. The catalog lock is held only for the short metadata commit, which is why several local processes can write side by side.

```mermaid
sequenceDiagram
    participant W as Writer (Dagster run)
    participant P as Parquet files (DATA_PATH)
    participant C as Catalog (SQLite)
    participant R as Reader (Marimo / Crows Nest)

    R->>C: Read current snapshot
    C-->>R: List of files for snapshot N
    R->>P: Read those files
    W->>P: Write new Parquet files (no lock)
    W->>C: Commit: register files as snapshot N+1 (short lock)
    alt Conflict on same table
        C-->>W: Conflict
        W->>C: Retry or report
    else No conflict
        C-->>W: Committed
    end
    Note over R: Keeps seeing snapshot N until it re-reads
```

## 3. Two ways of running, one artifact

```mermaid
flowchart TB
    PKG["PyPI package datavloot[optimist] (one codebase, one config schema)"]

    subgraph LAPTOP["Laptop mode"]
        L1["pip install datavloot[optimist]"]
        L2["datavloot start: Dagster + Crows Nest, plus Marimo"]
        L3["localhost only, no auth"]
    end

    subgraph VM["VM mode"]
        V1["Docker image built from the package"]
        V2["Docker Compose: Dagster, Crows Nest, Marimo"]
        V3["Reverse proxy + optional oauth2-proxy"]
    end

    DIR["Same directory: catalog + Parquet (relative paths)"]

    PKG --> L1 --> L2 --> L3
    PKG --> V1 --> V2 --> V3
    L2 --- DIR
    V2 --- DIR
    DIR -. "move directory" .-> V2
```

## 4. Access on the VM

Access to the site, not access policy on data. Per-user data authorisation belongs to Falcon. The Dagster UI and Marimo have no authentication of their own, so every service sits behind the proxy.

```mermaid
flowchart LR
    U["User in the organisation"] --> RP["Reverse proxy (TLS, port 443)"]
    RP --> OP["oauth2-proxy (optional)"]
    OP <--> IDP["Customer IdP: Entra ID / Google Workspace"]
    OP --> APPS["Crows Nest, Dagster UI, Marimo"]
    RP -. "fallback" .-> BA["VPN or basic auth"]
```

## 5. Backup

Copy the catalog first, then the files. Parquet files are never modified after they are written, so every file the copied catalog refers to already exists; files written after the catalog copy are harmless extras. Cleanup of old files must not run during the backup, or it can delete a file the copied catalog still references. Writers can keep running.

```mermaid
flowchart LR
    JOB["Backup job (no cleanup of old files while it runs)"] --> CATCOPY["1. Catalog: SQLite backup API"]
    CATCOPY --> FILECOPY["2. Parquet files"]
    FILECOPY --> SNAP["Consistent copy of the directory"]
    SNAP --> LOCAL["Local backup"]
    SNAP -. "optional" .-> BUCKET["S3-compatible bucket (restic / rclone)"]
```

## 6. Upgrade path to Falcon

Swap catalog and storage; project code (dlt, dbt, Dagster assets) stays the same. Falcon is on the roadmap; its components below are indicative, not decided.

```mermaid
flowchart LR
    subgraph OPT["Optimist"]
        O1[("SQLite catalog")]
        O2["Parquet on local disk"]
        O3["Access via customer IdP / proxy"]
    end

    subgraph FULL["Falcon (roadmap, indicative)"]
        F1[("PostgreSQL catalog")]
        F2["Parquet in S3-compatible storage"]
        F3["IAM (to be decided), per-user policy"]
    end

    O1 -- "migrate metadata" --> F1
    O2 -- "copy files, update data path" --> F2
    O3 -- "enable component" --> F3
```

## Component summary

| Component | Optimist | Falcon (indicative) |
|---|---|---|
| Ingest | dlt | dlt |
| Catalog | DuckLake + SQLite | DuckLake + PostgreSQL |
| Data storage | Parquet on local disk | Parquet in S3-compatible storage |
| Transform & test | dbt | dbt |
| Data quality | Elementary | Elementary |
| Orchestration | Dagster, concurrency limit on writing jobs | Dagster, multiple code locations |
| Writers | Multiple local processes, one production path | Multiple users and machines |
| Dashboard | Crows Nest, read-only | Crows Nest |
| Analysis | Marimo, read-only | Marimo per user with own rights |
| Access | Customer IdP via oauth2-proxy, or VPN / basic auth | IAM (to be decided), per-user policy |
| Secrets | `.env` on the host | Secrets management |
| Backup | Copy of the directory, optional off-site bucket | PostgreSQL dump + object storage versioning |
| Runtime | Laptop (pip) or single VM (Compose) | Compose or Kubernetes |
