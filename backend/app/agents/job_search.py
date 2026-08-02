"""
agents/job_search.py — Job Search with 48hr filter + Apify free tier
=====================================================================
Sources:
  FREE APIs (no auth):
    1. Remotive       - Remote tech jobs (48hr filter)
    2. Arbeitnow      - Worldwide tech jobs (48hr filter)
    3. Himalayas      - Remote tech jobs (48hr filter)
    4. Adzuna India   - Indian jobs (free 500/day)

  APIFY FREE TIER ($5 credit/month = ~1000 runs free):
    5. LinkedIn Jobs  - via Apify actor
    6. Indeed Jobs    - via Apify actor
    7. Naukri Jobs    - via Apify actor

  Setup Apify (completely free to start):
    1. Go to https://apify.com → Sign up free
    2. Get API token from https://console.apify.com/account/integrations
    3. Add to .env: APIFY_TOKEN=your_token_here
    4. Free tier gives $5/month credit (enough for hundreds of scrapes)
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from sqlalchemy import select

from app.agents.state import AgentState, JobData
from app.config import get_settings
from app.core.logging import get_logger
from app.database import get_db_context
from app.models.job import Job

logger = get_logger(__name__)
settings = get_settings()

# Jobs older than this are ignored
MAX_AGE_HOURS = 48

SEARCH_KEYWORDS = [
    "mern", "full stack", "fullstack", "react", "node", "nodejs",
    "devops", "cloud", "python", "javascript", "typescript", "aws",
    "developer", "engineer", "software", "backend", "frontend",
    "mongodb", "express", "docker", "kubernetes", "ai", "ml",
    "machine learning", "java", "golang", "next.js", "vue",
]


async def job_search_node(state: AgentState) -> dict:
    run_id = state.get("run_id", str(uuid.uuid4()))
    logger.info("Job search node started", extra={"run_id": run_id})

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    all_scraped: list[JobData] = []

    try:
        # ── Free APIs (always run) ────────────────────────────────────────────
        sources = [
            ("Remotive",   _fetch_remotive()),
            ("Arbeitnow",  _fetch_arbeitnow()),
            ("Himalayas",  _fetch_himalayas()),
            ("Adzuna",     _fetch_adzuna()),
        ]

        import asyncio
        results = await asyncio.gather(*[s[1] for s in sources], return_exceptions=True)
        for (name, _), result in zip(sources, results):
            if isinstance(result, Exception):
                logger.warning(f"{name} failed", extra={"error": str(result)})
            else:
                all_scraped.extend(result)
                logger.info(f"{name} fetched", extra={"count": len(result)})

        # ── Apify (LinkedIn + Indeed + Naukri) ───────────────────────────────
        apify_token = getattr(settings, "APIFY_TOKEN", None)
        if apify_token:
            apify_results = await asyncio.gather(
                _fetch_apify_linkedin(apify_token),
                _fetch_apify_indeed(apify_token),
                _fetch_apify_naukri(apify_token),
                return_exceptions=True,
            )
            for name, result in zip(["LinkedIn", "Indeed", "Naukri"], apify_results):
                if isinstance(result, Exception):
                    logger.warning(f"Apify {name} failed", extra={"error": str(result)})
                else:
                    all_scraped.extend(result)
                    logger.info(f"Apify {name}", extra={"count": len(result)})
        else:
            logger.info("Apify skipped - add APIFY_TOKEN to .env for LinkedIn/Indeed/Naukri")

        # ── Store new jobs ────────────────────────────────────────────────────
        new_jobs = await _store_new_jobs(all_scraped)

        # If all jobs were duplicates, still pass existing DB jobs to job_match
        if not new_jobs and all_scraped:
            logger.info("All jobs already in DB, loading existing for matching")
            async with get_db_context() as db:
                result = await db.execute(select(Job).limit(20))
                db_jobs = result.scalars().all()
                new_jobs = [{
                    "id": str(j.id),
                    "title": j.title,
                    "company": j.company,
                    "location": j.location or "",
                    "description": j.description or "",
                    "portal": j.portal,
                    "url": j.url,
                    "url_hash": j.url_hash,
                } for j in db_jobs]

        logger.info(
            "Job search complete",
            extra={"run_id": run_id, "scraped": len(all_scraped), "new": len(new_jobs)},
        )
        return {
            "raw_jobs": new_jobs,
            "jobs_found_count": len(all_scraped),
            "jobs_new_count": len(new_jobs),
            "current_step": "job_search_complete",
        }

    except Exception as e:
        logger.error("Job search failed", extra={"run_id": run_id, "error": str(e)})
        return {
            "errors": [{"step": "job_search", "message": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}],
            "last_error": str(e),
            "current_step": "job_search_failed",
            "raw_jobs": [],
            "jobs_found_count": 0,
            "jobs_new_count": 0,
        }


# ─── Free API Fetchers ────────────────────────────────────────────────────────

async def _fetch_remotive() -> list[JobData]:
    jobs: list[JobData] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    categories = ["software-dev", "devops-sysadmin", "data", "backend"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for cat in categories:
            try:
                resp = await client.get(
                    "https://remotive.com/api/remote-jobs",
                    params={"category": cat, "limit": 20},
                )
                resp.raise_for_status()
                for job in resp.json().get("jobs", []):
                    # 48hr filter
                    pub = job.get("publication_date", "")
                    if pub:
                        try:
                            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                            if pub_dt < cutoff:
                                continue
                        except Exception:
                            pass

                    title = job.get("title", "")
                    desc = _clean_html(job.get("description", ""))
                    if not _is_relevant(title + " " + desc):
                        continue
                    url = job.get("url", "")
                    jobs.append(JobData(
                        title=title,
                        company=job.get("company_name", "Unknown"),
                        location=job.get("candidate_required_location", "Remote"),
                        description=desc[:3000],
                        portal="remotive",
                        url=url,
                        url_hash=_hash(url),
                        salary=str(job.get("salary", "")),
                        status="new",
                        required_skills=job.get("tags", [])[:10],
                    ))
            except Exception as e:
                logger.warning("Remotive cat error", extra={"cat": cat, "error": str(e)})
    return jobs[:25]


async def _fetch_arbeitnow() -> list[JobData]:
    jobs: list[JobData] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in [1, 2]:
            try:
                resp = await client.get(
                    "https://www.arbeitnow.com/api/job-board-api",
                    params={"page": page},
                )
                resp.raise_for_status()
                for job in resp.json().get("data", []):
                    # 48hr filter using created_at
                    created = job.get("created_at", 0)
                    if created:
                        try:
                            pub_dt = datetime.fromtimestamp(created, tz=timezone.utc)
                            if pub_dt < cutoff:
                                continue
                        except Exception:
                            pass

                    title = job.get("title", "")
                    desc = _clean_html(job.get("description", ""))
                    if not _is_relevant(title + " " + desc):
                        continue
                    url = job.get("url", "")
                    location = "Remote" if job.get("remote") else job.get("location", "Remote")
                    jobs.append(JobData(
                        title=title,
                        company=job.get("company_name", "Unknown"),
                        location=location,
                        description=desc[:3000],
                        portal="arbeitnow",
                        url=url,
                        url_hash=_hash(url),
                        status="new",
                        required_skills=job.get("tags", [])[:10],
                    ))
            except Exception as e:
                logger.warning("Arbeitnow error", extra={"page": page, "error": str(e)})
    return jobs[:25]


async def _fetch_himalayas() -> list[JobData]:
    jobs: list[JobData] = []
    queries = ["react developer", "nodejs", "devops", "python developer", "fullstack", "mern"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for query in queries:
            try:
                resp = await client.get(
                    "https://himalayas.app/jobs/api",
                    params={"q": query, "limit": 10},
                )
                if resp.status_code != 200:
                    continue
                for job in resp.json().get("jobs", []):
                    title = job.get("title", "")
                    desc = _clean_html(job.get("description", ""))
                    url = job.get("applicationLink", job.get("url", ""))
                    if not url:
                        continue

                    # 48hr filter
                    pub = job.get("publishedAt", job.get("createdAt", ""))
                    if pub:
                        try:
                            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                            cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
                            if pub_dt < cutoff:
                                continue
                        except Exception:
                            pass

                    jobs.append(JobData(
                        title=title,
                        company=job.get("companyName", "Unknown"),
                        location=job.get("location", "Remote"),
                        description=desc[:3000] or title,
                        portal="himalayas",
                        url=url,
                        url_hash=_hash(url),
                        salary=str(job.get("salary", "")),
                        status="new",
                        required_skills=job.get("skills", [])[:10],
                    ))
            except Exception as e:
                logger.warning("Himalayas error", extra={"query": query, "error": str(e)})
    return jobs[:20]


async def _fetch_adzuna() -> list[JobData]:
    """Adzuna India — best Indian job API, free 500 calls/day."""
    jobs: list[JobData] = []
    app_id = getattr(settings, "ADZUNA_APP_ID", None)
    app_key = getattr(settings, "ADZUNA_APP_KEY", None)
    if not app_id or not app_key:
        logger.info("Adzuna skipped - no API key")
        return []

    queries = [
        "MERN developer", "full stack developer", "React developer",
        "Node.js developer", "DevOps engineer", "Python developer",
        "cloud engineer", "AWS engineer", "software engineer",
    ]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for query in queries:
            try:
                resp = await client.get(
                    "https://api.adzuna.com/v1/api/jobs/in/search/1",
                    params={
                        "app_id": app_id,
                        "app_key": app_key,
                        "what": query,
                        "results_per_page": 10,
                        "max_days_old": 2,  # ← 48hr filter built-in
                        "sort_by": "date",
                        "content-type": "application/json",
                    },
                )
                resp.raise_for_status()
                for job in resp.json().get("results", []):
                    title = job.get("title", "")
                    desc = _clean_html(job.get("description", ""))
                    url = job.get("redirect_url", "")
                    company = job.get("company", {}).get("display_name", "Unknown")
                    location = job.get("location", {}).get("display_name", "India")
                    salary_min = job.get("salary_min", "")
                    salary_max = job.get("salary_max", "")
                    salary = f"₹{salary_min}-{salary_max}" if salary_min else ""

                    jobs.append(JobData(
                        title=title,
                        company=company,
                        location=location,
                        description=desc[:3000] or title,
                        portal="adzuna",
                        url=url,
                        url_hash=_hash(url),
                        salary=salary,
                        status="new",
                        required_skills=[],
                    ))
            except Exception as e:
                logger.warning("Adzuna error", extra={"query": query, "error": str(e)})
    return jobs[:40]


# ─── Apify Fetchers (LinkedIn + Indeed + Naukri) ──────────────────────────────

async def _run_apify_actor(token: str, actor_id: str, input_data: dict) -> list[dict]:
    """
    Run an Apify actor and return results.
    Free tier: $5/month credit. Each run costs ~$0.001-0.01.
    That's 500-5000 free runs/month.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Start the actor run
        run_resp = await client.post(
            f"https://api.apify.com/v2/acts/{actor_id}/runs",
            params={"token": token, "waitForFinish": 60},
            json=input_data,
        )
        run_resp.raise_for_status()
        run_data = run_resp.json()
        run_id = run_data.get("data", {}).get("id")
        if not run_id:
            return []

        # Wait for completion (max 90 seconds)
        for _ in range(9):
            import asyncio
            await asyncio.sleep(10)
            status_resp = await client.get(
                f"https://api.apify.com/v2/acts/{actor_id}/runs/{run_id}",
                params={"token": token},
            )
            status = status_resp.json().get("data", {}).get("status", "")
            if status in ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"):
                break

        # Get results
        dataset_id = run_data.get("data", {}).get("defaultDatasetId", "")
        if not dataset_id:
            return []

        items_resp = await client.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            params={"token": token, "format": "json", "limit": 50},
        )
        items_resp.raise_for_status()
        return items_resp.json()


async def _fetch_apify_linkedin(token: str) -> list[JobData]:
    """
    LinkedIn Jobs via Apify free actor.
    Actor: apify/linkedin-jobs-scraper
    Cost: ~$0.005 per run (very cheap)
    """
    jobs: list[JobData] = []
    try:
        items = await _run_apify_actor(
            token=token,
            actor_id="hKByXkMQaC5Qt9UMN",  # LinkedIn Jobs Scraper (free actor)
            input_data={
                "queries": [
                    "MERN Stack Developer India",
                    "Full Stack Developer React Node India",
                    "DevOps Engineer India",
                    "Python Developer India",
                ],
                "datePosted": "past-24h",  # 48hr filter
                "maxResults": 20,
            },
        )
        for item in items:
            url = item.get("jobUrl", item.get("url", ""))
            title = item.get("title", item.get("jobTitle", ""))
            if not url or not title:
                continue
            jobs.append(JobData(
                title=title,
                company=item.get("companyName", item.get("company", "Unknown")),
                location=item.get("location", "India"),
                description=_clean_html(item.get("description", title))[:3000],
                portal="linkedin",
                url=url,
                url_hash=_hash(url),
                salary=item.get("salary", ""),
                status="new",
                required_skills=[],
            ))
    except Exception as e:
        logger.warning("Apify LinkedIn failed", extra={"error": str(e)})
    return jobs


async def _fetch_apify_indeed(token: str) -> list[JobData]:
    """
    Indeed Jobs via Apify free actor.
    Actor: misceres/indeed-scraper
    Cost: ~$0.005 per run
    """
    jobs: list[JobData] = []
    try:
        items = await _run_apify_actor(
            token=token,
            actor_id="misceres~indeed-scraper",
            input_data={
                "queries": [
                    {"query": "MERN Stack Developer", "location": "India"},
                    {"query": "Full Stack Developer", "location": "Bangalore"},
                    {"query": "DevOps Engineer", "location": "India"},
                    {"query": "React Node Developer", "location": "India"},
                ],
                "maxItems": 20,
                "fromDays": 2,  # last 48 hours
            },
        )
        for item in items:
            url = item.get("externalApplyLink", item.get("url", item.get("link", "")))
            title = item.get("positionName", item.get("title", ""))
            if not url or not title:
                continue
            jobs.append(JobData(
                title=title,
                company=item.get("company", "Unknown"),
                location=item.get("location", "India"),
                description=_clean_html(item.get("description", title))[:3000],
                portal="indeed",
                url=url,
                url_hash=_hash(url),
                salary=item.get("salary", ""),
                status="new",
                required_skills=[],
            ))
    except Exception as e:
        logger.warning("Apify Indeed failed", extra={"error": str(e)})
    return jobs


async def _fetch_apify_naukri(token: str) -> list[JobData]:
    """
    Naukri.com Jobs via Apify free actor.
    Actor: curious_coder/naukri-scraper
    Cost: ~$0.005 per run
    """
    jobs: list[JobData] = []
    try:
        items = await _run_apify_actor(
            token=token,
            actor_id="curious_coder~naukri-scraper",
            input_data={
                "keyword": "MERN Stack Full Stack DevOps React Node Python",
                "location": "India",
                "freshnessInDays": 2,  # last 48 hours
                "maxPages": 2,
            },
        )
        for item in items:
            url = item.get("jobUrl", item.get("url", ""))
            title = item.get("title", item.get("jobTitle", ""))
            if not url or not title:
                continue
            jobs.append(JobData(
                title=title,
                company=item.get("company", item.get("companyName", "Unknown")),
                location=item.get("location", "India"),
                description=_clean_html(item.get("description", title))[:3000],
                portal="naukri",
                url=url,
                url_hash=_hash(url),
                salary=item.get("salary", item.get("salaryRange", "")),
                experience_required=item.get("experience", ""),
                status="new",
                required_skills=item.get("keySkills", [])[:10],
            ))
    except Exception as e:
        logger.warning("Apify Naukri failed", extra={"error": str(e)})
    return jobs


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_relevant(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in SEARCH_KEYWORDS)


def _clean_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


async def _store_new_jobs(scraped_jobs: list[JobData]) -> list[JobData]:
    new_jobs: list[JobData] = []

    try:
        from app.services.llm_service import get_llm_service
        from app.services.vector_service import get_vector_service
        llm = get_llm_service()
        vector_service = get_vector_service()
        use_vectors = True
    except Exception:
        use_vectors = False
        logger.warning("Vector service unavailable")

    async with get_db_context() as db:
        for job_data in scraped_jobs:
            try:
                url_hash = job_data.get("url_hash", "")
                if not url_hash:
                    continue

                existing = await db.execute(select(Job).where(Job.url_hash == url_hash))
                if existing.scalar_one_or_none():
                    continue

                embedding_id = None
                if use_vectors:
                    try:
                        embed_text = f"{job_data['title']} {job_data['company']} {job_data['description']}"
                        vector = await llm.embed(embed_text)
                        embedding_id = await vector_service.add_job_embedding(
                            job_id="pending",
                            vector=vector,
                            metadata={
                                "title": job_data["title"],
                                "company": job_data["company"],
                                "portal": job_data["portal"],
                            },
                        )
                    except Exception as e:
                        logger.warning("Embedding failed", extra={"error": str(e)})

                db_job = Job(
                    id=uuid.uuid4(),
                    title=job_data["title"],
                    company=job_data["company"],
                    location=job_data.get("location", ""),
                    description=job_data["description"],
                    portal=job_data["portal"],
                    url=job_data["url"],
                    url_hash=url_hash,
                    salary=job_data.get("salary", ""),
                    experience_required=job_data.get("experience_required", ""),
                    embedding_id=embedding_id,
                    status="new",
                    required_skills=job_data.get("required_skills", []),
                )
                db.add(db_job)
                await db.flush()

                job_data["id"] = str(db_job.id)
                job_data["embedding_id"] = embedding_id or ""
                new_jobs.append(job_data)

            except Exception as e:
                logger.warning("Job store error", extra={"error": str(e)})
                continue

    logger.info("Jobs stored", extra={"new": len(new_jobs)})
    return new_jobs

