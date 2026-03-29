"""
Seek Job Scraper
Searches seek.com.au for product roles across Queensland and Remote Australia.

Usage:
    python seek_scraper.py
    python seek_scraper.py --pages 3
    python seek_scraper.py --output jobs.json
    python seek_scraper.py --keywords "Product Owner" "Product Manager" --pages 2

Install dependencies:
    pip install -r requirements.txt
    playwright install chromium
"""

import argparse
import asyncio
import json
import sys

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

DEFAULT_KEYWORDS = [
    "Product Owner",
    "Product Manager",
    "Senior Product Owner",
    "Product Analyst",
]

# Each location entry: (label, url_path, extra_params)
# Seek worktype=4 = Work from home / remote
LOCATIONS = [
    ("Queensland", "All-Queensland", ""),
    ("Remote (Australia)", "All-Australia", "worktype=4"),
]


def build_url(keywords: str, location_path: str, extra_params: str, page: int) -> str:
    slug = keywords.strip().lower().replace(" ", "-")
    url = f"https://www.seek.com.au/{slug}-jobs/in-{location_path}"
    params = []
    if extra_params:
        params.append(extra_params)
    if page > 1:
        params.append(f"page={page}")
    if params:
        url += "?" + "&".join(params)
    return url


def parse_jobs(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    for card in soup.select("article[data-card-type='JobCard']"):
        title_el = card.select_one("[data-automation='jobTitle']")
        company_el = card.select_one("[data-automation='jobCompany']")
        location_el = card.select_one("[data-automation='jobCardLocation']")
        salary_el = card.select_one("[data-automation='jobSalary']")
        date_el = card.select_one("[data-automation='jobListingDate']")
        link_el = card.select_one("a[data-automation='jobTitle']")

        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        job_url = None
        if link_el and link_el.get("href"):
            href = link_el["href"]
            job_url = href if href.startswith("http") else f"https://www.seek.com.au{href}"

        jobs.append({
            "title": title,
            "company": company_el.get_text(strip=True) if company_el else None,
            "location": location_el.get_text(strip=True) if location_el else None,
            "salary": salary_el.get_text(strip=True) if salary_el else None,
            "posted": date_el.get_text(strip=True) if date_el else None,
            "url": job_url,
        })

    return jobs


async def scrape_search(page, keywords: str, loc_label: str, loc_path: str, extra_params: str, pages: int) -> list[dict]:
    results = []
    for page_num in range(1, pages + 1):
        url = build_url(keywords, loc_path, extra_params, page_num)
        print(f"  [{loc_label}] page {page_num}: {url}", file=sys.stderr)

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_selector(
                "article[data-card-type='JobCard']",
                timeout=15000,
            )
        except Exception as e:
            print(f"  Warning: no results or timeout — {e}", file=sys.stderr)
            break

        html = await page.content()
        jobs = parse_jobs(html)

        if not jobs:
            print(f"  No jobs on page {page_num}, stopping.", file=sys.stderr)
            break

        print(f"  Found {len(jobs)} jobs.", file=sys.stderr)
        results.extend(jobs)

    return results


async def scrape(keywords_list: list[str], pages: int) -> list[dict]:
    seen_urls: set[str] = set()
    all_jobs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        for keywords in keywords_list:
            for loc_label, loc_path, extra_params in LOCATIONS:
                print(f"\nSearching: '{keywords}' in {loc_label}", file=sys.stderr)
                jobs = await scrape_search(page, keywords, loc_label, loc_path, extra_params, pages)
                for job in jobs:
                    url = job.get("url")
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    all_jobs.append(job)

        await browser.close()

    return all_jobs


def main():
    parser = argparse.ArgumentParser(description="Scrape product role jobs from seek.com.au")
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=DEFAULT_KEYWORDS,
        help="One or more job keyword strings to search (default: product roles)",
    )
    parser.add_argument("--pages", type=int, default=1, help="Pages per search (default: 1)")
    parser.add_argument("--output", help="Write results to this JSON file instead of stdout")
    args = parser.parse_args()

    jobs = asyncio.run(scrape(args.keywords, args.pages))

    result = json.dumps(jobs, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"\nWrote {len(jobs)} jobs to {args.output}", file=sys.stderr)
    else:
        print(result)

    print(f"\nTotal unique jobs scraped: {len(jobs)}", file=sys.stderr)


if __name__ == "__main__":
    main()
