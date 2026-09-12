# AGENTS.md — working in r36s-disp

Guidance for humans and coding agents contributing to this repo.

## Source of truth

- **[SPEC.md](SPEC.md) is the design source of truth.** Read the referenced
  sections before changing behavior. Do not edit SPEC.md as part of a code
  change; note ambiguities in the PR/issue instead.
- **GitHub Issues are the single source of truth for work tracking.** Every
  change maps to an issue. If it isn't filed, file it before or alongside the
  work.

## Issue tracking

- Milestones are labels `M1`–`M5`, matching SPEC.md §8 (M1 spec, M2 desktop
  player, M3 sync server/client, M4 device deploy, M5 hardening).
- One issue per deliverable. Keep acceptance criteria in the issue.
- If part of a ticket is deferred or split off, **file a follow-up issue
  first**, link it from the parent, then finish and close the parent.

```sh
gh issue list --state open
gh issue view <n>
gh issue create --label M2 --title "..." --body "..."
```

## Workflow

1. Pick an open issue; read its SPEC references.
2. Branch off the latest `main`:
   `git checkout main && git pull && git checkout -b issue-<n>-<slug>`.
3. Implement with tests. Keep device-targeted logic stdlib-only / Python 3.8+
   compatible; confine pygame to rendering (`app/player/render.py`,
   `audio.py`, `theme.py`, `app.py`). Pure logic must stay importable without
   pygame so headless tests run.
4. Run the suite: `.venv/bin/pytest -q`.
5. Commit with an imperative message referencing the issue, e.g.
   `Add desktop player (#2)`. Follow existing log style.
6. Push the branch and open a PR that links the issue:
   `gh pr create --fill` (include a `Closes #<n>` line in the body).
7. **When the ticket is finished: commit, push, merge the PR, and close the
   issue.** Only close when acceptance criteria are met; deferred items must
   already exist as follow-up issues.

## Dev commands

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt

.venv/bin/pytest                                     # full suite (incl. SDL smoke)
.venv/bin/python -m app.main testpackages/full       # play a sample package
.venv/bin/python -m app.main --validate-only <pkg>   # validate, exit 0/1
```

## Conventions

- Python 3.7+ for anything that ships to the device (verified on the R36S:
  3.7.5); no new runtime deps beyond `pygame` and `mpv` (see `deploy/`).
- Device display is KMS/DRM (no X11); the pygame wheel's bundled SDL2 lacks
  KMSDRM — `deploy/install.sh` repoints it at the system SDL2.
- Target screen is 640×480; render to a logical surface and scale at runtime.
- All network work is best-effort and must never crash the player.
- Do not add code comments unless they earn their place; prefer docstrings.
- Test packages live in `testpackages/` (`full`, `minimal`, `invalid/*`);
  regenerate assets with `testpackages/gen_assets.sh`.
