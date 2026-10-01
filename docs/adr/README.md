# Architecture decision records

An ADR records one architectural decision: the problem it answers, what was chosen, what was rejected and why. `docs/architecture.md` describes the target; the ADRs explain why it looks that way, so a later change can check whether the reasons still hold.

## Process

- One decision per file, numbered in order: `NNNN-short-title.md`.
- A new ADR starts as **Proposed** and is opened as a pull request. It becomes **Accepted** when a maintainer approves and it is merged with that status.
- An accepted ADR is not rewritten. If a decision changes, write a new ADR and mark the old one **Superseded by NNNN**.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-optimist-single-node-single-writer.md) | Optimist as a single-node, single-writer architecture | Proposed |

## Template

```markdown
# NNNN. Title

- **Status:** Proposed | Accepted | Superseded by NNNN
- **Date:** YYYY-MM-DD
- **Issue:** #n

## Context

The problem and the forces at play: what is true today, and why it is not good enough.

## Decision

What we will do, stated as decisions ("we will …").

## Consequences

What becomes easier, what becomes harder, and what follow-up work this creates.

## Alternatives considered

Each serious alternative and why it was not chosen.
```
