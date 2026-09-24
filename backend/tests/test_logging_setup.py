import logging

from app.logging_setup import quiet_http_logging


def test_quiet_http_logging_sets_httpx_and_httpcore_to_warning():
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)

    quiet_http_logging()

    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING


def test_quiet_http_logging_overrides_basic_config_raising_root_level():
    # This is the actual failure mode: basicConfig(level=INFO) raises the
    # root logger to INFO, and httpx (with no level of its own) would
    # inherit that and start logging every request URL -- key included.
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)

    quiet_http_logging()

    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
