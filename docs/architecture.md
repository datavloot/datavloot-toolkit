# Optimist architecture (single node)

> **Status: proposed.** This describes the target architecture, not the current implementation: scaffolded projects currently write to a single DuckDB file, without a DuckLake catalog or maintenance jobs. The reasoning is in [ADR 0001](adr/0001-optimist-single-node-single-writer.md).

The Optimist is the single-node vessel, aimed at an organisation with a data team of one: technically multi-client, organisationally single-writer. Everything lives on one host; the full state is one directory.

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
        V3["Traefik + optional oauth2-proxy"]
    end

    DIR["Same directory: catalog + Parquet (relative paths)"]

    PKG --> L1 --> L2 --> L3
    PKG --> V1 --> V2 --> V3
    L2 --- DIR
    V2 --- DIR
    DIR -. "move directory" .-> V2
```

## 4. Access on the VM

Access to the site, not access policy on data: whoever is let in sees everything. The Dagster UI and Marimo have no authentication of their own, so every service sits behind Traefik and is reachable only through it.

Traefik runs with the Docker provider (`exposedByDefault: false`), redirects HTTP to HTTPS and has its dashboard off; each service gets its own hostname (`crowsnest.`, `dagster.`, `marimo.<domain>`). A ForwardAuth middleware sends every request to oauth2-proxy, connected to the customer's own IdP, so one sign-in covers all three. Without an IdP, Traefik's built-in `basicAuth` middleware replaces oauth2-proxy. TLS comes from Let's Encrypt through Traefik's ACME resolver.

The Crows Nest's own token auth (`CROWSNEST_AUTH_TOKEN`) stays off behind the proxy, so users are not asked twice. That is only safe because the Crows Nest is not reachable except through Traefik.

```mermaid
flowchart LR
    U["User in the organisation"] --> TR["Traefik (TLS, port 443)"]
    TR -- "ForwardAuth" --> OP["oauth2-proxy (optional)"]
    OP <--> IDP["Customer IdP: Entra ID / Google Workspace"]
    TR --> APPS["crowsnest. / dagster. / marimo.#lt;domain#gt;"]
    TR -. "fallback" .-> BA["Traefik basicAuth middleware, or VPN"]
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

## Component summary

| Component | Optimist |
|---|---|
| Ingest | dlt |
| Catalog | DuckLake + SQLite |
| Data storage | Parquet on local disk, under the project directory |
| Transform & test | dbt |
| Data quality | Elementary |
| Orchestration | Dagster, concurrency limit on writing jobs |
| Writers | Multiple local processes, one production path |
| Dashboard | Crows Nest, read-only |
| Analysis | Marimo, read-only |
| Reverse proxy | Traefik (VM mode only) |
| Access | oauth2-proxy with the customer's IdP, or Traefik basic auth |
| Secrets | `.env` on the host |
| Backup | Copy of the directory, optional off-site bucket |
| Runtime | Laptop (pip) or single VM (Compose) |
