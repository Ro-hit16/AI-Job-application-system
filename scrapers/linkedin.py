"""
scrapers/linkedin.py — LinkedIn Job Scraper
Uses public LinkedIn job search pages (no login required for listings).
"""

import asyncio
from urllib.parse import quote_plus

from app.agents.state import JobData
from app.core.logging import get_logger
from scrapers.base_scraper import BaseScraper

logger = get_logger(__name__)


class LinkedInScraper(BaseScraper):
    portal_name = "linkedin"
    BASE_URL = "https://www.linkedin.com/jobs/search"

    async def search_jobs(self, query: str, location: str, max_results: int = 20) -> list[JobData]:
        jobs: list[JobData] = []
        url = f"{self.BASE_URL}?keywords={quote_plus(query)}&location={quote_plus(location)}&f_TPR=r86400&sortBy=DD"

        page = await self.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            job_cards = await page.query_selector_all(".job-search-card")
            if not job_cards:
                job_cards = await page.query_selector_all("[data-entity-urn]")

            logger.info("LinkedIn cards found", extra={"count": len(job_cards), "query": query})

            for card in job_cards[:max_results]:
                try:
                    title = await self._get_card_text(card, ".base-search-card__title, h3")
                    company = await self._get_card_text(card, ".base-search-card__subtitle, h4")
                    loc = await self._get_card_text(card, ".job-search-card__location")
                    link_el = await card.query_selector("a")
                    job_url = await link_el.get_attribute("href") if link_el else ""

                    if not title or not job_url:
                        continue

                    description = await self._get_description(page, job_url)
                    job = self.make_job_data(
                        title=title,
                        company=company or "Unknown",
                        location=loc or location,
                        description=description or f"{title} at {company}",
                        url=job_url.split("?")[0],
                    )
                    jobs.append(job)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning("Card parse error", extra={"error": str(e)})
                    continue

        except Exception as e:
            logger.error("LinkedIn scrape failed", extra={"error": str(e), "url": url})
        finally:
            await page.close()

        logger.info("LinkedIn scrape done", extra={"query": query, "jobs": len(jobs)})
        return jobs

    async def _get_card_text(self, card, selector: str) -> str:
        try:
            for sel in selector.split(", "):
                el = await card.query_selector(sel.strip())
                if el:
                    return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def _get_description(self, page, job_url: str) -> str:
        try:
            detail_page = await self.new_page()
            await detail_page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)
            desc = await self.safe_text(detail_page, ".description__text, .show-more-less-html__markup")
            await detail_page.close()
            return desc[:5000] if desc else ""
        except Exception:
            return ""