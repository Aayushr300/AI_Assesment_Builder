"""Blueprint creation + adaptive weighting (R3, W2)."""
from app.taxonomy import COMPETENCIES


SENIORITY_DIFFICULTY_MIX = {
    "intern":        {"easy": 0.70, "medium": 0.25, "hard": 0.05},
    "entry-level":   {"easy": 0.60, "medium": 0.35, "hard": 0.05},
    "junior":        {"easy": 0.50, "medium": 0.40, "hard": 0.10},
    "mid":           {"easy": 0.30, "medium": 0.50, "hard": 0.20},
    "senior":        {"easy": 0.15, "medium": 0.50, "hard": 0.35},
    "lead":          {"easy": 0.10, "medium": 0.40, "hard": 0.50},
    "principal":     {"easy": 0.05, "medium": 0.35, "hard": 0.60},
    "unknown":       {"easy": 0.33, "medium": 0.34, "hard": 0.33},
}


def create_blueprint(
    competencies: list[dict],
    seniority: str = "unknown",
) -> list[dict]:
    """Adaptive weighting: base weight × importance × evidence strength.

    Ensures weights sum to exactly 100 (last item absorbs rounding).
    """
    if not competencies:
        return []

    importance_weight = {"high": 3.0, "medium": 2.0, "low": 1.0}
    raw_scores = []
    for item in competencies:
        base = importance_weight.get(item.get("importance", "high"), 2.0)
        evidence_bonus = 1.0 + 0.1 * min(len(item.get("evidence_keywords", [])), 5)
        raw_scores.append(base * evidence_bonus)

    total = sum(raw_scores) or 1.0
    weights = [round(score / total * 100, 2) for score in raw_scores]

    # Fix rounding so total = 100
    diff = round(100 - sum(weights), 2)
    weights[-1] = round(weights[-1] + diff, 2)

    return [
        {**item, "weight": w}
        for item, w in zip(competencies, weights)
    ]


def target_difficulty_mix(seniority: str) -> dict:
    """Return the ideal easy/medium/hard mix for the given seniority."""
    key = (seniority or "unknown").strip().lower()
    return SENIORITY_DIFFICULTY_MIX.get(key, SENIORITY_DIFFICULTY_MIX["unknown"])