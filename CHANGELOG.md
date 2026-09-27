# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), following
[Semantic Versioning](https://semver.org/) (see [`RELEASING.md`](RELEASING.md)).

## [Unreleased]

## [0.1.0] - 2026-09-27

Extracted from monolith's `stelo-base`.

### Added

- `monobase.repository`: `AbstractRepository[T]`.
- `monobase.uow`: `AbstractUnitOfWork`, `SqlAlchemyUnitOfWork`.
- `monobase.db`: `make_engine(dsn)`.
- `monobase.migrations`: `run_migrations_online(target_metadata, dsn)`,
  keeping `alembic_version` in the target schema.
- `monobase.config`: `read_config(path)`, `setup_logging(level)`.

### Changed

Compared with `stelo-base`:

- `setup_logging(level: str | None = "WARNING")` takes the level name instead
  of a monolith `Config`; `None` or an unknown name falls back to `WARNING`.
- `read_config(path) -> dict[str, Any]` no longer returns the monolith-typed
  `dict[str, Config]`, and its parameter is renamed `fn` → `path`.
