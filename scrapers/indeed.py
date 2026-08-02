"""
scrapers/indeed.py — Indeed Job Scraper
"""

import asyncio
from urllib.parse import quote_plus

from app.agents.state import JobData
from app.core.logging import get_logger
from scrapers.base_scraper import BaseScraper

logger = get_logger(__name__)


class IndeedScraper(BaseScraper):
    portal_name = "indeed"
    BASE_URL = "https://www.indeed.com/jobs"

    async def search_jobs(self, query: str, location: str, max_results: int = 20) -> list[JobData]:
        jobs: list[JobData] = []
        url = f"{self.BASE_URL}?q={quote_plus(query)}&l={quote_plus(location)}&fromage=1&sort=date"

        page = await self.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            cards = await page.query_selector_all("[data-jk], .job_seen_beacon")
            logger.info("Indeed cards found", extra={"count": len(cards), "query": query})

            for card in cards[:max_results]:
                try:
                    title = await self._get_text(card, "h2 a span, .jobTitle span")
                    company = await self._get_text(card, "[data-testid='company-name'], .companyName")
                    loc = await self._get_text(card, "[data-testid='text-location'], .companyLocation")

                    link_el = await card.query_selector("h2 a, .jobTitle a")
                    job_url = ""
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href:
                            job_url = f"https://www.indeed.com{href}" if href.startswith("/") else href

                    if not title or not job_url:
                        continue

                    description = await self._get_description(job_url)
                    job = self.make_job_data(
                        title=title,
                        company=company or "Unknown",
                        location=loc or location,
                        description=description or title,
                        url=job_url.split("?")[0],
                    )
                    jobs.append(job)
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.warning("Indeed card error", extra={"error": str(e)})
                    continue
        except Exception as e:
            logger.error("Indeed scrape failed", extra={"error": str(e)})
        finally:
            await page.close()

        return jobs

    async def _get_text(self, element, selector: str) -> str:
        try:
            for sel in selector.split(", "):
                el = await element.query_selector(sel.strip())
                if el:
                    return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def _get_description(self, url: str) -> str:
        try:
            p = await self.new_page()
            await p.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)
            desc = await self.safe_text(p, "#jobDescriptionText, .jobsearch-jobDescriptionText")
            await p.close()
            return desc[:5000]
        except Exception:
            return ""