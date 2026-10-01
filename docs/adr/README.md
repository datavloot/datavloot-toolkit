# Architecture decision records

An ADR records one architectural decision: the problem, what was chosen, and what was rejected and why. `docs/architecture.md` describes the target; the ADRs explain why.

## Process

- One decision per file, numbered in order: `NNNN-short-title.md`.
- A new ADR is proposed as a pull request. Approving and merging it is accepting it, so every ADR on `main` is in force.
- An ADR on `main` is not rewritten. If a decision changes, write a new ADR and add a line to the top of the old one pointing to it: `Superseded by [NNNN](NNNN-short-title.md).`

## Index

| ADR | Title |
|---|---|
| [0001](0001-optimist-single-node-single-writer.md) | Optimist as a single-node, single-writer architecture |

## Template

```markdown
# NNNN. Title

- **Date:** YYYY-MM-DD
- **Issue:** #n

## Context

The problem and the forces at play: what is true today, and why it is not good enough.

## Decision

What we will do.

## Consequences

What becomes easier, what becomes harder, and what follow-up work this creates.

## Alternatives considered

Each serious alternative and why it was not chosen.
```
