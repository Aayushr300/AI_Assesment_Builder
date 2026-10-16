"""All Supabase/Postgres access. Nothing else in the app talks to the DB directly."""
import logging

from app.database import supabase

logger = logging.getLogger(__name__)


# ---------- Job descriptions ----------

def save_job_description(job_title: str, description: str) -> str:
    result = supabase.table("job_descriptions").insert({
        "job_title": job_title,
        "description": description,
        "status": "analyzed",
    }).execute()
    if not result.data:
        raise ValueError("Could not save job description")
    return result.data[0]["id"]


def get_job_description(job_id: str) -> dict | None:
    result = supabase.table("job_descriptions").select("*").eq(
        "id", job_id
    ).limit(1).execute()
    return result.data[0] if result.data else None


# ---------- Master competencies (taxonomy in DB) ----------

def load_master_competency_ids() -> dict[str, str]:
    """Return {competency_name: id} from the master `competencies` table."""
    result = supabase.table("competencies").select("id, name").execute()
    return {item["name"]: item["id"] for item in (result.data or [])}


# ---------- Job competencies (blueprint rows) ----------

def save_job_competencies(
    job_id: str,
    blueprint: list[dict],
    master_ids: dict[str, str],
) -> list[dict]:
    saved = []
    for item in blueprint:
        competency_id = master_ids.get(item["name"])
        if not competency_id:
            logger.warning("Competency missing from Supabase: %s", item["name"])
            continue

        evidence = ", ".join(item.get("evidence_keywords", []))
        result = supabase.table("job_competencies").insert({
            "job_description_id": job_id,
            "competency_id": competency_id,
            "importance": item.get("importance", "high"),
            "weight": item.get("weight", 0),
            "evidence": evidence,
        }).execute()
        saved.extend(result.data or [])
    return saved


# ---------- Blueprints ----------

def save_blueprint(
    job_id: str,
    analysis: dict,
    blueprint: list[dict],
    responsibilities: list[str],
    total_marks: int,
) -> dict:
    result = supabase.table("assessment_blueprints").insert({
        "job_description_id": job_id,
        "version": 1,
        "status": "draft",
        "total_marks": total_marks,
        "settings": {
            "responsibilities": responsibilities,
            "jd_analysis": analysis,
            "competencies": blueprint,
            "method": "Gemini analysis + local taxonomy + question bank",
        },
    }).execute()
    if not result.data:
        raise ValueError("Could not save assessment blueprint")
    return result.data[0]


def get_latest_blueprint_for_job(job_id: str) -> dict | None:
    result = supabase.table("assessment_blueprints").select("*").eq(
        "job_description_id", job_id
    ).order("version", desc=True).limit(1).execute()
    return result.data[0] if result.data else None


def get_blueprint_questions(blueprint_id: str) -> list[dict]:
    result = supabase.table("blueprint_questions").select(
        "position, marks, competency_id, questions(*)"
    ).eq("blueprint_id", blueprint_id).order("position").execute()
    return result.data or []


# ---------- Questions ----------

def find_question_by_text(question_text: str) -> str | None:
    result = supabase.table("questions").select("id").eq(
        "question_text", question_text
    ).limit(1).execute()
    return result.data[0]["id"] if result.data else None


def insert_question(question: dict) -> str:
    result = supabase.table("questions").insert({
        "question_text": question["question"],
        "question_type": question["type"],
        "difficulty": question["difficulty"],
        "marks": question["marks"],
        "status": "draft",
        "source": "local_question_bank",
    }).execute()
    if not result.data:
        raise ValueError("Could not insert question")
    return result.data[0]["id"]


def link_question_to_competency(question_id: str, competency_id: str) -> None:
    existing = supabase.table("question_competencies").select(
        "question_id"
    ).eq("question_id", question_id).eq(
        "competency_id", competency_id
    ).limit(1).execute()
    if not existing.data:
        supabase.table("question_competencies").insert({
            "question_id": question_id,
            "competency_id": competency_id,
        }).execute()


def link_question_to_blueprint(
    blueprint_id: str,
    question_id: str,
    position: int,
    marks: int,
    competency_id: str,
) -> None:
    supabase.table("blueprint_questions").insert({
        "blueprint_id": blueprint_id,
        "question_id": question_id,
        "position": position,
        "marks": marks,
        "competency_id": competency_id,
    }).execute()


# ---------- Health check ----------

def ping_competencies(limit: int = 10) -> list[dict]:
    result = supabase.table("competencies").select("id, name").limit(limit).execute()
    return result.data or []