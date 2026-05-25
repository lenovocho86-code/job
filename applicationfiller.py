"""
Fill job application forms with Playwright.

Required .env variables:
  FIRST_NAME, LAST_NAME, EMAIL

Optional .env variables:
  PHONE, LINKEDIN_URL, GITHUB_URL, WEBSITE, LOCATION, CITY, STATE, COUNTRY,
  RESUME_PATH, COVER_LETTER_PATH, UNIVERSITY, DEGREE, GRADUATION_YEAR,
  AUTHORIZED_TO_WORK (yes/no), REQUIRES_SPONSORSHIP (yes/no)

Usage:
  python applicationfiller.py "https://jobs.ashbyhq.com/..."
  python applicationfiller.py --headless "https://job-boards.greenhouse.io/..."
"""

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from playwright.sync_api import Locator, Page, sync_playwright

load_dotenv(".env")

APPLY_BUTTON_PATTERN = re.compile(
    r"apply(?:\s+(?:now|for\s+this\s+job|for\s+position))?$|submit\s+application|start\s+application",
    re.I,
)


@dataclass
class Profile:
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    website: str = ""
    location: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    resume_path: str = ""
    cover_letter_path: str = ""
    university: str = ""
    degree: str = ""
    graduation_year: str = ""
    authorized_to_work: str = ""
    requires_sponsorship: str = ""


FIELD_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("first_name", re.compile(r"\b(first|given|fname)\b", re.I)),
    ("last_name", re.compile(r"\b(last|family|lname|surname)\b", re.I)),
    ("email", re.compile(r"\b(e[- ]?mail)\b", re.I)),
    ("phone", re.compile(r"\b(phone|mobile|tel(?:ephone)?)\b", re.I)),
    ("linkedin_url", re.compile(r"\blinkedin\b", re.I)),
    ("github_url", re.compile(r"\bgithub\b", re.I)),
    ("website", re.compile(r"\b(website|portfolio|personal\s+site|url)\b", re.I)),
    ("location", re.compile(r"\b(location|address)\b", re.I)),
    ("city", re.compile(r"\bcity\b", re.I)),
    ("state", re.compile(r"\b(state|province|region)\b", re.I)),
    ("country", re.compile(r"\bcountry\b", re.I)),
    ("university", re.compile(r"\b(school|university|college|institution)\b", re.I)),
    ("degree", re.compile(r"\b(degree|major|discipline)\b", re.I)),
    ("graduation_year", re.compile(r"\b(graduation|grad\s+year|expected\s+graduation)\b", re.I)),
    ("resume_path", re.compile(r"\b(resume|cv|r[eé]sum[eé])\b", re.I)),
    ("cover_letter_path", re.compile(r"\b(cover\s+letter)\b", re.I)),
    (
        "authorized_to_work",
        re.compile(
            r"\b(authorized|authorised|legally\s+authorized|work\s+authorization|eligible\s+to\s+work)\b",
            re.I,
        ),
    ),
    ("requires_sponsorship", re.compile(r"\b(sponsor|visa|immigration)\b", re.I)),
]


def load_profile() -> Profile:
    first_name = os.getenv("FIRST_NAME", "").strip()
    last_name = os.getenv("LAST_NAME", "").strip()
    email = os.getenv("EMAIL", "").strip()
    missing = [
        name
        for name, value in [
            ("FIRST_NAME", first_name),
            ("LAST_NAME", last_name),
            ("EMAIL", email),
        ]
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required .env variables: {', '.join(missing)}")

    return Profile(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=os.getenv("PHONE", "").strip(),
        linkedin_url=os.getenv("LINKEDIN_URL", "").strip(),
        github_url=os.getenv("GITHUB_URL", "").strip(),
        website=os.getenv("WEBSITE", "").strip(),
        location=os.getenv("LOCATION", "").strip(),
        city=os.getenv("CITY", "").strip(),
        state=os.getenv("STATE", "").strip(),
        country=os.getenv("COUNTRY", "").strip(),
        resume_path=os.getenv("RESUME_PATH", "").strip(),
        cover_letter_path=os.getenv("COVER_LETTER_PATH", "").strip(),
        university=os.getenv("UNIVERSITY", "").strip(),
        degree=os.getenv("DEGREE", "").strip(),
        graduation_year=os.getenv("GRADUATION_YEAR", "").strip(),
        authorized_to_work=os.getenv("AUTHORIZED_TO_WORK", "").strip(),
        requires_sponsorship=os.getenv("REQUIRES_SPONSORSHIP", "").strip(),
    )


def profile_value(profile: Profile, field_key: str) -> str:
    return getattr(profile, field_key, "") or ""


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def field_descriptor(element: Locator) -> str:
    parts: list[str] = []
    for attr in ("name", "id", "placeholder", "aria-label", "autocomplete", "data-testid", "type"):
        value = element.get_attribute(attr)
        if value:
            parts.append(value)

    try:
        element_id = element.get_attribute("id")
        if element_id:
            label = element.page.locator(f'label[for="{element_id}"]').first
            if label.count():
                parts.append(label.inner_text(timeout=500))
    except Exception:
        pass

    try:
        parent_label = element.locator("xpath=ancestor::label[1]")
        if parent_label.count():
            parts.append(parent_label.first.inner_text(timeout=500))
    except Exception:
        pass

    return normalize_text(" ".join(parts))


def match_field(descriptor: str, input_type: str | None) -> str | None:
    if input_type == "file":
        if re.search(r"\b(cover\s+letter)\b", descriptor, re.I):
            return "cover_letter_path"
        return "resume_path"

    for field_key, pattern in FIELD_RULES:
        if pattern.search(descriptor):
            return field_key
    return None


def yes_no_value(raw: str) -> bool | None:
    value = normalize_text(raw)
    if value in {"yes", "y", "true", "1"}:
        return True
    if value in {"no", "n", "false", "0"}:
        return False
    return None


def is_visible(element: Locator) -> bool:
    try:
        return element.is_visible() and element.is_enabled()
    except Exception:
        return False


def click_apply_if_needed(page: Page) -> None:
    candidates = page.get_by_role("link", name=APPLY_BUTTON_PATTERN).all()
    candidates += page.get_by_role("button", name=APPLY_BUTTON_PATTERN).all()

    for candidate in candidates:
        if not is_visible(candidate):
            continue
        try:
            candidate.click(timeout=5_000)
            page.wait_for_load_state("domcontentloaded", timeout=30_000)
            time.sleep(1)
            print("Clicked apply button.")
            return
        except Exception:
            continue


def fill_text_like(element: Locator, value: str) -> None:
    element.click(timeout=3_000)
    element.fill(value, timeout=5_000)


def fill_native_select(element: Locator, value: str) -> None:
    tag = (element.evaluate("el => el.tagName") or "").lower()
    if tag != "select":
        return

    for strategy in ("label", "value"):
        try:
            if strategy == "label":
                element.select_option(label=value, timeout=2_000)
            else:
                element.select_option(value=value, timeout=2_000)
            return
        except Exception:
            pass

    options = element.locator("option").all()
    target = normalize_text(value)
    for option in options:
        text = normalize_text(option.inner_text(timeout=500))
        if target in text or text in target:
            option_value = option.get_attribute("value")
            if option_value:
                element.select_option(value=option_value, timeout=2_000)
                return


def fill_custom_combobox(element: Locator, value: str) -> None:
    fill_text_like(element, value)
    time.sleep(0.4)
    page = element.page
    options = page.locator('[role="option"], [role="listbox"] li, .select__option').all()
    target = normalize_text(value)
    for option in options:
        if not is_visible(option):
            continue
        text = normalize_text(option.inner_text(timeout=500))
        if target in text or text in target or (len(target) >= 3 and text.startswith(target[:3])):
            option.click(timeout=3_000)
            return


def fill_yes_no(element: Locator, value: str) -> None:
    choice = yes_no_value(value)
    if choice is None:
        return

    tag = (element.evaluate("el => el.tagName") or "").lower()
    input_type = (element.get_attribute("type") or "").lower()

    if tag == "select":
        fill_native_select(element, "Yes" if choice else "No")
        return

    if input_type in {"radio", "checkbox"}:
        name = element.get_attribute("name")
        if not name:
            return
        yes_values = ('Yes', 'yes', 'true', '1')
        no_values = ('No', 'no', 'false', '0')
        values = yes_values if choice else no_values
        for val in values:
            target = element.page.locator(f'input[name="{name}"][value="{val}"]').first
            if target.count() and is_visible(target):
                target.check(timeout=3_000)
                return
        return

    role = element.get_attribute("role") or ""
    if role == "combobox":
        fill_custom_combobox(element, "Yes" if choice else "No")


def fill_file_input(element: Locator, path: str) -> None:
    if not path:
        return
    if not os.path.isfile(path):
        print(f"Skipping missing file: {path}")
        return
    element.set_input_files(path, timeout=10_000)


def fill_element(element: Locator, field_key: str, profile: Profile) -> bool:
    value = profile_value(profile, field_key)
    if not value and field_key not in {"authorized_to_work", "requires_sponsorship"}:
        return False

    tag = (element.evaluate("el => el.tagName") or "").lower()
    input_type = (element.get_attribute("type") or "text").lower()

    try:
        if input_type == "file" or field_key in {"resume_path", "cover_letter_path"}:
            fill_file_input(element, value)
            return True

        if field_key in {"authorized_to_work", "requires_sponsorship"}:
            fill_yes_no(element, value)
            return True

        if tag == "select" or element.get_attribute("role") == "combobox":
            if tag == "select":
                fill_native_select(element, value)
            else:
                fill_custom_combobox(element, value)
            return True

        if input_type in {"checkbox", "radio"}:
            if yes_no_value(value) is True:
                element.check(timeout=3_000)
            return True

        if tag in {"input", "textarea"}:
            fill_text_like(element, value)
            return True
    except Exception as exc:
        print(f"Could not fill {field_key}: {exc}")
        return False

    return False


def collect_fillable_elements(page: Page) -> list[Locator]:
    selectors = (
        "input:not([type='hidden']):not([type='submit']):not([type='button'])",
        "textarea",
        "select",
        '[role="combobox"]',
    )
    elements: list[Locator] = []
    seen: set[str] = set()

    for frame in page.frames:
        for selector in selectors:
            for element in frame.locator(selector).all():
                if not is_visible(element):
                    continue
                try:
                    key = element.evaluate(
                        """el => [
                            el.tagName,
                            el.type || '',
                            el.name || '',
                            el.id || '',
                            el.getAttribute('aria-label') || ''
                        ].join('|')"""
                    )
                except Exception:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                elements.append(element)
    return elements


def fill_application(page: Page, profile: Profile) -> int:
    filled = 0
    for element in collect_fillable_elements(page):
        descriptor = field_descriptor(element)
        input_type = element.get_attribute("type")
        field_key = match_field(descriptor, input_type)
        if not field_key:
            continue
        if fill_element(element, field_key, profile):
            print(f"Filled {field_key} ({descriptor or 'unlabeled field'})")
            filled += 1
    return filled


def run(url: str, headless: bool, wait_seconds: int) -> None:
    profile = load_profile()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        print(f"Opening {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        click_apply_if_needed(page)
        filled = fill_application(page, profile)
        print(f"Filled {filled} field(s). Review the form and submit manually.")
        if wait_seconds > 0:
            print(f"Keeping browser open for {wait_seconds}s...")
            time.sleep(wait_seconds)
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill job application forms with Playwright.")
    parser.add_argument("url", help="Application or job posting URL")
    parser.add_argument("--headless", action="store_true", help="Run browser without a visible window")
    parser.add_argument(
        "--wait",
        type=int,
        default=300,
        help="Seconds to keep the browser open after filling (default: 300, use 0 to close immediately)",
    )
    args = parser.parse_args()
    run(args.url, headless=args.headless, wait_seconds=args.wait)


if __name__ == "__main__":
    main()
