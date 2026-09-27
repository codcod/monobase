# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), following
[Semantic Versioning](https://semver.org/) (see [`RELEASING.md`](RELEASING.md)).

## [Unreleased]

## [0.1.0] - 2026-09-27

### Added

- `monobase.repository`: `AbstractRepository[T]`.
- `monobase.uow`: `AbstractUnitOfWork`, `SqlAlchemyUnitOfWork`.
- `monobase.db`: `make_engine(dsn)`.
- `monobase.migrations`: `run_migrations_online(target_metadata, dsn)`,
  keeping `alembic_version` in the target schema.
- `monobase.config`: `read_config(path)`, `setup_logging(level)`.
- `monobase.outbox`: `outbox_table(metadata, schema)`, `OutboxRow`,
  `OutboxRepository` (bound by a service's unit of work) and
  `run_relay(engine, table, deliver)`, which delivers at-least-once: a row is
  marked published only after `deliver` returns, and a failing row doesn't
  block the rest.
