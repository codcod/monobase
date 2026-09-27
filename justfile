# monobase is a library, not a deployable service — no run/docker/
# migrate targets here.

# List available recipes (default when running `just` with no args)
[group('dev')]
list:
    @just --list

# Sync the package + dev group into .venv
[group('dev')]
install:
    uv sync

[group('test')]
test: install
    uv run pytest -q

# Auto-fix and reformat
[group('quality')]
fmt: install
    uv run ruff check --fix src tests
    uv run ruff format src tests

# Lint + format-check + type-check (ty only checks src — tests use loose
# fakes/doubles that aren't meant to type-check as the real thing)
[group('quality')]
lint: install
    uv run ruff check src tests
    uv run ruff format --check src tests
    uv run ty check src

# Build the sdist and wheel into dist/
[group('build')]
build:
    uv build

[group('dev')]
clean:
    rm -rf dist
    find . -name __pycache__ -type d -exec rm -rf {} +

# Lint + format-check + type-check + test (ci.yml also runs `uv build`)
[group('ci')]
ci: lint test
