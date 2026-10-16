"""RAG layer using Supabase pgvector + sentence-transformers."""
import logging

from app.database import supabase

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_model = None


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_text(text: str) -> list[float]:
    model = _load_model()
    return model.encode(text or "", normalize_embeddings=True).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    model = _load_model()
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.tolist() for v in vecs]


def _question_document(q: dict) -> str:
    parts = [
        q.get("question") or q.get("question_text", ""),
        q.get("competency", ""),
        q.get("subskill", ""),
        q.get("cognitive_level", ""),
        " ".join(q.get("tags") or []),
    ]
    return " | ".join(p for p in parts if p)


def upsert_question_embeddings(questions: list[dict]) -> int:
    """Embed + upsert questions into Supabase."""
    if not questions:
        return 0

    docs = [_question_document(q) for q in questions]
    vectors = embed_batch(docs)

    rows = []
    for q, vec in zip(questions, vectors):
        rows.append({
            "question_text": q.get("question") or q.get("question_text"),
            "competency": q.get("competency"),
            "difficulty": q.get("difficulty"),
            "question_type": q.get("type") or q.get("question_type"),
            "marks": int(q.get("marks", 5)),
            "status": q.get("status", "draft"),
            "source": q.get("source", "local_question_bank"),
            "embedding": vec,
        })

    supabase.table("questions").upsert(
        rows, on_conflict="question_text"
    ).execute()
    logger.info("Upserted %s questions with embeddings", len(rows))
    return len(rows)


def semantic_search(
    query: str,
    top_k: int = 20,
    competency: str | None = None,
) -> list[dict]:
    """Search questions semantically via Supabase pgvector."""
    if not query or not query.strip():
        return []
    vec = embed_text(query)
    try:
        resp = supabase.rpc(
            "match_questions",
            {
                "query_embedding": vec,
                "match_count": top_k,
                "filter_competency": competency,
            },
        ).execute()
    except Exception as exc:
        logger.exception("pgvector RPC failed: %s", exc)
        return []
    return resp.data or []


def tag_question_semantically(question: str, candidates: list[str]) -> dict:
    """W4: detect wrong-skill assignment."""
    if not question or not candidates:
        return {"best_competency": None, "confidence": 0.0, "candidates": []}

    import numpy as np
    q_vec = np.array(embed_text(question))
    c_vecs = embed_batch(candidates)

    scored = []
    for name, cv in zip(candidates, c_vecs):
        sim = float(np.dot(q_vec, np.array(cv)))
        scored.append({"competency": name, "similarity": round(sim, 4)})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return {
        "best_competency": scored[0]["competency"],
        "confidence": scored[0]["similarity"],
        "candidates": scored,
    }