
import os
import json
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",   # Lightweight model, usually lower load
    "gemini-2.5-flash-lite",   # Stable fallback option
]


def analyze_job_description(description: str) -> dict:
    if not description or len(description.strip()) < 20:
        raise ValueError("Please provide a valid job description.")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from backend/.env")

    prompt = f"""
Analyze this job description for an AI Assessment Blueprint Builder.

Return JSON with these fields:
{{
  "responsibilities": [],
  "mandatory_skills": [],
  "supporting_skills": [],
  "seniority": "Unknown",
  "tools": [],
  "observable_behaviors": [],
  "evidence_map": [
    {{
      "phrase": "Exact phrase from the JD",
      "competency": "Skill name",
      "confidence": 0.9,
      "importance": "high"
    }}
  ],
  "ambiguities": []
}}

Rules:
- Use only information supported by the JD.
- Copy evidence phrases exactly from the JD.
- Confidence must be between 0 and 1.
- Importance must be high, medium, or low.
- Do not invent skills or responsibilities.
- Use empty arrays when information is missing.
- Return JSON only.

JOB DESCRIPTION:
{description}
"""

    client = genai.Client(api_key=api_key)
    errors = []

    try:
        for model in MODELS:
            for attempt in range(2):
                try:
                    print(
                        f"Trying {model}, attempt {attempt + 1}"
                    )

                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config={
                            "response_mime_type": "application/json",
                            "temperature": 0.1,
                        },
                    )

                    if not response.text:
                        raise ValueError("Empty AI response")

                    analysis = json.loads(response.text)

                    required = [
                        "responsibilities",
                        "mandatory_skills",
                        "supporting_skills",
                        "seniority",
                        "tools",
                        "observable_behaviors",
                        "evidence_map",
                        "ambiguities",
                    ]

                    for field in required:
                        if field not in analysis:
                            raise ValueError(
                                f"Missing field: {field}"
                            )

                    print(f"JD analysis succeeded with {model}")
                    return analysis

                except Exception as exc:
                    errors.append(f"{model}: {exc}")
                    print(f"{model} failed: {exc}")

                    # Retry only transient/server errors.
                    message = str(exc).lower()
                    transient = any(
                        marker in message
                        for marker in [
                            "503", "unavailable", "429",
                            "resource_exhausted", "500",
                            "502", "504", "timeout",
                            "temporarily"
                        ]
                    )

                    if transient and attempt == 0:
                        time.sleep(2)
                        continue

                    # Try the next model.
                    break

        raise RuntimeError(
            "All Gemini models failed. " + " | ".join(errors)
        )

    finally:
        client.close()



def generate_assessment_questions(
    job_title: str,
    description: str,
    competencies: list[str],
    existing_questions: list[str] | None = None,
) -> list[dict]:
    """Create supplementary draft questions; callers must obtain HR approval."""
    if not competencies:
        raise ValueError("Select at least one competency.")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from backend/.env")

    existing = existing_questions or []
    prompt = f"""
You are assisting an HR professional who is designing a job-related assessment.
Generate exactly one useful supplementary question for each requested competency.
Prefer realistic scenario/work-sample questions where suitable. Questions must
be answerable, relevant to the job description, non-discriminatory, and not
repeat any existing question. Do not infer personal traits unrelated to work.
Return JSON only as:
{{
  "questions": [
    {{
      "question": "question text",
      "competency": "exact requested competency",
      "difficulty": "easy|medium|hard",
      "type": "scenario|practical|technical|work-sample",
      "marks": 5,
      "rationale": "brief explanation of what it measures"
    }}
  ]
}}
Use 5 marks for easy, 10 for medium, and 15 for hard. Only use the requested
competency names. These are drafts for human review, not approved questions.

JOB TITLE: {job_title}
JOB DESCRIPTION:
{description}

REQUESTED COMPETENCIES:
{json.dumps(competencies, ensure_ascii=False)}

EXISTING QUESTIONS TO AVOID:
{json.dumps(existing[:100], ensure_ascii=False)}
"""
    client = genai.Client(api_key=api_key)
    try:
        errors = []
        for model in MODELS:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json", "temperature": 0.2},
                )
                if not response.text:
                    raise ValueError("Empty AI response")
                parsed = json.loads(response.text)
                drafts = parsed.get("questions", [])
                if not isinstance(drafts, list):
                    raise ValueError("Gemini returned an invalid questions list")
                cleaned = []
                allowed = set(competencies)
                for item in drafts:
                    if not isinstance(item, dict):
                        continue
                    question = str(item.get("question", "")).strip()
                    competency = str(item.get("competency", "")).strip()
                    difficulty = str(item.get("difficulty", "medium")).lower()
                    qtype = str(item.get("type", "scenario")).lower()
                    if not question or competency not in allowed:
                        continue
                    if difficulty not in {"easy", "medium", "hard"}:
                        difficulty = "medium"
                    if qtype not in {"scenario", "practical", "technical", "work-sample"}:
                        qtype = "scenario"
                    marks = item.get("marks", {"easy": 5, "medium": 10, "hard": 15}[difficulty])
                    try:
                        marks = int(marks)
                    except (TypeError, ValueError):
                        marks = {"easy": 5, "medium": 10, "hard": 15}[difficulty]
                    cleaned.append({
                        "question": question,
                        "competency": competency,
                        "difficulty": difficulty,
                        "type": qtype,
                        "marks": max(1, min(marks, 30)),
                        "rationale": str(item.get("rationale", "")).strip(),
                        "source": "gemini_draft",
                    })
                if not cleaned:
                    raise ValueError("Gemini did not return any valid draft questions")
                return cleaned
            except Exception as exc:
                errors.append(f"{model}: {exc}")
        raise RuntimeError("Question generation failed. " + " | ".join(errors))
    finally:
        client.close()
