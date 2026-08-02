"""
scrapers/base_scraper.py — Abstract Base Scraper
"""

import hashlib
from abc import ABC, abstractmethod
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.agents.state import JobData
from app.core.logging import get_logger

logger = get_logger(__name__)


class BaseScraper(ABC):
    portal_name: str = "base"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        await self._context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return self

    async def __aexit__(self, *args):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_page(self) -> Page:
        return await self._context.new_page()

    @abstractmethod
    async def search_jobs(self, query: str, location: str, max_results: int = 20) -> list[JobData]:
        pass

    def make_url_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def make_job_data(
        self,
        title: str,
        company: str,
        location: str,
        description: str,
        url: str,
        salary: Optional[str] = None,
        experience: Optional[str] = None,
    ) -> JobData:
        return JobData(
            title=title.strip(),
            company=company.strip(),
            location=location.strip(),
            description=description.strip(),
            portal=self.portal_name,
            url=url.strip(),
            url_hash=self.make_url_hash(url),
            salary=salary,
            experience_required=experience,
            status="new",
            required_skills=[],
        )

    async def safe_text(self, page: Page, selector: str, default: str = "") -> str:
        try:
            el = await page.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return default

    async def safe_attr(self, page: Page, selector: str, attr: str, default: str = "") -> str:
        try:
            el = await page.query_selector(selector)
            if el:
                val = await el.get_attribute(attr)
                return val.strip() if val else default
        except Exception:
            pass
        return default