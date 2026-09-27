# Packaging

`monobase` is one standalone package (not a workspace member), built
with `hatchling`:

```
pyproject.toml          name "monobase"; extras declared as they land
justfile                install, test, lint, fmt, build, clean, ci
src/monobase/           regular top-level package, ships py.typed
tests/                  unit tests, no I/O (fake engine/connection/transaction)
.github/workflows/ci.yml, release.yml
```

`monobase` is a regular package, not a namespace package, so it can't
collide with a consumer's own namespace.

## Dependencies

`sqlalchemy[asyncio]`, `asyncpg` and `alembic`, lower bounds only. Each
consumer's `uv.lock` does the pinning. `requires-python = ">=3.13"` with no
upper bound. Optional extras (`[aiohttp]`, `[outbox]`, `[metrics]`) will be
declared as they land, so a consumer that doesn't install one never pulls its
dependencies.

This repo's own `uv.lock` is committed; CI syncs with `--locked`.

## Working on it

```sh
just              # lists recipes
just test         # uv run pytest -q
just lint         # ruff check, ruff format --check, ty check src
just build        # uv build → dist/*.whl and dist/*.tar.gz
```

## Tooling

- **`uv`** for dependencies, the lockfile and `uv build`.
- **`ruff`** for linting and formatting (line length 88, `py313`, double
  quotes — see `[tool.ruff]` in [`pyproject.toml`](pyproject.toml)).
- **`ty`** for type-checking, scoped to `src/` — test doubles under `tests/`
  use loose fakes that aren't meant to type-check against the real classes.
- **GitHub Actions** ([`ci.yml`](.github/workflows/ci.yml)) runs lint, tests
  and the build on Python 3.13 and 3.14; `just ci` runs the same steps on the
  local interpreter. [`release.yml`](.github/workflows/release.yml) drafts a
  GitHub release on each `vX.Y.Z` tag.
