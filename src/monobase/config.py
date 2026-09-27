import logging
import time
import tomllib
import typing as tp


def read_config(path: str) -> dict[str, tp.Any]:
    """
    Read a TOML configuration file. Each service declares its own TypedDict
    over the result.
    """
    with open(path, "rb") as f:
        return tomllib.load(f)


def setup_logging(level: str | None = "WARNING") -> None:
    """
    Setup logging for an application. An unknown or missing level name
    falls back to WARNING.
    """
    logging.basicConfig(
        level=logging.getLevelNamesMapping().get(level or "WARNING", logging.WARNING),
        format="%(asctime)s [%(module)s] %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S %Z",
        # Without force=True this is a no-op whenever the root logger
        # already has handlers (e.g. under pytest, or any host process
        # that configured logging first).
        force=True,
    )
    # UTC, not local time — containers shouldn't need a timezone package
    # just to log, and logs from every service line up on one clock.
    logging.Formatter.converter = time.gmtime
