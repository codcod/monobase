import logging

from monolith_base.config import read_config, setup_logging


def test_read_config_parses_toml(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[inbox]\ndb = "x"\nlog_level = "DEBUG"\n')

    config = read_config(str(config_file))

    assert config == {"inbox": {"db": "x", "log_level": "DEBUG"}}


def test_setup_logging_accepts_level_name():
    setup_logging("DEBUG")

    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG


def test_setup_logging_none_falls_back_to_warning():
    setup_logging(None)

    assert logging.getLogger().getEffectiveLevel() == logging.WARNING


def test_setup_logging_unknown_name_falls_back_to_warning():
    setup_logging("CHATTY")

    assert logging.getLogger().getEffectiveLevel() == logging.WARNING
