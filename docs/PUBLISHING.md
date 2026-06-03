# Publishing to PyPI

ScribeFlow publishes to PyPI automatically from CI using **OIDC trusted publishing** —
no long-lived API token is stored anywhere. The flow is driven entirely by a
SemVer git tag.

For the maintainer's step-by-step release checklist, see
[RELEASING.md](./RELEASING.md). This document explains *how the publish
machinery works* and the **one-time** PyPI setup.

---

## The pipeline at a glance

```
git tag vX.Y.Z  ──►  push tag
       │
       ▼
release.yml   (on: push tag "v*")          permissions: contents: write
   builds sdist + wheel with `python -m build`
   uploads them as the `dist` artifact
       │
       ▼  (maintainer publishes the GitHub Release)
publish.yml   (on: release published)      permissions: id-token: write
   builds sdist + wheel
   publishes to PyPI via pypa/gh-action-pypi-publish (OIDC)
   skip-existing: true  → idempotent
```

Two workflows, two triggers:

- **`release.yml`** fires on any pushed tag matching `v*`. It builds the
  distributions and uploads them as a CI artifact named `dist`. This is your
  build/sanity gate — it proves the package builds on a clean runner.
- **`publish.yml`** fires when a **GitHub Release is published**. It rebuilds the
  distributions and uploads them to PyPI through trusted publishing.

> Because `publish.yml` triggers on *release published* (not on the tag push),
> pushing a tag alone does **not** ship to PyPI. You create/publish the GitHub
> Release from the tag to trigger the upload. This gives you a deliberate
> "build first, publish on purpose" gate.

### Why OIDC trusted publishing

`publish.yml` requests `id-token: write` and runs in the `pypi` GitHub
Environment. The `pypa/gh-action-pypi-publish` action exchanges a short-lived
GitHub OIDC token for a one-time PyPI upload credential. Benefits:

- **No API token** to store, rotate, or leak — nothing in repo secrets.
- The trust is scoped to *this repo + this workflow + this environment*.
- `skip-existing: true` makes re-runs safe: an already-uploaded file is
  tolerated instead of failing the job (idempotent publishes).

---

## First-time PyPI trusted-publisher setup

Do this **once**, before the first real release. The project owner is
`htahaozlu`; the repo is <https://github.com/htahaozlu/scribeflow>.

### 1. Create the project's trusted publisher on PyPI

For a project that does **not yet exist** on PyPI, use a *pending* publisher so
the very first upload can create the project:

1. Sign in to <https://pypi.org> as the project owner.
2. Go to **Account → Publishing** (Manage account → Publishing), under
   *"Add a new pending publisher"*.
3. Fill in exactly:
   - **PyPI Project Name**: `scribeflow`
   - **Owner**: `htahaozlu`
   - **Repository name**: `scribeflow`
   - **Workflow name**: `publish.yml`
   - **Environment name**: `pypi`
4. Save. Once the first publish succeeds, the project exists and the pending
   publisher becomes a normal trusted publisher.

> If the project already exists on PyPI, add the publisher from the project page
> instead: **Manage project → Settings → Publishing → Add a publisher**, with the
> same four values (owner `htahaozlu`, repo `scribeflow`, workflow `publish.yml`,
> environment `pypi`).

### 2. Create the `pypi` GitHub Environment

The publish job declares `environment: pypi`, so it must exist in the repo:

1. In GitHub: **Settings → Environments → New environment** → name it `pypi`
   (the name must match `publish.yml` exactly).
2. Optionally add a **required reviewer** as a deploy gate so a human approves
   each PyPI upload. (Recommended for an extra publish checkpoint.)
3. No secrets are needed — OIDC handles authentication.

### 3. (Optional) TestPyPI dry run

To rehearse end-to-end without touching real PyPI, register a matching pending
publisher on <https://test.pypi.org> and point the publish action at TestPyPI
with `repository-url: https://test.pypi.org/legacy/`. Remove it before the real
release.

---

## Verifying a publish

After the GitHub Release is published:

1. Watch the **publish** workflow in the repo's **Actions** tab — it should be
   green, with the upload step reporting success (or *skipped existing* on a
   re-run).
2. Confirm the new version on PyPI: <https://pypi.org/project/scribeflow/>.
3. Smoke-test the published artifact from a clean environment:

   ```bash
   python -m venv /tmp/scribeflow-check && /tmp/scribeflow-check/bin/pip install scribeflow
   /tmp/scribeflow-check/bin/scribeflow --version   # should print: scribeflow X.Y.Z
   /tmp/scribeflow-check/bin/scribeflow doctor
   ```

If `publish.yml` fails with an authentication/permissions error, re-check that
the four trusted-publisher values match the repo/workflow/environment names
exactly, and that the `pypi` GitHub Environment exists.
