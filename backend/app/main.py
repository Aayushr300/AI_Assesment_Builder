
import re

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.question_bank import QUESTION_BANK
from app.embeddings import upsert_question_embeddings
from app.jd_analyzer import analyze_job_description, generate_assessment_questions
from app import repository
from app.validation import (
    normalize_question,
    validate_seniority,
    assess_blueprint,
)


from app.ai_engine import run_analysis
from app.coverage import build_evidence_coverage, build_coverage_heatmap


app = FastAPI(
    title="AI Assessment Blueprint Builder",
    version="1.1.0",
)




class JobDescriptionRequest(BaseModel):
    job_title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20)


class GenerateQuestionsRequest(BaseModel):
    job_title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20)
    competencies: list[str] = Field(min_length=1, max_length=8)
    existing_questions: list[str] = Field(default_factory=list, max_length=100)




def create_blueprint(competencies):
    if not competencies:
        return []

    weight = round(100 / len(competencies), 2)
    result = []

    for index, item in enumerate(competencies):
        final_weight = (
            round(100 - weight * (len(competencies) - 1), 2)
            if index == len(competencies) - 1
            else weight
        )

        result.append({**item, "weight": final_weight})

    return result




def build_analysis_text(request, analysis):
    parts = [
        request.job_title,
        request.description,
        " ".join(analysis.get("mandatory_skills", [])),
        " ".join(analysis.get("supporting_skills", [])),
        " ".join(analysis.get("tools", [])),
        " ".join(
            item.get("phrase", "")
            for item in analysis.get("evidence_map", [])
        ),
    ]
    return "\n".join(part for part in parts if part)



@app.on_event("startup")
def _seed_embeddings():
    try:
        upsert_question_embeddings(QUESTION_BANK)
    except Exception as exc:
        print("Embedding seed at startup failed:", exc)
        
@app.get("/")
def home():
    return {
        "success": True,
        "message": "AI Assessment Blueprint Builder API is running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/analyze-jd")
def analyze_jd(request: JobDescriptionRequest):
    try:
        result = run_analysis(request.job_title, request.description)
        return {
            "success": True,
            "job_title": request.job_title,
            "analysis": result["analysis"],
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"JD analysis failed: {exc}")

    
@app.post("/analyze-job")
def analyze_job(request: JobDescriptionRequest):
    try:
        # 1-6. Deterministic pipeline (LLM + taxonomy + blueprint)
        result = run_analysis(request.job_title, request.description)
        analysis        = result["analysis"]
        competencies    = result["competencies"]
        ambiguous       = result["ambiguous_skills"]
        responsibilities = result["responsibilities"]
        blueprint       = result["blueprint"]
        selected_questions = result["selected_questions"]

        # 7. Persist
        job_id = repository.save_job_description(request.job_title, request.description)
        master_ids = repository.load_master_competency_ids()
        repository.save_job_competencies(job_id, blueprint, master_ids)

        valid_questions = [q for q in selected_questions if q.get("competency") in master_ids]
        total_marks = sum(int(q.get("marks", 0)) for q in valid_questions)

        saved_blueprint = repository.save_blueprint(
            job_id=job_id,
            analysis=analysis,
            blueprint=blueprint,
            responsibilities=responsibilities,
            total_marks=total_marks,
        )
        blueprint_id = saved_blueprint["id"]

        saved_questions = []
        for position, question in enumerate(valid_questions, start=1):
            question_id = repository.find_question_by_text(question["question"])
            if not question_id:
                question_id = repository.insert_question(question)
            competency_id = master_ids[question["competency"]]
            repository.link_question_to_competency(question_id, competency_id)
            repository.link_question_to_blueprint(
                blueprint_id=blueprint_id,
                question_id=question_id,
                position=position,
                marks=question["marks"],
                competency_id=competency_id,
            )
            saved_questions.append({**question, "database_id": question_id})

        # 8. Reports
        validation = assess_blueprint(blueprint, saved_questions)
        evidence_coverage = build_evidence_coverage(
            analysis.get("evidence_map", []),
            blueprint,
            saved_questions,
        )
        coverage_heatmap = build_coverage_heatmap(blueprint, saved_questions)

        return {
            "success": True,
            "job_id": job_id,
            "blueprint_id": blueprint_id,
            "job_title": request.job_title,
            "analysis": analysis,
            "competencies": competencies,
            "ambiguous_skills": ambiguous,
            "responsibilities": responsibilities,
            "evidence_map": analysis.get("evidence_map", []),
            "blueprint": blueprint,
            "questions": saved_questions,
            "total_questions": len(saved_questions),
            "total_marks": total_marks,
            "validation": validation,
            "evidence_coverage": evidence_coverage,
            "coverage_heatmap": coverage_heatmap,
            "message": "Assessment saved to Supabase",
        }

    except Exception as exc:
        print("ASSESSMENT PROCESSING ERROR:", repr(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Assessment processing failed: {exc}",
        )


    


@app.post("/generate-gap-questions")
def generate_gap_questions(request: GenerateQuestionsRequest):
    """Generate draft questions for HR review; nothing is published or saved here."""
    try:
        drafts = generate_assessment_questions(
            job_title=request.job_title,
            description=request.description,
            competencies=request.competencies,
            existing_questions=request.existing_questions,
        )
        # Add a second deterministic duplicate check against the existing bank.
        existing_norm = {normalize_question(q) for q in request.existing_questions if normalize_question(q)}
        bank_norm = {normalize_question(q.get("question", "")) for q in QUESTION_BANK}
        for draft in drafts:
            norm = normalize_question(draft.get("question", ""))
            draft["possible_duplicate"] = bool(norm and (norm in existing_norm or norm in bank_norm))
            draft["review_status"] = "pending"
        return {"success": True, "draft_questions": drafts, "saved": False,
                "message": "Generated drafts are not published. HR must review each question."}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Question generation failed: {exc}")


@app.get("/assessments/{job_id}")
def get_assessment(job_id: str):
    try:
        job = repository.get_job_description(job_id)
        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job description not found",
            )

        assessment = repository.get_latest_blueprint_for_job(job_id)
        if not assessment:
            return {
                "success": True,
                "job": job,
                "assessment": None,
                "questions": [],
            }

        questions = repository.get_blueprint_questions(assessment["id"])

        return {
            "success": True,
            "job": job,
            "assessment": assessment,
            "questions": questions,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/questions")
def get_questions(competency: str | None = None):
    if competency:
        results = [
            question for question in QUESTION_BANK
            if question["competency"].lower() == competency.lower()
        ]
    else:
        results = QUESTION_BANK

    return {
        "success": True,
        "count": len(results),
        "questions": results,
    }

@app.get("/database-health")
def database_health():
    try:
        return {
            "success": True,
            "database": "connected",
            "competencies": repository.ping_competencies(),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Database connection failed: {exc}",
        )