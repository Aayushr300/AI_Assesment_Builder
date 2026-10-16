"""Local competency taxonomy + normalization + duplicate merging (R2).

Pure functions — no DB, no LLM, no FastAPI.
"""
import re

from app.question_bank import QUESTION_BANK


# ---------- Taxonomy ----------

COMPETENCIES = {
    "Python Programming": [
        "python", "programming", "oop", "object-oriented",
        "decorators", "classes", "functions", "scripting",
    ],
    "FastAPI and REST APIs": [
        "fastapi", "rest api", "rest apis", "api development",
        "endpoints", "http", "api testing", "restful",
    ],
    "SQL and Databases": [
        "sql", "mysql", "postgresql", "database",
        "databases", "queries", "rdbms",
    ],
    "Authentication and JWT": [
        "jwt", "authentication", "authorization",
        "access token", "security", "oauth",
    ],
    "Problem Solving": [
        "problem-solving", "problem solving", "debugging",
        "troubleshooting", "analytical", "critical thinking",
    ],
    "Git and GitHub": [
        "git", "github", "version control", "branches",
        "pull request", "merge",
    ],
}


# Maps LLM-provided skill names → local taxonomy names.
# Extend this list as new LLM variants appear in production.
SYNONYMS = {
    # Python
    "python": "Python Programming",
    "python programming": "Python Programming",
    "programming": "Python Programming",
    "oop": "Python Programming",
    "object-oriented programming": "Python Programming",
    # APIs
    "fastapi": "FastAPI and REST APIs",
    "rest api": "FastAPI and REST APIs",
    "rest apis": "FastAPI and REST APIs",
    "api development": "FastAPI and REST APIs",
    "restful apis": "FastAPI and REST APIs",
    "api": "FastAPI and REST APIs",
    # DB
    "sql": "SQL and Databases",
    "database": "SQL and Databases",
    "databases": "SQL and Databases",
    "postgresql": "SQL and Databases",
    "mysql": "SQL and Databases",
    # Auth
    "jwt": "Authentication and JWT",
    "authentication": "Authentication and JWT",
    "authorization": "Authentication and JWT",
    "security": "Authentication and JWT",
    # Problem solving
    "problem solving": "Problem Solving",
    "debugging": "Problem Solving",
    "troubleshooting": "Problem Solving",
    "analytical": "Problem Solving",
    # Git
    "git": "Git and GitHub",
    "github": "Git and GitHub",
    "version control": "Git and GitHub",

     # LLM-returned variants we've seen in production
    "technical proficiency": "Python Programming",
    "api development": "FastAPI and REST APIs",
    "api design": "FastAPI and REST APIs",
    "backend development": "Python Programming",
    "troubleshooting": "Problem Solving",
    "analytical skills": "Problem Solving",
    "critical thinking": "Problem Solving",
    "database management": "SQL and Databases",
    "data modeling": "SQL and Databases",
    "query optimization": "SQL and Databases",
    "security": "Authentication and JWT",
    "access control": "Authentication and JWT",
    "version control": "Git and GitHub",
    "collaboration": "Git and GitHub",
    "code review": "Git and GitHub",

}


# ---------- Helpers ----------

def _word_boundary_regex(keyword: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)")


# ---------- Extraction ----------

def extract_competencies(description: str) -> list[dict]:
    """Match text against the local taxonomy using word-boundary keywords."""
    text = (description or "").lower()
    found = []

    for name, keywords in COMPETENCIES.items():
        matched = [
            keyword for keyword in keywords
            if _word_boundary_regex(keyword).search(text)
        ]
        if matched:
            found.append({
                "name": name,
                "evidence_keywords": matched,
                "importance": "high",
            })

    return found


def extract_responsibilities(description: str) -> list[str]:
    """Extract action-oriented sentences from a JD."""
    sentences = re.split(
        r"(?<=[.!?])\s+",
        (description or "").strip(),
    )

    action_words = (
        "develop", "build", "design", "create", "manage",
        "maintain", "implement", "debug", "deploy",
        "responsible for", "work with", "test",
    )

    return [
        sentence.strip()
        for sentence in sentences
        if any(word in sentence.lower() for word in action_words)
    ]


# ---------- Normalization ----------

def normalize_competency_name(raw: str) -> str:
    """Map an LLM-provided skill to a taxonomy competency name.

    Returns the original (stripped) if no mapping exists.
    """
    key = (raw or "").strip().lower()
    if not key:
        return ""

    # Exact taxonomy match
    for name in COMPETENCIES:
        if name.lower() == key:
            return name

    # Synonym lookup
    if key in SYNONYMS:
        return SYNONYMS[key]

    # Substring match (e.g. "Advanced Python" → "Python Programming")
    for alias, canonical in SYNONYMS.items():
        if alias and alias in key:
            return canonical

    return raw.strip()


def merge_duplicates(competencies: list[dict]) -> list[dict]:
    """Combine duplicate competencies (by normalized name) into one entry.

    Merges: evidence_keywords (union), keeps highest importance.
    """
    importance_rank = {"high": 3, "medium": 2, "low": 1}
    merged: dict[str, dict] = {}

    for item in competencies:
        canonical = normalize_competency_name(item.get("name", ""))
        if not canonical:
            continue

        existing = merged.get(canonical)
        if not existing:
            merged[canonical] = {
                "name": canonical,
                "evidence_keywords": list(item.get("evidence_keywords", [])),
                "importance": item.get("importance", "high"),
            }
        else:
            keywords = set(existing["evidence_keywords"])
            keywords.update(item.get("evidence_keywords", []))
            existing["evidence_keywords"] = sorted(keywords)

            new_rank = importance_rank.get(item.get("importance", "high"), 3)
            old_rank = importance_rank.get(existing["importance"], 3)
            if new_rank > old_rank:
                existing["importance"] = item["importance"]

    return list(merged.values())


def find_ambiguous_requirements(analysis: dict) -> list[str]:
    """Return JD skills that don't map to any taxonomy competency."""
    raw_skills = (
        analysis.get("mandatory_skills", [])
        + analysis.get("supporting_skills", [])
        + analysis.get("tools", [])
    )

    known_aliases = set(SYNONYMS.keys())
    known_canonical = {c.lower() for c in COMPETENCIES}

    unknown = []
    for skill in raw_skills:
        lowered = (skill or "").strip().lower()
        if not lowered:
            continue
        if lowered in known_aliases or lowered in known_canonical:
            continue
        # Substring match against synonyms
        if any(alias in lowered for alias in known_aliases if alias):
            continue
        unknown.append(skill.strip())

    return sorted(set(unknown))



def _normalize_rag_hit(hit: dict) -> dict:
    """Normalize a pgvector hit to match the local question_bank shape."""
    return {
        "id": hit.get("id"),
        "question": hit.get("question_text") or hit.get("question", ""),
        "competency": hit.get("competency"),
        "difficulty": hit.get("difficulty"),
        "type": hit.get("question_type") or hit.get("type"),
        "marks": int(hit.get("marks", 5)),
        "similarity": hit.get("similarity"),
        "source": "rag",
    }


def retrieve_questions(
    competencies: list[dict],
    bank: list[dict] | None = None,
    query_text: str | None = None,
    use_rag: bool = True,
) -> list[dict]:
    """Retrieve questions.

    If `use_rag` and `query_text` are provided, use semantic search via pgvector.
    Otherwise fall back to exact competency match against the local bank.
    """
    if use_rag and query_text:
        try:
            from app.embeddings import semantic_search
            hits = semantic_search(query_text, top_k=20)
            if hits:
                return [_normalize_rag_hit(h) for h in hits]
        except Exception:
            pass

    from app.question_bank import QUESTION_BANK
    bank = bank if bank is not None else QUESTION_BANK
    names = {item["name"] for item in competencies}
    return [q for q in bank if q.get("competency") in names]