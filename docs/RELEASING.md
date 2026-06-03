# Releasing

The maintainer checklist for cutting a new Yazıt release. The version lives in a
single place; a SemVer tag drives the rest. For how the CI publish machinery and
the one-time PyPI trusted-publisher setup work, see
[PUBLISHING.md](./PUBLISHING.md).

Releases follow [SemVer](https://semver.org/): `MAJOR.MINOR.PATCH`, tagged
`vX.Y.Z`.

---

## Checklist

### 1. Bump the version

The version is single-sourced in `src/yazit/__about__.py` (Hatchling reads it
via `[tool.hatch.version]`). Edit one line:

```python
# src/yazit/__about__.py
__version__ = "X.Y.Z"
```

Nothing else needs changing — the CLI (`yazit --version`) and the package
metadata both read from here.

### 2. Update the CHANGELOG

In [`CHANGELOG.md`](../CHANGELOG.md):

- Move the relevant items from `[Unreleased]` into a new `## [X.Y.Z] - YYYY-MM-DD`
  section (use today's date).
- Leave a fresh, empty `[Unreleased]` section at the top.
- Update the comparison links at the bottom.

### 3. Dry-run the build locally

Build and validate the distributions **before** tagging, so a broken build never
reaches CI or PyPI:

```bash
python -m pip install --upgrade build twine
rm -rf dist/
python -m build          # produces dist/*.whl and dist/*.tar.gz
twine check dist/*       # validates metadata + long description rendering
```

Optionally install the built wheel in a throwaway venv and smoke-test it:

```bash
python -m venv /tmp/yazit-rel && /tmp/yazit-rel/bin/pip install dist/*.whl
/tmp/yazit-rel/bin/yazit --version   # should print: yazit X.Y.Z
/tmp/yazit-rel/bin/yazit doctor
```

Both `python -m build` and `twine check dist/*` must succeed before continuing.

### 4. Commit

Commit the version bump + changelog together:

```bash
git add src/yazit/__about__.py CHANGELOG.md
git commit -m "release: vX.Y.Z"
git push origin main
```

### 5. Tag and push the tag

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

Pushing the `v*` tag triggers **`release.yml`**, which builds the sdist + wheel
on a clean runner and uploads them as the `dist` artifact.

### 6. Publish the GitHub Release

Pushing the tag builds, but does **not** publish to PyPI on its own. Create and
publish the GitHub Release from the tag to trigger the PyPI upload:

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes-file - <<'NOTES'
<paste the X.Y.Z section from CHANGELOG.md>
NOTES
```

(Or create it from the GitHub UI: **Releases → Draft a new release →** pick tag
`vX.Y.Z` → publish.) Publishing the release triggers **`publish.yml`**, which
uploads to PyPI via OIDC trusted publishing.

### 7. Verify CI + PyPI

- **Actions** tab: both `release` and `publish` workflows are green.
- PyPI shows the new version: <https://pypi.org/project/yazit/>.
- Smoke-test the published package from a clean environment:

  ```bash
  python -m venv /tmp/yazit-verify && /tmp/yazit-verify/bin/pip install yazit
  /tmp/yazit-verify/bin/yazit --version   # yazit X.Y.Z
  ```

If `publish.yml` was re-run, `skip-existing: true` makes already-uploaded files a
no-op — safe to retry.

---

## Quick reference

```bash
# 1. bump src/yazit/__about__.py  → __version__ = "X.Y.Z"
# 2. update CHANGELOG.md          → new [X.Y.Z] - YYYY-MM-DD section
# 3. local dry run
python -m build && twine check dist/*
# 4. commit
git add src/yazit/__about__.py CHANGELOG.md && git commit -m "release: vX.Y.Z" && git push
# 5. tag
git tag vX.Y.Z && git push origin vX.Y.Z
# 6. publish the GitHub Release (triggers PyPI upload)
gh release create vX.Y.Z --title "vX.Y.Z" --notes-file -
# 7. verify Actions are green + https://pypi.org/project/yazit/
```
