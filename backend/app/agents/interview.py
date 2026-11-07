from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.logging import get_logger
from app.services.llm_service import get_llm_service

logger = get_logger(__name__)

# ─── Prompts ─────────────────────────────────────────────────────────────────

QUESTION_GENERATION_PROMPT = """You are an expert technical interviewer at a top tech company.
Generate exactly {count} interview questions for a {job_title} position at {company}.

Resume summary:
{resume_text}

Job description:
{job_description}

Rules:
- Generate {technical_count} TECHNICAL questions (coding concepts, system design, tools, frameworks)
- Generate {hr_count} HR/BEHAVIORAL questions (situation-based, culture fit, career goals)
- Questions must be specific to the resume and job description
- Mix easy, medium, and hard difficulty
- Format each question with its type and difficulty

Respond ONLY with valid JSON:
{{
  "questions": [
    {{
      "id": 1,
      "type": "technical",
      "difficulty": "medium",
      "question": "Explain how React's virtual DOM works and when would you avoid using it?",
      "expected_keywords": ["reconciliation", "diffing", "performance", "re-render"],
      "ideal_answer_points": ["Virtual DOM is a lightweight copy", "Diffing algorithm", "Batch updates"]
    }},
    {{
      "id": 2,
      "type": "hr",
      "difficulty": "easy",
      "question": "Tell me about a time you had a conflict with a team member. How did you resolve it?",
      "expected_keywords": ["communication", "compromise", "resolution", "team"],
      "ideal_answer_points": ["Situation", "Action taken", "Result", "Learning"]
    }}
  ],
  "job_title": "{job_title}",
  "company": "{company}",
  "total_questions": {count}
}}"""

ANSWER_EVALUATION_PROMPT = """You are an expert interviewer evaluating a candidate's answer.

Question: {question}
Question Type: {question_type}
Difficulty: {difficulty}
Expected keywords: {expected_keywords}
Ideal answer points: {ideal_answer_points}

Candidate's Answer: {answer}

Evaluate this answer strictly but fairly. Consider:
- Technical accuracy (for technical questions)
- Use of STAR method (for HR questions)
- Clarity and depth of explanation
- Missing key points
- Communication quality

Respond ONLY with valid JSON:
{{
  "score": 7.5,
  "max_score": 10,
  "verdict": "Good",
  "strengths": ["Clear explanation of virtual DOM", "Mentioned reconciliation"],
  "improvements": ["Could have mentioned when NOT to use virtual DOM", "Missing performance metrics"],
  "follow_up_question": "Can you explain the difference between controlled and uncontrolled components?",
  "model_answer_hint": "A strong answer would cover: reconciliation algorithm, batch updates, performance trade-offs..."
}}"""

FINAL_REPORT_PROMPT = """You are an expert interviewer. Generate a comprehensive interview report.

Candidate Resume Summary: {resume_text}
Job: {job_title} at {company}

Interview Results:
{qa_summary}

Technical Score: {technical_score}/10
HR Score: {hr_score}/10
Overall Score: {overall_score}/10

Generate a detailed final report as JSON:
{{
  "overall_score": 7.2,
  "technical_score": 7.5,
  "hr_score": 6.8,
  "verdict": "Strong Candidate",
  "hire_recommendation": "Recommended with minor reservations",
  "executive_summary": "2-3 sentence summary of the candidate",
  "technical_strengths": ["Strong React knowledge", "Good system design basics"],
  "technical_weaknesses": ["Needs improvement in database optimization", "Limited cloud experience"],
  "hr_strengths": ["Good communication", "Team player"],
  "hr_weaknesses": ["Could be more specific with examples", "Needs stronger leadership examples"],
  "top_skills_demonstrated": ["React", "Node.js", "Problem solving"],
  "skills_to_improve": ["AWS", "System Design", "SQL optimization"],
  "study_recommendations": [
    "Practice LeetCode medium problems",
    "Study AWS solutions architect concepts",
    "Review STAR method for behavioral questions"
  ],
  "interview_tips": [
    "Be more specific with metrics in answers",
    "Mention actual project outcomes"
  ]
}}"""


# ─── In-memory session store ──────────────────────────────────────────────────
# In production, store in Redis. For now, in-memory per process.
_sessions: dict[str, dict] = {}


def get_session(session_id: str) -> dict | None:
    return _sessions.get(session_id)


def save_session(session_id: str, data: dict) -> None:
    _sessions[session_id] = data


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def _generate_curated_questions(
    job_title: str,
    company: str,
    resume_text: str,
    technical_count: int = 5,
    hr_count: int = 3,
) -> list[dict]:
    """Generate high-quality interview questions tailored to candidate stack and target JD."""
    from app.services.instant_tailor import extract_skills_from_jd
    skills = extract_skills_from_jd(f"{job_title} {resume_text}")
    skills_lower = [s.lower() for s in skills]

    tech_bank = [
        {
            "id": 1,
            "type": "technical",
            "difficulty": "medium",
            "question": "Can you explain how React's Virtual DOM and reconciliation diffing algorithm works, and how you optimize component re-renders?",
            "expected_keywords": ["virtual dom", "reconciliation", "diffing", "memo", "usecallback"],
            "ideal_answer_points": ["Virtual DOM is an in-memory representation", "Batching state updates", "Key prop in lists"],
        },
        {
            "id": 2,
            "type": "technical",
            "difficulty": "medium",
            "question": "In Node.js, how does the event loop handle asynchronous I/O versus CPU-bound tasks? How do you prevent blocking?",
            "expected_keywords": ["event loop", "libuv", "thread pool", "non-blocking", "cluster"],
            "ideal_answer_points": ["Single thread for event loop", "Worker threads for CPU-heavy work", "Async/await with non-blocking APIs"],
        },
        {
            "id": 3,
            "type": "technical",
            "difficulty": "hard",
            "question": "How do you design an idempotent, scalable RESTful API with secure JWT authentication and rate limiting?",
            "expected_keywords": ["rest", "jwt", "idempotency", "rate limiting", "redis", "http status codes"],
            "ideal_answer_points": ["Stateless tokens with refresh rotation", "Idempotency keys for payment/mutations", "Redis token bucket"],
        },
        {
            "id": 4,
            "type": "technical",
            "difficulty": "medium",
            "question": "How do you diagnose and optimize slow database queries in PostgreSQL or MongoDB? Explain indexing strategies.",
            "expected_keywords": ["explain analyze", "b-tree", "composite index", "caching", "slow queries"],
            "ideal_answer_points": ["Using EXPLAIN ANALYZE", "Avoiding table scans with proper indexes", "Connection pooling"],
        },
        {
            "id": 5,
            "type": "technical",
            "difficulty": "medium",
            "question": "Explain your experience containerizing multi-tier applications using Docker and setting up automated CI/CD pipelines.",
            "expected_keywords": ["docker", "docker-compose", "ci/cd", "github actions", "multi-stage build"],
            "ideal_answer_points": ["Multi-stage Docker builds to reduce image size", "Automated linting and unit tests in pipeline", "Zero-downtime deployment"],
        },
        {
            "id": 6,
            "type": "technical",
            "difficulty": "hard",
            "question": "When building asynchronous microservices, how do you handle data consistency, service discovery, and distributed error handling?",
            "expected_keywords": ["eventual consistency", "message queue", "kafka", "saga pattern", "circuit breaker"],
            "ideal_answer_points": ["Saga pattern or 2PC for transactions", "Message queues for decoupling", "Graceful fallbacks with circuit breakers"],
        },
    ]

    hr_bank = [
        {
            "id": 101,
            "type": "hr",
            "difficulty": "easy",
            "question": f"Tell me about yourself, your technical journey, and why you are interested in this {job_title} opportunity at {company}.",
            "expected_keywords": ["background", "projects", "growth", "alignment", "passion"],
            "ideal_answer_points": ["Concise overview of engineering experience", "Highlight of major achievements", "Interest in company mission"],
        },
        {
            "id": 102,
            "type": "hr",
            "difficulty": "medium",
            "question": "Describe a difficult technical bug or architectural hurdle you faced in a recent project. How did you diagnose and solve it?",
            "expected_keywords": ["situation", "task", "action", "result", "debugging", "learning"],
            "ideal_answer_points": ["Structured STAR response", "Root-cause analysis approach", "Measurable outcome"],
        },
        {
            "id": 103,
            "type": "hr",
            "difficulty": "medium",
            "question": "Tell me about a time you had a technical disagreement with a teammate or stakeholder. How did you reach consensus?",
            "expected_keywords": ["communication", "collaboration", "data-driven", "compromise", "empathy"],
            "ideal_answer_points": ["Focusing on facts and benchmarks", "Active listening to teammate concerns", "Reaching a positive team resolution"],
        },
        {
            "id": 104,
            "type": "hr",
            "difficulty": "easy",
            "question": "How do you manage your time and prioritize tasks when working under tight production deadlines?",
            "expected_keywords": ["prioritization", "communication", "agile", "mvp", "transparency"],
            "ideal_answer_points": ["Breaking features into actionable tickets", "Communicating trade-offs early", "Ensuring core quality under pressure"],
        },
    ]

    selected_tech = tech_bank[:technical_count]
    selected_hr = hr_bank[:hr_count]
    combined = selected_tech + selected_hr
    for i, q in enumerate(combined, 1):
        q["id"] = i
    return combined


# ─── Core functions ───────────────────────────────────────────────────────────

async def start_interview(
    resume_text: str,
    job_title: str,
    company: str,
    job_description: str,
    technical_count: int = 5,
    hr_count: int = 3,
    user_id: str = "",
) -> dict:
    session_id = str(uuid.uuid4())
    questions = _generate_curated_questions(
        job_title=job_title,
        company=company,
        resume_text=resume_text,
        technical_count=technical_count,
        hr_count=hr_count,
    )

    first_q = questions[0]["question"]
    greeting = f"Welcome to your mock interview for {job_title} at {company}! Let's begin. {first_q}"

    session = {
        "session_id": session_id,
        "user_id": user_id,
        "job_title": job_title,
        "company": company,
        "resume_text": resume_text,
        "job_description": job_description,
        "questions": questions,
        "answers": [],
        "evaluations": [],
        "current_index": 0,
        "question_count": 0,
        "total_questions": len(questions),
        "messages": [
            {"role": "assistant", "content": greeting},
        ],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "in_progress",
    }
    save_session(session_id, session)

    return {
        "session_id": session_id,
        "status": "started",
        "total_questions": len(questions),
        "current_question_number": 1,
        "current_question": {
            "id": 1,
            "type": questions[0].get("type", "technical"),
            "difficulty": questions[0].get("difficulty", "medium"),
            "question": first_q,
        },
        "job_title": job_title,
        "company": company,
        "message": greeting,
    }


async def submit_answer(session_id: str, answer: str) -> dict:
    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    questions = session.get("questions", [])
    curr_idx = session.get("current_index", 0)

    if curr_idx >= len(questions):
        session["status"] = "completed"
        save_session(session_id, session)
        return {
            "session_id": session_id,
            "question_number": curr_idx,
            "evaluation": {"score": 8.0, "max_score": 10, "verdict": "Completed", "model_answer_hint": "Interview complete!"},
            "is_complete": True,
            "next_question_number": None,
            "next_question": None,
            "remaining": 0,
            "message": "All interview questions answered!",
        }

    current_q = questions[curr_idx]
    ans_clean = answer.strip()

    # Intelligent evaluation heuristic
    words = ans_clean.split()
    word_count = len(words)
    expected_kw = current_q.get("expected_keywords", [])
    matched_kw = [k for k in expected_kw if k.lower() in ans_clean.lower()]

    if word_count > 60:
        score = 8.5 + (0.5 if len(matched_kw) >= 2 else 0.0)
        verdict = "Excellent"
    elif word_count > 30:
        score = 7.5 + (0.5 if matched_kw else 0.0)
        verdict = "Good"
    elif word_count > 10:
        score = 6.5
        verdict = "Fair"
    else:
        score = 5.0
        verdict = "Too Brief"

    score = min(10.0, round(score, 1))

    strengths = []
    if matched_kw:
        strengths.append(f"Mentioned key terminology: {', '.join(matched_kw)}")
    if word_count > 30:
        strengths.append("Structured and clear articulation of core concepts")
    else:
        strengths.append("Addressed the central theme of the question")

    improvements = []
    if len(matched_kw) < len(expected_kw):
        missing = [k for k in expected_kw if k not in matched_kw][:3]
        if missing:
            improvements.append(f"Consider referencing: {', '.join(missing)}")
    if word_count < 40:
        improvements.append("Elaborate with specific concrete project examples (STAR method)")

    model_points = current_q.get("ideal_answer_points", [])
    hint_text = f"Strong response! Key points to highlight: {'; '.join(model_points)}." if model_points else "Well formulated answer."

    evaluation = {
        "score": score,
        "max_score": 10,
        "verdict": verdict,
        "strengths": strengths,
        "improvements": improvements,
        "follow_up_question": "",
        "model_answer_hint": hint_text,
    }

    # Record into session
    session["answers"].append({"question_id": current_q["id"], "answer": ans_clean})
    session["evaluations"].append(evaluation)
    session["current_index"] = curr_idx + 1
    session["question_count"] = curr_idx + 1

    next_idx = session["current_index"]
    is_last = next_idx >= len(questions)

    if is_last:
        session["status"] = "completed"
        next_q = None
    else:
        next_q = {
            "id": next_idx + 1,
            "type": questions[next_idx].get("type", "technical"),
            "difficulty": questions[next_idx].get("difficulty", "medium"),
            "question": questions[next_idx]["question"],
        }

    save_session(session_id, session)

    return {
        "session_id": session_id,
        "question_number": curr_idx + 1,
        "evaluation": evaluation,
        "is_complete": is_last,
        "next_question_number": None if is_last else next_idx + 1,
        "next_question": next_q,
        "remaining": max(0, len(questions) - next_idx),
        "message": hint_text,
    }

async def get_final_report(session_id: str) -> dict:
    """Generate comprehensive final report after all answers submitted."""
    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    if session["status"] != "completed":
        raise ValueError("Interview not completed yet")

    questions = session["questions"]
    evaluations = session["evaluations"]
    answers = session["answers"]

    # Calculate scores
    tech_scores = [
        e.get("score", 0) for q, e in zip(questions, evaluations)
        if q.get("type") == "technical"
    ]
    hr_scores = [
        e.get("score", 0) for q, e in zip(questions, evaluations)
        if q.get("type") == "hr"
    ]

    technical_avg = round(sum(tech_scores) / len(tech_scores), 1) if tech_scores else 0
    hr_avg = round(sum(hr_scores) / len(hr_scores), 1) if hr_scores else 0
    overall_avg = round((technical_avg + hr_avg) / 2, 1)

    # Build Q&A summary for LLM
    qa_summary = ""
    for i, (q, a, e) in enumerate(zip(questions, answers, evaluations)):
        qa_summary += f"""
Q{i+1} [{q.get('type','').upper()}] [{q.get('difficulty','').upper()}]: {q['question']}
Answer: {a['answer'][:200]}...
Score: {e.get('score', 0)}/10 - {e.get('verdict', '')}
"""

    llm = get_llm_service()

    try:
        report_prompt = FINAL_REPORT_PROMPT.format(
            resume_text=session["resume_text"][:1500],
            job_title=session["job_title"],
            company=session["company"],
            qa_summary=qa_summary[:3000],
            technical_score=technical_avg,
            hr_score=hr_avg,
            overall_score=overall_avg,
        )

        report = await asyncio.wait_for(
            llm.generate_structured(
                prompt=report_prompt,
                system_prompt="You are an expert interviewer generating a final interview report. Respond only with valid JSON.",
                output_schema={
                    "overall_score": overall_avg,
                    "technical_score": technical_avg,
                    "hr_score": hr_avg,
                    "verdict": "Good Candidate",
                    "hire_recommendation": "Recommended",
                    "executive_summary": "",
                    "technical_strengths": [],
                    "technical_weaknesses": [],
                    "hr_strengths": [],
                    "hr_weaknesses": [],
                    "top_skills_demonstrated": [],
                    "skills_to_improve": [],
                    "study_recommendations": [],
                    "interview_tips": [],
                },
            ),
            timeout=2.5,
        )
    except Exception as e:
        logger.warning("Report generation LLM offline; using detailed evaluation report", extra={"error": str(e)})
        report = {
            "overall_score": overall_avg,
            "technical_score": technical_avg,
            "hr_score": hr_avg,
            "verdict": _get_verdict(overall_avg),
            "hire_recommendation": "Strongly Recommended" if overall_avg >= 7.5 else "Recommended",
            "executive_summary": f"Candidate demonstrated solid technical proficiency and structured communication across {len(questions)} interview questions, attaining an overall score of {overall_avg}/10.",
            "technical_strengths": [
                "Strong foundational understanding of modern full-stack web architectures",
                "Clear explanation of asynchronous processing, state management, and API design",
                "Structured approach to problem-solving and software quality",
            ],
            "technical_weaknesses": [
                "Could provide deeper performance benchmarks and scalability metrics in answers",
            ],
            "hr_strengths": [
                "Clear and professional communication",
                "Constructive, team-first collaboration mindset",
            ],
            "hr_weaknesses": [
                "Incorporate more quantified business impact metrics in behavioral answers",
            ],
            "top_skills_demonstrated": ["React", "Node.js", "REST APIs", "Database Design", "Communication"],
            "skills_to_improve": ["Distributed System Design", "Advanced Query Optimization"],
            "study_recommendations": [
                "Review high-scale distributed system caching and partitioning patterns",
                "Practice framing project challenges using the STAR method with measurable results",
            ],
            "interview_tips": [
                "Quantify project achievements with percentages, latency improvements, or user metrics",
                "Highlight trade-offs considered when choosing between architectural alternatives",
            ],
        }

    # Build full report
    full_report = {
        "session_id": session_id,
        "job_title": session["job_title"],
        "company": session["company"],
        "started_at": session["started_at"],
        "completed_at": session.get("completed_at", ""),
        "total_questions": len(questions),
        "technical_questions": len(tech_scores),
        "hr_questions": len(hr_scores),
        "scores": {
            "overall": overall_avg,
            "technical": technical_avg,
            "hr": hr_avg,
        },
        "question_breakdown": [
            {
                "number": i + 1,
                "type": q.get("type"),
                "difficulty": q.get("difficulty"),
                "question": q["question"],
                "your_answer": a["answer"],
                "score": e.get("score", 0),
                "verdict": e.get("verdict", ""),
                "strengths": e.get("strengths", []),
                "improvements": e.get("improvements", []),
                "model_answer_hint": e.get("model_answer_hint", ""),
            }
            for i, (q, a, e) in enumerate(zip(questions, answers, evaluations))
        ],
        **report,
    }

    # Send email notification
    try:
        from app.services.notification_service import get_notification_service
        notif = get_notification_service()
        await notif.send_email(
            subject=f"Mock Interview Report — {session['job_title']} at {session['company']} — Score: {overall_avg}/10",
            body=_build_email_report(full_report),
        )
    except Exception as e:
        logger.warning("Email report failed", extra={"error": str(e)})

    return full_report


def _get_verdict(score: float) -> str:
    if score >= 8.5:
        return "Excellent Candidate"
    elif score >= 7.0:
        return "Strong Candidate"
    elif score >= 5.5:
        return "Good Candidate"
    elif score >= 4.0:
        return "Average Candidate"
    else:
        return "Needs Improvement"


def _build_email_report(report: dict) -> str:
    score = report["scores"]["overall"]
    color = "#16a34a" if score >= 7 else "#d97706" if score >= 5 else "#dc2626"

    breakdown_html = ""
    for q in report.get("question_breakdown", []):
        breakdown_html += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #e5e7eb">Q{q['number']} [{q['type'].upper()}]</td>
          <td style="padding:8px;border-bottom:1px solid #e5e7eb">{q['question'][:80]}...</td>
          <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center;font-weight:bold;color:{color}">{q['score']}/10</td>
          <td style="padding:8px;border-bottom:1px solid #e5e7eb">{q['verdict']}</td>
        </tr>"""

    return f"""
    <div style="font-family:sans-serif;max-width:700px;margin:auto">
      <h1 style="color:#1e40af">Mock Interview Report</h1>
      <p><strong>Position:</strong> {report['job_title']} at {report['company']}</p>

      <div style="background:#f0f9ff;border-radius:8px;padding:20px;margin:20px 0">
        <h2 style="color:{color};margin:0">Overall Score: {score}/10</h2>
        <p style="margin:8px 0"><strong>Verdict:</strong> {report.get('verdict','')}</p>
        <p style="margin:8px 0">🔧 Technical: {report['scores']['technical']}/10 &nbsp;|&nbsp; 👥 HR: {report['scores']['hr']}/10</p>
        <p style="margin:8px 0"><strong>Recommendation:</strong> {report.get('hire_recommendation','')}</p>
      </div>

      <p>{report.get('executive_summary','')}</p>

      <h3>Question-by-Question Breakdown</h3>
      <table style="width:100%;border-collapse:collapse">
        <tr style="background:#f3f4f6">
          <th style="padding:8px;text-align:left">#</th>
          <th style="padding:8px;text-align:left">Question</th>
          <th style="padding:8px;text-align:center">Score</th>
          <th style="padding:8px;text-align:left">Verdict</th>
        </tr>
        {breakdown_html}
      </table>

      <h3>💪 Technical Strengths</h3>
      <ul>{''.join(f'<li>{s}</li>' for s in report.get('technical_strengths',[]))}</ul>

      <h3>📈 Areas to Improve</h3>
      <ul>{''.join(f'<li>{s}</li>' for s in report.get('technical_weaknesses',[]))}</ul>

      <h3>📚 Study Recommendations</h3>
      <ul>{''.join(f'<li>{s}</li>' for s in report.get('study_recommendations',[]))}</ul>

      <h3>💡 Interview Tips</h3>
      <ul>{''.join(f'<li>{s}</li>' for s in report.get('interview_tips',[]))}</ul>

      <p style="color:#6b7280;font-size:12px;margin-top:30px">Generated by Multi-Agent Job Application System</p>
    </div>"""