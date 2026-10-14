# Releasing

## PyPI (one-time setup, ~5 minutes)

Publishing uses PyPI **trusted publishing** (OIDC) — no tokens stored anywhere.

1. Create an account at https://pypi.org (enable 2FA).
2. Go to https://pypi.org/manage/account/publishing/ and add a **pending
   publisher** with exactly:
   - PyPI project name: `gitfreeze`
   - Owner: `pantha704`
   - Repository name: `gitfreeze`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. Done. The first release creates the project.

## Cutting a release

1. Bump `version` in `pyproject.toml` and `src/gitfreeze/__init__.py`; add a
   CHANGELOG entry; commit.
2. Tag and publish a GitHub release:

   ```sh
   git tag v0.1.0 && git push origin v0.1.0
   gh release create v0.1.0 --title "gitfreeze v0.1.0" --notes-file CHANGELOG.md
   ```

   The `publish.yml` workflow builds the sdist + wheel and publishes to PyPI
   on release.

## Manual publish (fallback)

```sh
uv build                 # dist/gitfreeze-*.tar.gz + *.whl
uv publish               # requires an API token via UV_PUBLISH_TOKEN
```

Verify:

```sh
pipx run --spec gitfreeze gitfreeze --version
```
