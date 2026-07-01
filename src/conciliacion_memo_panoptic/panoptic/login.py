from __future__ import annotations
import re
from collections.abc import Callable
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

LocatorFactory = Callable[[Page], Locator]

EMAIL_LOCATORS: list[LocatorFactory] = [
    lambda page: page.get_by_label(re.compile(r"Email address|Correo", re.I)),
    lambda page: page.get_by_role(
        "textbox", name=re.compile(r"Email address|Correo", re.I)
    ),
    lambda page: page.locator('input[type="email"]'),
    lambda page: page.locator('input[name="email"]'),
    lambda page: page.locator('input[name="username"]'),
    lambda page: page.locator('input[id*="email" i]'),
    lambda page: page.locator('input[id*="username" i]'),
    lambda page: page.locator('input[placeholder*="email" i]'),
    lambda page: page.locator('input[placeholder*="correo" i]'),
]

GENERIC_LOGIN_INPUTS: list[LocatorFactory] = [
    lambda page: page.locator('form input:not([type="hidden"]):not([disabled])'),
    lambda page: page.locator('input:not([type="hidden"]):not([disabled])'),
]

CONTINUE_LOCATORS: list[LocatorFactory] = [
    lambda page: page.get_by_role("button", name=re.compile(r"Continue|Continuar", re.I)),
    lambda page: page.locator('button:has-text("Continue")'),
    lambda page: page.locator('input[type="submit"][value="Continue"]'),
    lambda page: page.locator('button:has-text("Continuar")'),
    lambda page: page.locator('input[type="submit"][value="Continuar"]'),
]


def _is_login_context(page: Page) -> bool:
    return "signon.prgx.com" in page.url or "/openid-connect/auth" in page.url


def _first_visible_locator(
    page: Page,
    factories: list[LocatorFactory],
    timeout_ms: int,
) -> Locator | None:
    per_locator_timeout = max(500, min(timeout_ms, 2_000))
    for factory in factories:
        locator = factory(page).first
        try:
            locator.wait_for(state="visible", timeout=per_locator_timeout)
            return locator
        except PlaywrightTimeoutError:
            continue
    return None


def _email_input(page: Page, timeout_ms: int) -> Locator | None:
    email_input = _first_visible_locator(page, EMAIL_LOCATORS, timeout_ms)
    if email_input is not None:
        return email_input
    if _is_login_context(page):
        return _first_visible_locator(page, GENERIC_LOGIN_INPUTS, timeout_ms)
    return None


def _fill_email(locator: Locator, email: str) -> None:
    locator.click()
    locator.fill(email)
    try:
        if locator.input_value(timeout=1_000) == email:
            return
    except PlaywrightError:
        pass
    locator.press("Control+A")
    locator.type(email)


def submit_email_if_present(page: Page, email: str, timeout_ms: int = 8_000) -> bool:
    email_input = _email_input(page, timeout_ms)
    if email_input is None:
        return False
    _fill_email(email_input, email)
    continue_button = _first_visible_locator(page, CONTINUE_LOCATORS, 5_000)
    if continue_button is None:
        page.keyboard.press("Enter")
    else:
        continue_button.click()
    page.wait_for_timeout(750)
    return True