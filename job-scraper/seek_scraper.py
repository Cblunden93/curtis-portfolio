"""
Seek Job Scraper
Usage:
    python seek_scraper.py --keywords "python developer" --location "melbourne" --pages 2
    python seek_scraper.py --keywords "data engineer" --location "sydney" --output jobs.json

Install dependencies:
    pip install -r requirements.txt
    playwright install chromium
"""

import argparse
import asyncio
import json
import sys
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


def build_url(keywords: str, location: str, page: int) -> str:
    slug = keywords.strip().lower().replace(" ", "-")
    loc = location.strip().lower().replace(" ", "-")
    url = f"https://www.seek.com.au/{slug}-jobs/in-{loc}"
    if page > 1:
        url += f"?page={page}"
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


async def scrape(keywords: str, location: str, pages: int) -> list[dict]:
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

        for page_num in range(1, pages + 1):
            url = build_url(keywords, location, page_num)
            print(f"Fetching page {page_num}: {url}", file=sys.stderr)

            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                # Wait for job cards to appear
                await page.wait_for_selector(
                    "article[data-card-type='JobCard']",
                    timeout=15000,
                )
            except Exception as e:
                print(f"Warning: page {page_num} timed out or had no results: {e}", file=sys.stderr)
                break

            html = await page.content()
            jobs = parse_jobs(html)

            if not jobs:
                print(f"No jobs found on page {page_num}, stopping.", file=sys.stderr)
                break

            print(f"Found {len(jobs)} jobs on page {page_num}.", file=sys.stderr)
            all_jobs.extend(jobs)

        await browser.close()

    return all_jobs


def main():
    parser = argparse.ArgumentParser(description="Scrape job listings from seek.com.au")
    parser.add_argument("--keywords", required=True, help='Job keywords, e.g. "python developer"')
    parser.add_argument("--location", required=True, help='Location, e.g. "melbourne"')
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to scrape (default: 1)")
    parser.add_argument("--output", help="Write results to this JSON file instead of stdout")
    args = parser.parse_args()

    jobs = asyncio.run(scrape(args.keywords, args.location, args.pages))

    result = json.dumps(jobs, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Wrote {len(jobs)} jobs to {args.output}", file=sys.stderr)
    else:
        print(result)

    print(f"\nTotal jobs scraped: {len(jobs)}", file=sys.stderr)


if __name__ == "__main__":
    main()
