"""Chrome WebDriver factory.

Selenium >= 4.6 ships Selenium Manager, which downloads the chromedriver that matches the installed
Chrome. Google publishes no chromedriver for ARM Linux (Raspberry Pi), so there the system Chromium and
its distribution chromedriver are used instead (``sudo apt install chromium chromium-driver``).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver

import paths

_LINUX_BROWSERS = ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome")


def _system_chrome() -> tuple[Optional[str], Optional[str]]:
    """(chromedriver, browser) installed by the Linux distribution, or (None, None) to let Selenium Manager decide."""
    if os.name == "nt":
        return None, None
    driver = shutil.which("chromedriver")
    browser = next((path for path in _LINUX_BROWSERS if Path(path).exists()), None)
    return (driver, browser) if driver and browser else (None, None)


def create_driver(url: str, keep_session: bool = False, headless: bool = False) -> WebDriver:
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    if headless:
        options.add_argument("--headless=new")

    if keep_session:
        # Dedicated Chrome profile inside the project (git-ignored), one per bot profile, so the
        # "remember me" cookie survives between runs and two airlines never share a browser.
        session = paths.current().session
        session.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={session.resolve()}")

    chromedriver, browser = _system_chrome()
    if chromedriver:
        options.binary_location = browser
        driver = webdriver.Chrome(service=Service(executable_path=chromedriver), options=options)
    else:
        driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(60)
        driver.get(url)
    except BaseException:
        # Nobody else holds this driver yet: an orphan Chrome would keep the profile folder locked and
        # every automatic restart would then fail with "user data directory is already in use".
        try:
            driver.quit()
        except Exception:  # noqa: BLE001 - the original error is the one worth reporting
            pass
        raise
    return driver
