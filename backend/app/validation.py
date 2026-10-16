"""Deterministic validation, normalization and quality checks.

Pure functions — no DB, no LLM, no FastAPI. Easy to unit-test.
"""
import re
from collections import Counter
from difflib import SequenceMatcher


# ---------- Text normalization ----------

def normalize_question(text: str) -> str:
    """Lowercase + strip punctuation + collapse whitespace."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# ---------- Seniority ----------

def validate_seniority(job_title: str, analysis: dict) -> dict:
    """Prevent obvious title/seniority contradictions."""
    title = (job_title or "").lower()
    seniority = str(analysis.get("seniority", "")).lower()

    title_levels = {
        "senior": ("senior", "senior"),
        "junior": ("junior", "junior"),
        "lead": ("lead", "Lead"),
        "principal": ("principal", "Principal"),
        "intern": ("intern", "Intern"),
        "entry": ("entry-level", "Entry-level"),
    }

    for keyword, (_, normalized) in title_levels.items():
        if keyword in title:
            if keyword == "entry" and "entry-level" not in title:
                continue

            if keyword == "senior" and seniority == "junior":
                analysis.setdefault("ambiguities", []).append(
                    "Model seniority conflicted with the supplied job title; "
                    "seniority was aligned to the explicit title."
                )

            analysis["seniority"] = normalized
            return analysis

    return analysis


# ---------- Duplicate detection ----------

def find_duplicate_pairs(questions: list[dict], threshold: float = 0.82) -> list[dict]:
    """Detect exact and near-duplicate questions."""
    texts = [q.get("question", "") for q in questions]
    normalized = [normalize_question(t) for t in texts]

    pairs = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if normalized[i] and normalized[i] == normalized[j]:
                pairs.append({
                    "question_1": i + 1,
                    "question_2": j + 1,
                    "similarity": 1.0,
                    "kind": "exact",
                })
            elif normalized[i] and normalized[j]:
                ratio = SequenceMatcher(
                    None, normalized[i], normalized[j]
                ).ratio()
                if ratio >= threshold:
                    pairs.append({
                        "question_1": i + 1,
                        "question_2": j + 1,
                        "similarity": round(ratio, 2),
                        "kind": "similar",
                    })
    return pairs


# ---------- Difficulty balance ----------

def check_difficulty_balance(questions: list[dict]) -> dict:
    """Return counts + a warning if the mix is unbalanced."""
    counts = Counter(
        str(q.get("difficulty", "unspecified")).lower() for q in questions
    )
    easy = counts.get("easy", 0)
    medium = counts.get("medium", 0)
    hard = counts.get("hard", 0)

    warning = None
    if len(questions) >= 3 and (easy == 0 or medium == 0 or hard == 0):
        warning = (
            "Difficulty mix does not include easy, medium and hard questions."
        )

    return {
        "counts": dict(counts),
        "easy": easy,
        "medium": medium,
        "hard": hard,
        "warning": warning,
    }


# ---------- Keyword overload ----------

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
    "with", "is", "are", "how", "what", "why", "would", "you",
    "your", "explain", "describe", "give", "example", "using",
}


def detect_keyword_overload(
    questions: list[dict],
    ratio_threshold: float = 0.4,
) -> list[dict]:
    """Flag keywords that appear in too many questions (overrepresentation).

    Only meaningful when there are at least 3 questions.
    """
    if len(questions) < 3:
        return []

    token_sets = []
    for q in questions:
        tokens = set(
            normalize_question(q.get("question", "")).split()
        )
        tokens = {t for t in tokens if t and t not in STOPWORDS and len(t) > 2}
        token_sets.append(tokens)

    counter = Counter()
    for tokens in token_sets:
        counter.update(tokens)

    total = len(questions)
    flagged = []
    for token, count in counter.items():
        if count / total >= ratio_threshold and count >= 3:
            flagged.append({
                "keyword": token,
                "question_count": count,
                "total_questions": total,
                "ratio": round(count / total, 2),
            })

    flagged.sort(key=lambda x: x["question_count"], reverse=True)
    return flagged


# ---------- Bias checks ----------

BIAS_PATTERNS = [
    (r"\bage\b", "Age-related term detected."),
    (r"\bgender\b|\bmale\b|\bfemale\b", "Gender-related term detected."),
    (r"\bmarried\b|\bsingle\b|\bchildren\b", "Personal-life term detected."),
    (r"\bnative speaker\b", "'Native speaker' may be discriminatory."),
    (r"\bhe\b|\bshe\b", "Gendered pronoun — prefer 'they'."),
]


def run_bias_checks(questions: list[dict]) -> list[dict]:
    """Return a list of potential bias issues (title + position)."""
    issues = []
    for index, q in enumerate(questions, start=1):
        text = q.get("question", "").lower()
        for pattern, message in BIAS_PATTERNS:
            if re.search(pattern, text):
                issues.append({
                    "question": index,
                    "issue": message,
                    "pattern": pattern,
                })
    return issues


# ---------- Full blueprint assessment ----------

def assess_blueprint(competencies: list[dict], questions: list[dict]) -> dict:
    """Deterministic coverage, weight, difficulty and duplicate checks."""
    warnings = []
    errors = []

    total_weight = round(
        sum(float(item.get("weight", 0)) for item in competencies), 2
    )
    if competencies and total_weight != 100:
        errors.append(
            f"Competency weights total {total_weight}%, not 100%."
        )

    if not competencies:
        errors.append("No competencies were detected from this JD.")

    if not questions:
        warnings.append(
            "No question-bank questions matched the detected competencies."
        )

    duplicate_pairs = find_duplicate_pairs(questions)
    if duplicate_pairs:
        warnings.append(
            f"{len(duplicate_pairs)} possible duplicate/similar "
            "question pair(s) found."
        )

    difficulty = check_difficulty_balance(questions)
    if difficulty["warning"]:
        warnings.append(difficulty["warning"])

    overload = detect_keyword_overload(questions)
    if overload:
        warnings.append(
            f"{len(overload)} keyword(s) appear in a large share of "
            "questions (possible overrepresentation)."
        )

    bias_issues = run_bias_checks(questions)
    if bias_issues:
        warnings.append(
            f"{len(bias_issues)} potential bias issue(s) detected."
        )

    # Coverage per competency
    question_counts = Counter(q.get("competency", "Unmapped") for q in questions)
    coverage = []
    for item in competencies:
        name = item.get("name", "Unknown")
        count = question_counts.get(name, 0)
        coverage.append({
            "competency": name,
            "weight": item.get("weight", 0),
            "question_count": count,
            "covered": count > 0,
            "easy": sum(
                1 for q in questions
                if q.get("competency") == name
                and str(q.get("difficulty", "")).lower() == "easy"
            ),
            "medium": sum(
                1 for q in questions
                if q.get("competency") == name
                and str(q.get("difficulty", "")).lower() == "medium"
            ),
            "hard": sum(
                1 for q in questions
                if q.get("competency") == name
                and str(q.get("difficulty", "")).lower() == "hard"
            ),
        })

    uncovered = [c["competency"] for c in coverage if not c["covered"]]
    if uncovered:
        warnings.append(
            "Competencies without questions: " + ", ".join(uncovered)
        )

    # Rough duration estimate (only for planning)
    estimated_duration = sum(
        3 if str(q.get("type", "")).lower() == "technical"
        else 8 if str(q.get("type", "")).lower() in (
            "practical", "scenario", "work-sample"
        )
        else 5
        for q in questions
    )

    # Simple diagnostic score (not psychometric-validated)
    score = max(
        0,
        min(
            100,
            100
            - len(errors) * 25
            - len(warnings) * 8
            - len(duplicate_pairs) * 5,
        ),
    )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "quality_score": score,
        "total_weight": total_weight,
        "difficulty_distribution": difficulty["counts"],
        "duplicate_pairs": duplicate_pairs,
        "keyword_overload": overload,
        "bias_issues": bias_issues,
        "coverage": coverage,
        "uncovered_competencies": uncovered,
        "estimated_duration_minutes": estimated_duration,
    }