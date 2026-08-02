from typing import TypedDict, Any, Optional


class JobData(TypedDict, total=False):
    id: str
    title: str
    company: str
    location: str
    description: str
    salary: str
    portal: str
    url: str
    url_hash: str
    required_skills: list[str]
    match_score: float
    embedding_id: str
    status: str


class ResumeData(TypedDict, total=False):
    resume_id: str
    filename: str
    file_path: str
    contact_info: dict[str, Any]
    skills: dict[str, Any]
    experience: list[dict[str, Any]]
    education: list[dict[str, Any]]
    summary: str
    raw_text: str
    years_of_experience: float
    embedding_id: str


class ApplicationData(TypedDict, total=False):
    application_id: str
    status: str
    job: dict[str, Any]
    resume: dict[str, Any]
    tailored_content: str
    cover_letter_content: str
    match_score: float
    tailored_resume_path: str
    cover_letter_path: str
    confirmation_number: str
    confirmation_screenshot_path: str
    error_message: str


class AgentState(TypedDict, total=False):
    # Run metadata
    run_id: str
    user_id: str
    resume_id: str
    triggered_by: str
    current_step: str

    # Config
    portals_to_search: list[str]
    job_categories: list[str]
    match_threshold: float

    # Job search results
    raw_jobs: list[JobData]
    jobs_found_count: int
    jobs_new_count: int

    # Resume analysis
    resume_data: ResumeData

    # Job matching
    scored_jobs: list[JobData]
    jobs_above_threshold: list[JobData]

    # Applications
    applications_to_process: list[ApplicationData]
    applications_submitted: int
    applications_rejected: int

    # Human approval
    awaiting_human_approval: bool
    human_decision: str
    human_edit_instructions: str
    skip_application: bool

    # Output
    summary: str
    errors: list
    last_error: str
    should_stop: bool


def create_initial_state(
    user_id: str,
    resume_id: str,
    run_id: str,
    triggered_by: str = "user",
    portals=None,
    categories=None,
    match_threshold=None,
) -> AgentState:
    return {
        "user_id": user_id,
        "resume_id": resume_id,
        "run_id": run_id,
        "triggered_by": triggered_by,
        "portals_to_search": portals or [],
        "job_categories": categories or [],
        "match_threshold": match_threshold or 65.0,
        "jobs_found_count": 0,
        "jobs_new_count": 0,
        "applications_submitted": 0,
        "applications_rejected": 0,
        "errors": [],
        "should_stop": False,
        "awaiting_human_approval": False,
    }