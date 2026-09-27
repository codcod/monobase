# Releasing

Releases are SemVer git tags `vX.Y.Z` on `main`. There is no package index:
consumers pin the tag's GitHub archive URL. There is no release automation;
this is a manual process.

## Cutting a release

**1. Decide what changed.**

```sh
git log "$(git describe --tags --abbrev=0)..HEAD" --oneline
```

**2. Stamp the changelog and bump the version.** In
[`CHANGELOG.md`](CHANGELOG.md), move the `[Unreleased]` entries under a new
`## [X.Y.Z] - YYYY-MM-DD` heading, and bump `version = "..."` in
[`pyproject.toml`](pyproject.toml). Commit both together on the release's
branch and merge it to `main`.

**3. Tag `main` after the merge**, never a feature branch:

```sh
git checkout main && git pull
git tag vX.Y.Z
git push origin vX.Y.Z
curl -sfIL https://github.com/codcod/monolith-base/archive/refs/tags/vX.Y.Z.tar.gz
```

## Upgrading a consumer

Change the tag in the consumer's `[tool.uv.sources]` URL, then `uv lock` and
run its tests:

```toml
monolith-base = { url = "https://github.com/codcod/monolith-base/archive/refs/tags/vX.Y.Z.tar.gz" }
```

## Validating locally before tagging

```sh
just lint
just test
just build
```

## Versioning

Semantic versioning. While below `1.0.0`, a minor release may break the API
and must label it `### Breaking` in the changelog entry; a patch release may
not break it.
