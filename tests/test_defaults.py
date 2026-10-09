"""config/defaults.ini is the single source of the defaults: every setting the app shows must be there."""
from configparser import ConfigParser

import pytest

from conftest import ROOT
from settings_schema import ALL_FIELDS, ALL_SWITCHES, OPTION_DEFAULTS, TEXT_SETTINGS, clamp_settings, parse_int


@pytest.fixture(scope="module")
def defaults() -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    assert parser.read(ROOT / "config" / "defaults.ini", encoding="utf-8")
    return parser


def test_every_field_and_switch_has_a_default(defaults):
    for key, _ in ALL_FIELDS + TEXT_SETTINGS:
        assert defaults.has_option("settings", key), key
    for key, _ in ALL_SWITCHES:
        assert defaults.has_option("options", key), key


def test_option_fallbacks_agree_with_defaults_ini(defaults):
    for key, value in OPTION_DEFAULTS.items():
        assert defaults.getboolean("options", key) is value, key


def test_no_personal_data_in_defaults(defaults):
    assert defaults.get("web", "remote_instances").strip() == ""
    assert defaults.get("web", "host") == "127.0.0.1"
    assert not defaults.has_section("login") and not defaults.has_section("telegram")


def test_parse_int_and_clamp():
    assert parse_int("200,000") == 200000
    assert parse_int(" 42 ") == 42
    assert parse_int("abc") is None
    assert clamp_settings({"summary_hour": 30, "cycle_min_minutes": 0, "cycle_max_minutes": 0}) == \
        {"summary_hour": 23, "cycle_min_minutes": 1, "cycle_max_minutes": 1}
