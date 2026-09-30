"""Chrome WebDriver factory.

Selenium >= 4.6 ships Selenium Manager, which downloads the chromedriver that
matches the installed Chrome. No bundled binaries and no webdriver-manager.
"""
from __future__ import annotations

from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver

SESSION_DIR = Path("config/session")


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
        # Dedicated Chrome profile inside the project (git-ignored) so the
        # "remember me" cookie survives between runs.
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={SESSION_DIR.resolve()}")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    driver.get(url)
    return driver
