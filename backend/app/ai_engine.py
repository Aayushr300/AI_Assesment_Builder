"""Pipeline orchestration: JD → analysis → taxonomy → blueprint → questions."""
import logging
from app.embeddings import upsert_question_embeddings
from app.question_bank import QUESTION_BANK
from app.jd_analyzer import analyze_job_description
from app.taxonomy import (
    extract_competencies,
    extract_responsibilities,
    retrieve_questions,
    merge_duplicates,
    find_ambiguous_requirements,
)
from app.blueprint import create_blueprint
from app.validation import validate_seniority

logger = logging.getLogger(__name__)


def build_analysis_text(job_title: str, description: str, analysis: dict) -> str:
    parts = [
        job_title,
        description,
        " ".join(analysis.get("mandatory_skills", [])),
        " ".join(analysis.get("supporting_skills", [])),
        " ".join(analysis.get("tools", [])),
        " ".join(
            item.get("phrase", "")
            for item in analysis.get("evidence_map", [])
        ),
    ]
    return "\n".join(p for p in parts if p)


def run_analysis(job_title: str, description: str) -> dict:
    """Full deterministic pipeline after the JD text is available.

    Returns everything needed to persist + respond.
    """
    # 1. LLM
    analysis = analyze_job_description(
        f"Job title: {job_title}\n\nJob description:\n{description}"
    )

    # 2. Seniority alignment
    analysis = validate_seniority(job_title, analysis)

    # 3. Taxonomy match + normalize
    combined = build_analysis_text(job_title, description, analysis)
    competencies = merge_duplicates(extract_competencies(combined))

    # 4. Ambiguity flags
    ambiguous = find_ambiguous_requirements(analysis)
    if ambiguous:
        analysis.setdefault("ambiguities", []).extend(
            f"Skill not in taxonomy: {s}" for s in ambiguous
        )

    # 5. Responsibilities
    responsibilities = analysis.get("responsibilities") or extract_responsibilities(description)

    # 6. Blueprint (adaptive) + questions
    blueprint = create_blueprint(
        competencies,
        seniority=analysis.get("seniority", "unknown"),
    )
    
    try:
        upsert_question_embeddings(QUESTION_BANK)
    except Exception as exc:
        logger.warning("Embedding seed failed: %s", exc)

    selected_questions = retrieve_questions(
        competencies,
        query_text=combined,
        use_rag=True,
    )

    return {
        "analysis": analysis,
        "competencies": competencies,
        "ambiguous_skills": ambiguous,
        "responsibilities": responsibilities,
        "blueprint": blueprint,
        "selected_questions": selected_questions,
    }