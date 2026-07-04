---
name: updating-documentation
description: Use when the user asks to update, refresh, sync, or write project documentation — English or Romanian ("update the docs", "update documentation", "document the changes", "actualizează documentația", "actualizează docs", "documentează", "refă/reface documentația", "scrie în documentație") — or right after finishing an implementation round that changed behavior, data model, business logic, ETL, or infrastructure.
---

# Updating Documentation

## Overview
Document the **delta, not the codebase.** Detect what changed since the last CHANGELOG entry, route each change to the one canonical doc that owns it, edit only the affected section, and never invent business facts. Runs autonomously end-to-end, then hands back the updated docs plus any open questions for the user to review.

## Core principles
- **One fact, one home.** Each doc owns a domain (see Index). Put a fact where it belongs and cross-reference instead of duplicating.
- **Delta only.** Document what changed since the newest CHANGELOG `###` entry — not the whole system.
- **Ask, don't invent.** If a change implies a business decision, rationale, or target number that is NOT in the code/commits, list it under "Open questions" at the end — never fabricate it. This is the collaborative safety valve.
- **Match the house style.** English in developer docs; Romanian only for user-facing strings/manuals. Preserve each doc's existing section structure, heading levels, and date format.

## Document index — route each change to its owner
| Doc | Owns | Update when the change touches… |
|-----|------|--------------------------------|
| `CHANGELOG.md` | Dated log of every notable change (Keep-a-Changelog: `## [Unreleased]` → dated `### <Feature> (YYYY-MM-DD)` sections, bullets, closing "Documented in …" refs) | **Always** — add one new dated entry per feature |
| `context/STATUS.md` | Live tracker: delivered / in progress / blocked + "Next immediate step" | **Always** — reflect the new state |
| `docs/BUSINESS.md` | Company, market, strategy, risks, AI opportunities, 2026–2030 plan (§7) | A business capability, strategy, risk, or opportunity changed |
| `docs/BUSINESS_LOGIC.md` | Domain vocabulary, data model, bonus, virtual brands, stock sync, forecast concepts | A domain rule / data model / calculation / forecast logic changed |
| `docs/TECHNICAL.md` | Data layer + input-file map (§Data); deploy/VPS/secrets; Romanian-in-`.py` encoding (§Encoding, **critical**); Typst manuals (§Typst); frontend error conventions (§Frontend conventions — `AppError.show()`); logging (§Application logging) | ETL, SQLite, migration, Excel/data files; deploy/secrets/infra; editing a `.py` with Romanian strings; Typst manuals; user-facing error handling; logging |
| `docs/BACKLOG.md` | Tech-debt + open issues | A change delivered a backlog item (tick/annotate) or created a new one |
| Module README (e.g. `app/forecast/README.md`) | Feature-local reference | The change lives inside that module |
| `README.md` (root) | Project overview, setup, run commands | Setup, commands, or top-level structure changed |

**Skip** (do not touch unless explicitly asked): `docs/TECHNICAL_history.md` (write-mostly archive), `docs/manuals/` (Typst PDFs/sources — the §Typst *rules* live in `TECHNICAL.md`), `docs/specs|analysis|plans/` (design artifacts), `docs/decision.html` (owner-managed).

> This index mirrors the **Read-on-demand routing** table in `CLAUDE.md` — the source of truth for which doc owns what (incl. the `TECHNICAL.md` sub-sections §Data / §Encoding / §Typst / §Frontend conventions). `CHANGELOG.md` and root `README.md` aren't in that table but are maintained here. If CLAUDE.md's routing table changes, update this index to match.

## Workflow (autonomous)
1. **Scope.** Find the newest dated `###` entry under `## [Unreleased]` in `CHANGELOG.md`. Collect changes since then: `git log <that-date-or-sha>..HEAD --stat` **plus** uncommitted work (`git status`, `git diff`). If the branch diverged from `main`, also cross-check `git diff main...HEAD --stat`. If nothing new is undocumented, say so and stop.
2. **Classify.** For each changed area read the code / commit messages enough to state *what changed and why*. Group into features. If a doc-updating task already ran this round (e.g. a module README or STATUS was already edited on the branch), treat those as done and only fill the gaps.
3. **Route.** Map each feature to docs via the Index. Open **only** the matching section of each target doc — grep its heading and read that slice; never read a large doc (`BUSINESS.md`, `TECHNICAL.md`) whole.
4. **Edit surgically.** Update each affected section in place, matching its style. Always add the CHANGELOG entry and the STATUS update. Tick delivered BACKLOG items and annotate blocked ones. Keep every fact in its one canonical doc; cross-reference elsewhere.
5. **Report.** Print a summary table (doc → section → what changed) and an **Open questions** list (anything unresolved from code alone — business rationale, target metrics, naming intent). Do **not** commit — leave the edits for the user to review unless they ask you to commit.

## Token efficiency
- The Index tells you which 2–4 docs a change hits — don't open all eight.
- Read only the section you will edit (grep the heading, slice it), not whole large docs.
- Read each source file once; batch independent reads in one step.
- Don't restate one change across multiple docs — put it in its owner and cross-reference.

## Common mistakes
- Documenting the whole system instead of the delta → re-anchor on the CHANGELOG scope.
- Opening entire large docs → grep to the section first.
- Duplicating the same fact across docs → one home + cross-ref.
- Inventing business reasons/metrics not present in code → move them to Open questions.
- Auto-committing the edits → leave them for review unless asked.
