<!-- See CONTRIBUTING.md. Delete lines that do not apply; keep the rest short. -->

## What and why

<!-- One paragraph. What changes, and the reason. Link the issue if there is one: Closes #NN -->

## Which part

<!-- Tick what you touched. This decides which release train the change rides. -->

- [ ] `datavloot` Python package (CLI, Crows Nest, Dagster layer, templates)
- [ ] `optimist` dbt package (`dbt/optimist/`)
- [ ] Docs only

## Tests run locally

<!-- Tick what you ran. The tiers and their commands are in CONTRIBUTING.md. -->

- [ ] Fast tier (`-m "not slow and not package"`)
- [ ] Crows Nest tests, with fastapi and duckdb installed (required for changes under `crowsnest/`)
- [ ] Smoke tier (`-m slow`; required for changes to `dbt/optimist/` or the templates)
- [ ] Packaging tier (`tests/test_packaging.py`; required for changes to `pyproject.toml` or what ships)

## Checklist

- [ ] No version bump in `pyproject.toml` or `dbt/optimist/dbt_project.yml`
- [ ] New or changed macro is documented in `docs/`
- [ ] Convention changes are made in `dbt/optimist/data-instructions.md` only, not copied into the templates
- [ ] Scaffold and demo templates are kept in step
- [ ] Frontend source change comes with a rebuilt and committed `crowsnest/static/`
- [ ] Widened dependency bound is explained above
- [ ] Fixed `docs/backlog.md` entry removed, if any

## Breaking change?

<!-- If this changes behaviour for an existing consuming project (macro signature, meta key, built-in model columns, scaffold structure, CLI flag), say what breaks and what a consumer has to change. Otherwise delete this section. -->
