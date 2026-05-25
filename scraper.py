import csv
import json
import os
import time

import requests
from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

load_dotenv(".env")

VISITED_LINKS_FOLDER = "visited_links"
SCRAPED_JOBS_FOLDER = "scraped_jobs"

SUMMER_INTERNSHIPS_URL = "https://github.com/SimplifyJobs/Summer2026-Internships"
SUMMER_LINKS_FILE = "summer_internships.json"
SUMMER_CSV_FILE = "summer_internships.csv"

NEW_GRAD_URL = "https://github.com/SimplifyJobs/New-Grad-Positions"
NEW_GRAD_LINKS_FILE = "new_grad.json"
NEW_GRAD_CSV_FILE = "new_grad.csv"

OFF_SEASON_INTERNSHIPS_URL = (
    "https://github.com/SimplifyJobs/Summer2026-Internships/blob/dev/README-Off-Season.md"
)
OFF_SEASON_INTERNSHIPS_LINKS_FILE = "off_season_internships.json"

try:
    SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]
except KeyError:
    SLACK_WEBHOOK = "Token not available!"

try:
    NEW_GRAD_WEBHOOK = os.environ["NEW_GRAD_WEBHOOK"]
except KeyError:
    NEW_GRAD_WEBHOOK = "Token not available!"


def send_slack_message(message, webhook):
    if not webhook or webhook == "Token not available!":
        print("Slack webhook not configured; skipping notification.")
        return
    payload = '{"text":"%s"}' % message
    response = requests.post(webhook, data=payload, timeout=30)
    if not response.ok:
        print(f"Slack post failed: {response.status_code} {response.text}")


def normalize_application_link(url: str) -> str:
    """Canonical job URL for deduplication (strip tracking params)."""
    if not url or url == "N/A":
        return url
    normalized = url.replace("&amp;", "&")
    for suffix in (
        "?utm_source=Simplify&ref=Simplify",
        "&utm_source=Simplify&ref=Simplify",
        "?utm_source=GHList&utm_medium=company",
        "&utm_source=GHList&utm_medium=company",
    ):
        if suffix in normalized:
            normalized = normalized.replace(suffix, "")
    return normalized.rstrip("?&")


def scrape_internships(page: Page, url: str) -> list[dict]:
    """
    Scrapes job listings from a Simplify Jobs GitHub README using Playwright.

    Returns a list of dicts with Company, Role, Location, Application Link, Date Posted.
    """
    try:
        print(f"Fetching data from {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_selector(
            "markdown-accessiblity-table table tbody tr",
            timeout=60_000,
        )
        print("Successfully loaded page content.")

        jobs = page.evaluate(
            """() => {
            const table = document.querySelector('markdown-accessiblity-table table');
            if (!table) return [];

            return Array.from(table.querySelectorAll('tbody tr'))
                .map((row) => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length !== 5) return null;

                    const linkEl = cells[3].querySelector('a[href]');
                    return {
                        Company: cells[0].innerText.trim(),
                        Role: cells[1].innerText.trim(),
                        Location: cells[2].innerText.trim(),
                        'Application Link': linkEl ? linkEl.href : 'N/A',
                        'Date Posted': cells[4].innerText.trim(),
                    };
                })
                .filter(Boolean);
        }"""
        )

        print(f"Found {len(jobs)} listings.")
        return jobs

    except Exception as e:
        print(f"Scraping failed: {e}")
        return []


def load_visited_links(filepath) -> set[str]:
    """Load visited links from a JSON file. Returns an empty set if file doesn't exist."""
    if os.path.exists(filepath):
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
                raw = data.get("visited_links", [])
                return {normalize_application_link(link) for link in raw}
        except (json.JSONDecodeError, KeyError):
            print(f"Could not parse {filepath}; treating as empty.")
    return set()


def save_visited_links(filepath, visited_links: set[str]):
    """Save visited links to a JSON file."""
    directory = os.path.dirname(filepath)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({"visited_links": sorted(visited_links)}, f, indent=2)


def write_jobs_csv(csv_path: str, jobs: list[dict]):
    """Write the full current scrape to a single CSV."""
    os.makedirs(SCRAPED_JOBS_FOLDER, exist_ok=True)
    full_path = os.path.join(SCRAPED_JOBS_FOLDER, csv_path)
    with open(full_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Company", "Role", "Location", "Application Link", "Date Posted"],
        )
        writer.writeheader()
        writer.writerows(jobs)


def extract_internships(
    page: Page,
    url: str,
    links_filename: str,
    slack_webhook: str,
    csv_filename: str,
):
    start_time = time.time()
    links_filepath = os.path.join(VISITED_LINKS_FOLDER, links_filename)

    latest_internships = scrape_internships(page, url)

    if not latest_internships:
        print("Scraping failed. No data was processed.")
        print(f"\nTotal time taken: {time.time() - start_time:.2f} seconds")
        return

    write_jobs_csv(csv_filename, latest_internships)

    visited_links = load_visited_links(links_filepath)
    current_links = {
        normalize_application_link(job["Application Link"]) for job in latest_internships
    }
    new_links = current_links - visited_links

    print(f"{len(current_links)} scraped, {len(new_links)} new, {len(current_links) - len(new_links)} already seen.")

    if new_links:
        new_internships = [
            job
            for job in latest_internships
            if normalize_application_link(job["Application Link"]) in new_links
        ]

        print(f"Found {len(new_internships)} new positions:")
        for job in new_internships:
            print(f"  - {job['Company']}: {job['Role']}")

        send_slack_message(format_internship_digest(new_internships), slack_webhook)
        visited_links.update(new_links)
    else:
        print("No new positions since last run.")

    save_visited_links(links_filepath, visited_links)

    elapsed = time.time() - start_time
    print(f"\nTotal time taken: {elapsed:.2f} seconds")


def remove_utm_params(url):
    """Remove UTM parameters from URL for Slack notifications."""
    return normalize_application_link(url)


def format_internship_digest(internships):
    """Formats a list of new internships into a single digest message."""
    message_lines = [f"🔥 *{len(internships)} New Jobs Found!*"]

    for job in internships:
        company = f"*{job['Company']}*"
        role = job["Role"]
        short_role = (role[:40] + "...") if len(role) > 43 else role
        clean_url = remove_utm_params(job["Application Link"])
        link = f"<{clean_url}|{short_role}>"
        message_lines.append(f"• {company} - {link}")

    return message_lines[0] + "\n\n" + "\n".join(message_lines[1:])


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            extract_internships(
                page,
                SUMMER_INTERNSHIPS_URL,
                SUMMER_LINKS_FILE,
                SLACK_WEBHOOK,
                SUMMER_CSV_FILE,
            )
            extract_internships(
                page,
                NEW_GRAD_URL,
                NEW_GRAD_LINKS_FILE,
                NEW_GRAD_WEBHOOK,
                NEW_GRAD_CSV_FILE,
            )
            # extract_internships(page, OFF_SEASON_INTERNSHIPS_URL, OFF_SEASON_INTERNSHIPS_LINKS_FILE, "idk", "...")
        finally:
            browser.close()
