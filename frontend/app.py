"""Streamlit frontend for AI Assessment Blueprint Builder."""
import json
import os
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
from pypdf import PdfReader


API_URL = os.getenv(
    "ASSESSMENT_API_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


st.set_page_config(
    page_title="AI Assessment Blueprint Builder",
    page_icon="📋",
    layout="wide",
)

st.title("AI Assessment Blueprint Builder")
st.caption(
    "Analyze a job description and generate a draft assessment blueprint."
)


# ---------- Helpers ----------

def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))

    if reader.is_encrypted:
        raise ValueError(
            "This PDF is password-protected. Upload an unlocked PDF."
        )

    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")

    text = "\n".join(pages).strip()

    if not text:
        raise ValueError(
            "No selectable text found. This may be a scanned PDF; "
            "OCR is required for scanned documents."
        )

    return text


def call_api(endpoint: str, payload: dict) -> dict:
    try:
        response = requests.post(
            f"{API_URL}{endpoint}",
            json=payload,
            timeout=240,
        )

        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text

            raise RuntimeError(
                f"API returned HTTP {response.status_code}: {detail}"
            )

        return response.json()

    except requests.ConnectionError as exc:
        raise RuntimeError(
            "Cannot connect to FastAPI. Start the backend on port 8000."
        ) from exc
    except requests.Timeout as exc:
        raise RuntimeError(
            "The request timed out. Check the backend terminal and retry."
        ) from exc


# ---------- Sidebar ----------

with st.sidebar:
    st.subheader("Backend status")

    if st.button("Check API health", use_container_width=True):
        try:
            response = requests.get(f"{API_URL}/health", timeout=10)
            response.raise_for_status()
            st.success("Backend is reachable")
        except requests.RequestException as exc:
            st.error(f"Backend unavailable: {exc}")

    st.caption(f"API: {API_URL}")


# ---------- 1. Job details ----------

st.subheader("1. Job details")

job_title = st.text_input(
    "Job title",
    placeholder="e.g. Senior Python Developer",
)

upload = st.file_uploader(
    "Upload job description (PDF or TXT)",
    type=["pdf", "txt"],
)

manual_text = st.text_area(
    "Or paste the job description",
    height=220,
    placeholder=(
        "Paste the complete job description here, "
        "including responsibilities and required skills..."
    ),
)

extracted_text = ""

if upload is not None:
    try:
        file_bytes = upload.getvalue()

        if upload.name.lower().endswith(".pdf"):
            extracted_text = extract_pdf_text(file_bytes)
        else:
            extracted_text = file_bytes.decode(
                "utf-8-sig", errors="replace"
            ).strip()

        if extracted_text:
            st.success(f"Extracted text from {upload.name}")
            st.text_area(
                "Extracted document text",
                value=extracted_text,
                height=200,
                key="pdf_text_preview",
            )

    except Exception as exc:
        st.error(f"File reading failed: {exc}")

description = extracted_text or manual_text

st.caption(f"Characters available for analysis: {len(description.strip())}")

st.divider()
st.subheader("2. Analyze and generate blueprint")

if st.button(
    "Analyze Job & Generate Blueprint",
    type="primary",
    use_container_width=True,
):
    if len(job_title.strip()) < 2:
        st.error("Please enter a job title.")
    elif len(description.strip()) < 20:
        st.error(
            "Please upload a readable PDF/TXT or paste at least "
            "20 characters of job description."
        )
    else:
        payload = {
            "job_title": job_title.strip(),
            "description": description.strip(),
        }

        with st.spinner(
            "Analyzing JD, mapping competencies and saving assessment..."
        ):
            try:
                result = call_api("/analyze-job", payload)

                if not result.get("success"):
                    st.error("Assessment generation did not succeed.")
                else:
                    st.session_state["assessment_result"] = result
                    st.session_state["assessment_job_title"] = payload["job_title"]
                    st.session_state["assessment_description"] = payload["description"]
                    st.session_state.setdefault("generated_drafts", [])
                    st.success(
                        result.get("message", "Assessment generated successfully.")
                    )

            except Exception as exc:
                st.error(str(exc))


# ---------- 3. Assessment results ----------

result = st.session_state.get("assessment_result")

if result:
    st.divider()
    st.header("3. Assessment results")

    col1, col2, col3 = st.columns(3)

    col1.metric("Questions", result.get("total_questions", 0))
    col2.metric("Total marks", result.get("total_marks", 0))
    col3.metric("Competencies detected", len(result.get("competencies", [])))

    if result.get("job_id"):
        st.code(f"Job ID: {result['job_id']}")
    if result.get("blueprint_id"):
        st.code(f"Blueprint ID: {result['blueprint_id']}")

    # Ambiguous skills warning
    ambiguous = result.get("ambiguous_skills") or []
    if ambiguous:
        st.warning(
            "Skills not found in local taxonomy (reviewer confirmation needed): "
            + ", ".join(ambiguous)
        )

    with st.expander("AI job description analysis", expanded=True):
        st.json(result.get("analysis", {}))

    st.subheader("Competency weights")

    competencies = result.get("blueprint", [])

    if competencies:
        st.dataframe(
            [
                {
                    "Competency": item.get("name"),
                    "Importance": item.get("importance"),
                    "Weight (%)": item.get("weight"),
                    "Evidence keywords": ", ".join(
                        item.get("evidence_keywords", [])
                    ),
                }
                for item in competencies
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("No matching competencies found in the current taxonomy.")

    st.subheader("Selected questions")

    questions = result.get("questions", [])

    if questions:
        for index, question in enumerate(questions, start=1):
            with st.expander(
                f"{index}. {question.get('competency', 'Question')} "
                f"— {question.get('difficulty', 'Unspecified')}"
            ):
                st.write(question.get("question", ""))
                st.write(f"**Type:** {question.get('type', 'N/A')}")
                st.write(f"**Marks:** {question.get('marks', 0)}")

        export_data = {
            "job_title": result.get("job_title"),
            "analysis": result.get("analysis"),
            "blueprint": result.get("blueprint"),
            "questions": questions,
            "total_marks": result.get("total_marks"),
        }

        st.download_button(
            "Download assessment JSON",
            data=json.dumps(export_data, indent=2, ensure_ascii=False),
            file_name="assessment_blueprint.json",
            mime="application/json",
            use_container_width=True,
        )
    else:
        st.warning(
            "No questions matched the detected competencies. "
            "Review the taxonomy and local question bank."
        )

    # ---------- 4. Evidence Map & Coverage Heatmap ----------

    st.divider()
    st.header("4. Evidence Map & Coverage Heatmap")

    evidence_items = result.get("evidence_map") or result.get("analysis", {}).get("evidence_map", [])
    if evidence_items:
        st.dataframe(
            [
                {
                    "Exact JD phrase": item.get("phrase", ""),
                    "Mapped competency": item.get("competency", ""),
                    "Confidence": item.get("confidence", ""),
                    "Importance": item.get("importance", ""),
                }
                for item in evidence_items
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No evidence phrases were returned by the JD analysis.")

    validation = result.get("validation", {})
    coverage_rows = result.get("coverage_heatmap") or validation.get("coverage", [])

    if coverage_rows:
        coverage_df = pd.DataFrame(coverage_rows)
        st.caption(
            "Coverage is based on questions currently selected for this blueprint. "
            "status: assessed (2+), under_assessed (1), missing (0)."
        )

        def coverage_color(value):
            if value == 0:
                return "background-color: #fee2e2; color: #991b1b"
            if value == 1:
                return "background-color: #fef3c7; color: #92400e"
            return "background-color: #dcfce7; color: #166534"

        styled = coverage_df.style.applymap(
            coverage_color, subset=["question_count"]
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)
        chart_data = coverage_df.set_index("competency")[["question_count"]]
        st.bar_chart(chart_data)

    if validation:
        st.subheader("Blueprint validation")
        m1, m2, m3 = st.columns(3)
        m1.metric("Quality indicator", f"{validation.get('quality_score', 0)}/100")
        m2.metric("Weight total", f"{validation.get('total_weight', 0)}%")
        m3.metric(
            "Estimated duration",
            f"{validation.get('estimated_duration_minutes', 0)} min",
        )
        for error in validation.get("errors", []):
            st.error(error)
        for warning in validation.get("warnings", []):
            st.warning(warning)

        if validation.get("duplicate_pairs"):
            st.write("Possible duplicate/similar question pairs")
            st.dataframe(
                validation["duplicate_pairs"],
                use_container_width=True,
                hide_index=True,
            )

        if validation.get("keyword_overload"):
            st.write("Keyword overrepresentation")
            st.dataframe(
                validation["keyword_overload"],
                use_container_width=True,
                hide_index=True,
            )

        if validation.get("bias_issues"):
            st.write("Potential bias issues")
            st.dataframe(
                validation["bias_issues"],
                use_container_width=True,
                hide_index=True,
            )

    # ---------- 5. Evidence Coverage (explainability) ----------

    evidence_cov = result.get("evidence_coverage", [])
    if evidence_cov:
        with st.expander("Evidence → competency → questions mapping (explainability)"):
            st.dataframe(
                [
                    {
                        "JD phrase": item.get("phrase", ""),
                        "Competency": item.get("competency", ""),
                        "Question count": item.get("question_count", 0),
                        "Status": item.get("status", ""),
                    }
                    for item in evidence_cov
                ],
                use_container_width=True,
                hide_index=True,
            )

    # ---------- 6. Generate Questions for Skill Gaps ----------

    st.divider()
    st.header("5. Generate Questions for Skill Gaps")
    st.caption(
        "Generated questions stay as drafts until you review and approve them. "
        "They are not automatically published to Supabase."
    )

    competency_names = [
        item.get("name", "")
        for item in result.get("competencies", [])
        if item.get("name")
    ]

    selected_for_generation = st.multiselect(
        "Choose competencies that need additional questions",
        options=competency_names,
        key="generation_competencies",
    )

    if st.button("Generate draft questions with Gemini", type="secondary"):
        if not selected_for_generation:
            st.warning("Select at least one competency first.")
        else:
            existing_questions = [
                item.get("question", "") for item in result.get("questions", [])
            ] + [
                item.get("question", "")
                for item in st.session_state.get("generated_drafts", [])
            ]
            payload = {
                "job_title": st.session_state.get(
                    "assessment_job_title", result.get("job_title", "")
                ),
                "description": st.session_state.get("assessment_description", ""),
                "competencies": selected_for_generation,
                "existing_questions": existing_questions,
            }
            with st.spinner("Gemini is creating draft questions..."):
                try:
                    generated = call_api("/generate-gap-questions", payload)
                    st.session_state["generated_drafts"] = generated.get(
                        "draft_questions", []
                    )
                    st.success(
                        f"Generated {len(st.session_state['generated_drafts'])} "
                        "draft question(s). Review each below."
                    )
                except Exception as exc:
                    st.error(str(exc))

    drafts = st.session_state.get("generated_drafts", [])
    approved_drafts = []

    if drafts:
        st.subheader("Human review")
        for index, draft in enumerate(drafts):
            with st.expander(
                f"Draft {index + 1}: {draft.get('competency')} · "
                f"{draft.get('difficulty')}",
                expanded=True,
            ):
                if draft.get("possible_duplicate"):
                    st.warning(
                        "Possible duplicate detected. Edit the wording or reject it."
                    )
                st.write(
                    f"**AI rationale:** {draft.get('rationale', 'Not provided')}"
                )
                edited_question = st.text_area(
                    "Question text",
                    value=draft.get("question", ""),
                    key=f"draft_question_{index}",
                    height=110,
                )
                st.write(
                    f"Type: {draft.get('type')} · "
                    f"Difficulty: {draft.get('difficulty')} · "
                    f"Marks: {draft.get('marks')}"
                )
                decision = st.radio(
                    "HR decision",
                    ["Pending", "Approve", "Reject"],
                    horizontal=True,
                    key=f"draft_decision_{index}",
                )
                draft["question"] = edited_question.strip()
                draft["review_status"] = decision.lower()
                if decision == "Approve" and edited_question.strip():
                    approved_drafts.append(draft)

        st.caption(
            f"Approved in this session: {len(approved_drafts)} / {len(drafts)}"
        )

        if st.button("Download final reviewed blueprint JSON", type="primary"):
            final_data = {
                "job_title": result.get("job_title"),
                "job_id": result.get("job_id"),
                "blueprint_id": result.get("blueprint_id"),
                "analysis": result.get("analysis"),
                "competencies": result.get("blueprint"),
                "existing_questions": result.get("questions", []),
                "approved_generated_questions": approved_drafts,
                "validation": result.get("validation", {}),
                "note": (
                    "Generated questions are approved in this Streamlit session; "
                    "they have not been saved/published to Supabase."
                ),
            }
            st.download_button(
                "Download reviewed blueprint",
                data=json.dumps(final_data, indent=2, ensure_ascii=False),
                file_name="reviewed_assessment_blueprint.json",
                mime="application/json",
                key="download_reviewed_blueprint",
            )

    with st.expander("Extracted responsibilities"):
        st.write(result.get("responsibilities", []))