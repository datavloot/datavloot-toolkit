# Toolkit Developer Standards

Decisions about how the toolkit is structured and how it relates to the scaffold and example projects.
When working on any of these components, verify against the standards below.

---

## 1. Component roles

| Component | Role |
|---|---|
| `dbt/optimist/` | The installable dbt package. Contains macros, built-in dimensions, and config templates. |
| `scaffold/` | Copy-paste template for a new consuming project. Mirrors the structure a real project should have. |
| `noaa/` | A real example project built on the toolkit. Demonstrates AIS + weather ingestion with Dagster + dlt. |
| `optimist_platform/` | Dagster platform template. Contains only toolkit assets + commented dlt pattern for new projects. |

---

## 2. Architectural separation

`optimist_platform/` is a **template**. Example project assets (like NOAA ingestion) must not be
added to it — that would imply they are building blocks rather than examples.

Each example project (e.g. `noaa/`) has its own `<project>_platform/` Dagster layer inside its own
directory. The root `optimist_platform/` stays clean.

---

## 3. CLAUDE.md as single source of truth

Everything a crew agent needs to work in a consuming project lives in `dbt/optimist/CLAUDE.md`:
captain/crew model, pre-departure questions, workflow steps 1–7, modelling conventions, naming
conventions, file map, and when to pause. It ships with the package and becomes available at
`dbt_packages/optimist/CLAUDE.md` after `dbt deps`.

**Consuming project CLAUDE.md files** (`scaffold/CLAUDE.md`, `noaa/CLAUDE.md`) contain only:
- Project name and one-line description
- A reference to `dbt_packages/optimist/CLAUDE.md`
- A "Project context" section with project-specific details (sources, warehouse, orchestration)

They do **not** duplicate workflow or conventions. Convention updates are made once in the package
and inherited automatically on the next `dbt deps`.

**Root `CLAUDE.md`** covers toolkit developer workflow only (macro authoring, template editing).
It is not the right place for project-level or modelling guidance.

---

## 4. Checklist for adding or changing a convention

- [ ] Update `dbt/optimist/CLAUDE.md`
- [ ] Verify scaffold/CLAUDE.md and noaa/CLAUDE.md still correctly reference the package doc (no duplication crept in)
- [ ] If the convention affects macro behaviour, update `docs/` as well

---

## 5. Checklist for adding a new example project

- [ ] Create `<project>/` at the repo root — self-contained, not nested under another project
- [ ] Create `<project>/<project>_platform/` for the Dagster layer (assets.py, definitions.py)
- [ ] Create `<project>/pyproject.toml` with `[tool.dagster]` pointing to `<project>_platform.definitions`
- [ ] Copy `scaffold/CLAUDE.md` as the starting `<project>/CLAUDE.md` and fill in project-specific details
- [ ] Add a section to the root `README.md` describing the example
