---
name: pp-risk-development
description: Govern all PP_Risk feature, database, API, frontend, simulator, testing, and documentation changes. Use whenever Codex is asked to design, implement, fix, refactor, or extend the F:\pyHome\PythonProject\PP_Risk project.
---

# PP Risk Development

## Mandatory design gate

1. Read the project-root `DESIGN` file completely before proposing or making changes.
2. Update `DESIGN` first with the requested scope, architecture, schema/API/UI impact, tests, risks, and open decisions.
3. Stop after the design update and ask the user to review it. Do not modify functional code in the same approval cycle.
4. Implement only after the user explicitly confirms the current design.
5. If implementation reveals a material design change, update `DESIGN` and stop for confirmation again.
6. Update `DESIGN` to reflect the final implementation and verification results after approved work is complete.

An explicit user instruction to perform an emergency fix immediately may waive the waiting step, but never waive documenting the change in `DESIGN` before editing functional code.

## Project invariants

- Keep PP_Risk independent from AI_Risk; use AI_Risk only as a read-only reference.
- Do not change the nine reusable risk-table schemas or the fixed decision pipeline unless the user explicitly changes that constraint.
- Use MySQL `pp_risk` for application/demo data and isolated SQLite for automated unit tests.
- Keep consequential actions at manual-review submission unless separately authorized.
- Preserve sensitive values in `.env`; never print or commit database passwords.

## Delivery check

- Link the updated `DESIGN` file in the response requesting approval.
- State clearly whether functional code was changed.
- After implementation, run proportionate tests and verify relevant MySQL/frontend flows.
