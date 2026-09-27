# Releasing

Releases are SemVer git tags `vX.Y.Z` on `main`. There is no package index:
consumers pin the tag's GitHub archive URL. Pushing a tag runs
[`release.yml`](.github/workflows/release.yml), which builds the package and
opens a **draft** GitHub release; publishing it is a manual step.

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
curl -sfIL https://github.com/codcod/monobase/archive/refs/tags/vX.Y.Z.tar.gz
```

**4. Publish the draft.** The workflow fails if the tag doesn't match
`pyproject.toml`'s version or the changelog has no `[X.Y.Z]` section.
Otherwise it creates a draft release with that section as notes and the
wheel and sdist attached. Review it under GitHub → Releases and publish it
(or `gh release edit vX.Y.Z --draft=false`).

## Upgrading a consumer

Change the tag in the consumer's `[tool.uv.sources]` URL, then `uv lock` and
run its tests:

```toml
monobase = { url = "https://github.com/codcod/monobase/archive/refs/tags/vX.Y.Z.tar.gz" }
```

## Validating locally before tagging

```sh
just ci
```

## Versioning

Semantic versioning. While below `1.0.0`, a minor release may break the API
and must label it `### Breaking` in the changelog entry; a patch release may
not break it.
