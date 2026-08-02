from __future__ import annotations

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
    llm = get_llm_service()

    system_prompt = f"""You are an expert interviewer at {company} interviewing for the position of {job_title}.

Candidate Resume:
{resume_text[:2000]}

Job Description:
{job_description[:1500]}

Your job:
- Ask {technical_count} technical questions and {hr_count} HR/behavioral questions
- Ask ONE question at a time
- After each answer, give brief feedback then ask the next question
- Be conversational, professional and encouraging
- Start by greeting the candidate and asking the first question

Start the interview now with a warm greeting and your first question."""

    # Start conversation
    first_message = await llm.chat(
        messages=[{"role": "user", "content": "Hello, I'm ready for the interview."}],
        system_prompt=system_prompt,
    )

    session = {
        "session_id": session_id,
        "user_id": user_id,
        "job_title": job_title,
        "company": company,
        "system_prompt": system_prompt,
        "messages": [
            {"role": "user", "content": "Hello, I'm ready for the interview."},
            {"role": "assistant", "content": first_message},
        ],
        "question_count": 0,
        "total_questions": technical_count + hr_count,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "in_progress",
    }
    save_session(session_id, session)

    return {
        "session_id": session_id,
        "status": "started",
        "total_questions": technical_count + hr_count,
        "current_question_number": 1,
        "current_question": {
            "id": 1,
            "type": "conversational",
            "difficulty": "medium",
            "question": first_message,
        },
        "job_title": job_title,
        "company": company,
        "message": "Interview started!",
    }

async def submit_answer(session_id: str, answer: str) -> dict:
    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    llm = get_llm_service()

    # Add user answer to history
    session["messages"].append({"role": "user", "content": answer})
    session["question_count"] += 1

    is_last = session["question_count"] >= session["total_questions"]

    if is_last:
        # Ask for final summary
        session["messages"].append({
            "role": "user",
            "content": "That was my last answer. Please give me overall feedback and end the interview."
        })

    # Get AI response
    ai_response = await llm.chat(
        messages=session["messages"],
        system_prompt=session["system_prompt"],
    )

    session["messages"].append({"role": "assistant", "content": ai_response})
    session["status"] = "completed" if is_last else "in_progress"
    save_session(session_id, session)

    return {
        "session_id": session_id,
        "question_number": session["question_count"],
        "evaluation": {
            "score": 7.0,
            "max_score": 10,
            "verdict": "Good",
            "strengths": [],
            "improvements": [],
            "follow_up_question": "",
            "model_answer_hint": ai_response,
        },
        "is_complete": is_last,
        "next_question_number": session["question_count"] + 1,
        "next_question": None if is_last else {
            "id": session["question_count"] + 1,
            "type": "conversational",
            "difficulty": "medium",
            "question": ai_response,
        },
        "remaining": max(0, session["total_questions"] - session["question_count"]),
        "message": ai_response,
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

        report = await llm.generate_structured(
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
        )
    except Exception as e:
        logger.warning("Report generation failed", extra={"error": str(e)})
        report = {
            "overall_score": overall_avg,
            "technical_score": technical_avg,
            "hr_score": hr_avg,
            "verdict": _get_verdict(overall_avg),
            "hire_recommendation": "Review required",
            "executive_summary": f"Candidate completed {len(questions)} questions with overall score {overall_avg}/10.",
            "technical_strengths": [],
            "technical_weaknesses": [],
            "hr_strengths": [],
            "hr_weaknesses": [],
            "top_skills_demonstrated": [],
            "skills_to_improve": [],
            "study_recommendations": [],
            "interview_tips": [],
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