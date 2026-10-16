"""Coverage + explainability report (R7, W1, W3)."""
from collections import Counter

from app.taxonomy import normalize_competency_name


def build_evidence_coverage(
    evidence_map: list[dict],
    blueprint: list[dict],
    saved_questions: list[dict],
) -> list[dict]:
    """Map each JD evidence phrase to its competency, questions and status."""
    by_name = {b["name"].casefold(): b for b in blueprint}

    coverage = []
    for evidence in evidence_map or []:
        raw_name = (evidence.get("competency") or "").strip()

        # Step 1: direct match
        matched = by_name.get(raw_name.casefold())

        # Step 2: normalize via synonyms, then match
        if not matched:
            normalized = normalize_competency_name(raw_name)
            matched = by_name.get(normalized.casefold())

        final_name = matched["name"] if matched else raw_name

        related = [
            q.get("question", "")
            for q in saved_questions
            if q.get("competency") == final_name
        ]

        coverage.append({
            "phrase": evidence.get("phrase", ""),
            "raw_competency": raw_name,
            "competency": final_name,
            "confidence": evidence.get("confidence", 0),
            "importance": evidence.get("importance", ""),
            "question_count": len(related),
            "questions": related,
            "status": "covered" if related else "uncovered",
        })

    return coverage


def build_coverage_heatmap(
    blueprint: list[dict],
    saved_questions: list[dict],
) -> list[dict]:
    """Assessed / under-assessed / missing per competency (W3)."""
    counts = Counter(q.get("competency", "") for q in saved_questions)

    rows = []
    for item in blueprint:
        name = item["name"]
        count = counts.get(name, 0)

        if count == 0:
            status = "missing"
        elif count == 1:
            status = "under_assessed"
        else:
            status = "assessed"

        rows.append({
            "competency": name,
            "weight": item.get("weight", 0),
            "question_count": count,
            "status": status,
            "easy": sum(
                1 for q in saved_questions
                if q.get("competency") == name and q.get("difficulty") == "easy"
            ),
            "medium": sum(
                1 for q in saved_questions
                if q.get("competency") == name and q.get("difficulty") == "medium"
            ),
            "hard": sum(
                1 for q in saved_questions
                if q.get("competency") == name and q.get("difficulty") == "hard"
            ),
        })

    return rows