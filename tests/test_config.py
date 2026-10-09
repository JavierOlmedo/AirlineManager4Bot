import os
from configparser import ConfigParser

import pytest

import paths
from config import AppConfig

DEFAULTS = """[settings]
fuel_price_good = 650
cash_reserve = 100000

[options]
dry_run = off
telegram = on

[web]
port = 8744
remote_instances =

[selectors]
money = //*[@id='headerAccount']
"""


@pytest.fixture
def files(tmp_path):
    defaults = tmp_path / "defaults.ini"
    defaults.write_text(DEFAULTS, encoding="utf-8")
    return defaults, tmp_path / "settings.ini", tmp_path / "secrets.ini"


def make(files) -> AppConfig:
    defaults, settings, secrets = files
    return AppConfig(settings_file=settings, secrets_file=secrets, defaults_file=defaults)


def test_reads_defaults_without_a_settings_file(files):
    cfg = make(files)
    assert cfg.get_int("settings", "fuel_price_good") == 650
    assert cfg.get_bool("options", "telegram") is True
    assert cfg.get("web", "remote_instances") == ""
    assert cfg.get("app", "language") == ""
    assert cfg.get_int("settings", "missing", 7) == 7


def test_settings_override_defaults_and_only_changes_are_saved(files):
    _, settings, _ = files
    cfg = make(files)
    cfg.set("settings", "fuel_price_good", 600)
    cfg.set("settings", "cash_reserve", 100000)  # same as the default: nothing to keep
    cfg.set("web", "remote_instances", "10.0.0.5")
    cfg.save()
    saved = ConfigParser(interpolation=None)
    saved.read(settings, encoding="utf-8")
    assert dict(saved.items("settings")) == {"fuel_price_good": "600"}
    assert saved.get("web", "remote_instances") == "10.0.0.5"
    assert make(files).get_int("settings", "fuel_price_good") == 600


def test_back_to_the_default_removes_the_override(files):
    _, settings, _ = files
    cfg = make(files)
    cfg.set("options", "dry_run", "on")
    cfg.save()
    version = cfg.version
    cfg.set("options", "dry_run", "off")
    assert cfg.version == version + 1
    cfg.save()
    saved = ConfigParser(interpolation=None)
    saved.read(settings, encoding="utf-8")
    assert not saved.has_section("options")
    assert cfg.get_bool("options", "dry_run") is False


def test_old_full_copy_is_tidied_and_never_pins_selectors(files):
    _, settings, _ = files
    settings.write_text(DEFAULTS.replace("headerAccount", "oldHeader").replace("650", "700"), encoding="utf-8")
    cfg = make(files)
    assert cfg.get("selectors", "money") == "//*[@id='headerAccount']"
    assert cfg.get_int("settings", "fuel_price_good") == 700
    cfg.save()
    text = settings.read_text(encoding="utf-8")
    assert "selectors" not in text and "cash_reserve" not in text and "fuel_price_good = 700" in text


def test_forget_credentials_keeps_the_other_secrets(files):
    _, _, secrets = files
    secrets.write_text("[login]\nusername = a@b.c\npassword = x\n\n[telegram]\nbot_token = 1:AA\nchat_id = 2\n",
                       encoding="utf-8")
    cfg = make(files)
    assert cfg.forget_credentials() is True
    left = ConfigParser(interpolation=None)
    left.read(secrets, encoding="utf-8")
    assert left.sections() == ["telegram"]
    assert cfg.forget_credentials() is False


def test_forget_credentials_deletes_a_login_only_file(files):
    _, _, secrets = files
    secrets.write_text("[login]\nusername = a@b.c\npassword = x\n", encoding="utf-8")
    assert make(files).forget_credentials() is True
    assert not secrets.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_secrets_are_owner_only(files):
    _, _, secrets = files
    cfg = make(files)
    cfg.set_credentials("a@b.c", "x", persist=True)
    assert secrets.stat().st_mode & 0o777 == 0o600
    secrets.chmod(0o644)
    make(files)  # loading an old world-readable file tightens it
    assert secrets.stat().st_mode & 0o777 == 0o600


def test_write_atomic_replaces_and_leaves_no_temp_file(tmp_path):
    target = tmp_path / "state.json"
    paths.write_atomic(target, "one")
    paths.write_atomic(target, "two\n")
    assert target.read_bytes() == b"two" + os.linesep.encode()
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]
