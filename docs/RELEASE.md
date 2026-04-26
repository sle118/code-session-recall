# Release Process

CSR is packaged as `code-session-recall` and exposes the `csr` console script.

## Publishing Model

Every push to `main` and every pull request builds and checks the package. PyPI
publishing happens only when a version tag is pushed:

```bash
git tag v0.1.1
git push origin v0.1.1
```

The workflow refuses to publish unless the tag exactly matches the version in
`pyproject.toml`. For example, tag `v0.1.1` requires:

```toml
[project]
version = "0.1.1"
```

PyPI package versions are immutable, so each published release needs a new
version number.

## One-Time PyPI Setup

Use PyPI Trusted Publishing so the GitHub workflow can publish without storing a
long-lived API token.

Configure a trusted publisher for:

- PyPI project: `code-session-recall`
- Owner/repository: this GitHub repository
- Workflow filename: `publish.yml`
- Environment: `pypi`

The workflow publish job grants `id-token: write`, which is required for the
trusted publishing token exchange.

## Release Checklist

1. Pick the next version number.
2. Update `pyproject.toml`.
3. Run local checks:

```bash
python -m py_compile csr.py
python -m build
python -m twine check dist/*
```

4. Commit the version change:

```bash
git add pyproject.toml
git commit -m "Release v0.1.1"
```

5. Push the commit and matching tag:

```bash
git push origin main
git tag v0.1.1
git push origin v0.1.1
```

6. Confirm the GitHub Actions `Package` workflow completed and PyPI shows the
   new release.

## Failed Publish

If a tag publish fails before PyPI accepts the files, fix the issue and rerun the
workflow or move the tag after the fix. If PyPI accepted the version, do not try
to overwrite it; bump `pyproject.toml` to the next version and publish a new tag.
