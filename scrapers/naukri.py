"""
scrapers/naukri.py — Naukri Job Scraper
"""

import asyncio
from urllib.parse import quote_plus

from app.agents.state import JobData
from app.core.logging import get_logger
from scrapers.base_scraper import BaseScraper

logger = get_logger(__name__)


class NaukriScraper(BaseScraper):
    portal_name = "naukri"
    BASE_URL = "https://www.naukri.com"

    async def search_jobs(self, query: str, location: str, max_results: int = 20) -> list[JobData]:
        jobs: list[JobData] = []
        query_slug = query.lower().replace(" ", "-")
        location_slug = location.lower().replace(" ", "-")
        url = f"{self.BASE_URL}/{query_slug}-jobs-in-{location_slug}"

        page = await self.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            cards = await page.query_selector_all(".jobTuple, article.jobTupleHeader, .cust-job-tuple")
            logger.info("Naukri cards found", extra={"count": len(cards), "query": query})

            for card in cards[:max_results]:
                try:
                    title = await self._get_text(card, ".title, a.title, .jobTitle")
                    company = await self._get_text(card, ".companyInfo a, .comp-name")
                    loc = await self._get_text(card, ".location span, .locWdth")
                    salary = await self._get_text(card, ".salary, .sal")
                    exp = await self._get_text(card, ".experience, .exp")

                    link_el = await card.query_selector("a.title, a.jobTitle, .title a")
                    job_url = ""
                    if link_el:
                        job_url = await link_el.get_attribute("href") or ""

                    if not title or not job_url:
                        continue

                    description = await self._get_description(job_url)
                    job = self.make_job_data(
                        title=title,
                        company=company or "Unknown",
                        location=loc or location,
                        description=description or title,
                        url=job_url,
                        salary=salary or None,
                        experience=exp or None,
                    )
                    jobs.append(job)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning("Naukri card error", extra={"error": str(e)})
                    continue
        except Exception as e:
            logger.error("Naukri scrape failed", extra={"error": str(e), "url": url})
        finally:
            await page.close()

        logger.info("Naukri scrape done", extra={"query": query, "jobs": len(jobs)})
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
            desc = await self.safe_text(p, ".job-desc, .dang-inner-html, #job_description")
            await p.close()
            return desc[:5000]
        except Exception:
            return ""