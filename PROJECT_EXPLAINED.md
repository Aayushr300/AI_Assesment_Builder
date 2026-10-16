# AI Assessment Blueprint Builder — Explained Simply

**Ek line mein:** Job description daalo → 10 seconds mein ready-to-use
assessment blueprint, har decision ke reason ke saath.

---

## 📌 Problem Kya Hai

HR teams ko ek nayi job ke liye assessment banane mein 4–8 ghante lagte hain:

- Job description padho
- Skills identify karo
- Questions dhoondho ya likho
- Difficulty balance karo
- Duplicates aur bias check karo

Yeh process slow hai, biased ho sakta hai, aur often role ke saath
misaligned hota hai.

**Yeh system us poore process ko automate karta hai — par AI ko blindly
trust nahi karta. Har decision explainable hai, aur human final
approval deta hai.**

---

## 🔄 System Kaise Kaam Karta Hai

Chalo ek **real JD** se chalte hain:

> *"We are looking for a Senior Python Developer. You will build REST
> APIs using FastAPI, write SQL queries, implement JWT authentication,
> and debug production issues. Git experience required."*

User "Analyze Job" button dabata hai. Andar 9 steps chalte hain:

---

### Step 1 — JD Ko Padhna (LLM)

**Kaun:** Google Gemini (LLM)  
**File:** `jd_analyzer.py`

Gemini JD ko padhke structured JSON return karta hai:

```json
{
  "responsibilities": ["build REST APIs", "debug production issues"],
  "mandatory_skills": ["Python", "FastAPI", "SQL", "JWT", "Git"],
  "seniority": "senior",
  "tools": ["Git"],
  "evidence_map": [
    {
      "phrase": "build REST APIs using FastAPI",
      "competency": "REST APIs",
      "confidence": 0.95,
      "importance": "high"
    }
  ]
}
```

**Kyun important hai:**
- Just keywords nahi — har skill ke saath **exact JD phrase** aur
  **confidence score**.
- Baad mein HR poochh sakta hai "yeh skill kahan se aayi?" — system
  exact sentence dikha sakta hai.

**Agar Gemini fail ho jaye?**
System automatically next model try karta hai. Ek down ho toh doosra
chalta hai.

---

### Step 2 — Seniority Verify Karna

**Kaun:** Python code  
**File:** `validation.py`

Gemini ne "senior" bola. Title bhi "Senior Python Developer" hai.
Match ✅.

**Agar mismatch ho:**
- Title: "Junior Developer"
- Gemini: "senior"

System **title ko trust karta hai**, LLM ko nahi. Kyunki HR ne title
jaan-boojh kar likha hai.

---

### Step 3 — Skills Ko Local Taxonomy Se Match Karna

**Kaun:** Python code  
**File:** `taxonomy.py`

System ke paas ek **local taxonomy** hai — 6 fixed competencies:

| Gemini ne bola | Taxonomy ka naam |
|---|---|
| Python | Python Programming |
| REST APIs | FastAPI and REST APIs |
| JWT | Authentication and JWT |
| SQL | SQL and Databases |
| Git | Git and GitHub |

Yahan do cheezein hoti hain:

1. **Synonyms mapping** — "Python", "OOP", "python programming" sab
   → "Python Programming"
2. **Duplicate merge** — agar Gemini ne "Python" aur "Python
   Programming" dono diye, ek hi entry banti hai

**Agar Gemini koi aisi skill de jo taxonomy mein nahi hai**
(jaise "Kubernetes") — toh woh `ambiguous_skills` mein aa jaati hai.
HR ko dikhayi jaati hai review ke liye.

---

### Step 4 — Weighted Blueprint Banana

**Kaun:** Python code  
**File:** `blueprint.py`

Ab system decide karta hai: **har competency ka weight kitna hoga?**

**Naive tarika (galat):**
```
5 competencies → sab ko 20% do
```

**Tumhara tarika:**
```
Weight = importance × evidence strength
```

Result:

| Competency | Keywords | Weight |
|---|---|---|
| Python Programming | python, oop, functions | 22.5% |
| FastAPI and REST APIs | fastapi, rest apis | 21.4% |
| Authentication and JWT | jwt | 19.6% |
| SQL and Databases | sql | 19.6% |
| Git and GitHub | git | 16.9% |
| **Total** | | **100%** |

**Difficulty mix bhi adaptive hai:**

| Seniority | Easy | Medium | Hard |
|---|---|---|---|
| Intern | 70% | 25% | 5% |
| Junior | 50% | 40% | 10% |
| Mid | 30% | 50% | 20% |
| Senior | 15% | 50% | 35% |
| Lead | 10% | 40% | 50% |
| Principal | 5% | 35% | 60% |

Same JD agar Senior aur Intern ko diya jaaye, different difficulty
mix milega.

---

### Step 5 — Questions Dhoondhna (RAG) ⭐

**Kaun:** Python + Postgres (pgvector)  
**File:** `embeddings.py`

**Yeh sabse important step hai.**

#### Purana tarika (keyword matching):

```
JD mein "Python" likha → question bank mein dhundo jisme
competency = "Python Programming" → wahi questions return karo
```

**Problem:** JD mein likha ho "write fast microservices" — toh
"FastAPI" keyword match nahi karega. Zero questions milenge.

#### RAG (semantic matching):

```
1. JD ka text → 384 numbers ka vector banao
   "build REST APIs using FastAPI" → [0.12, -0.45, 0.88, ...]

2. Question bank ke saare questions bhi pehle se vectorized hain
   "How would you design a REST API using FastAPI?"
   → [0.11, -0.43, 0.87, ...]

3. Cosine similarity se compare karo
   Similarity = 0.87 → bahut similar ✅

4. Top 20 questions return karo
```

**Real example:**

Query: *"Need Python, FastAPI, SQL, JWT and Git skills. Will build
REST APIs and debug issues."*

Result (similarity se sorted):

```
0.39 | What are the main principles of OOP?
0.37 | How would you design a REST API using FastAPI?
0.30 | Explain how Python decorators work
0.29 | Explain how Git branches help
0.20 | How would you implement JWT authentication?
0.19 | How would you debug an API that returns incorrect data?
0.09 | Explain the difference between SQL JOIN types
```

Query mein "FastAPI" likha tha, aur wahi question #2 pe aaya —
**similarity se, keyword match se nahi**.

**Yeh RAG ka jaadu hai.**

#### Kaise store hota hai:

- Postgres mein `vector(384)` column hai `questions` table mein
- Startup pe saare questions embed hoke save ho jaate hain
- Har request pe query embed hoti hai aur Postgres function
  `match_questions()` call hoti hai

SQL:
```sql
ORDER BY embedding <=> query_embedding LIMIT 20
```

`<=>` = cosine distance operator (pgvector ka).

---

### Step 6 — Quality Checks (System Khud Ko Critique Karta Hai)

**Kaun:** Python code  
**File:** `validation.py`

System apne output ko **khud test karta hai**:

| Check | Trigger |
|---|---|
| Duplicate questions | 82%+ similar pairs |
| Difficulty balance | Easy/medium/hard sab hone chahiye |
| Keyword overload | Word 40%+ questions mein |
| Bias | Age, gender, marital status patterns |
| Coverage | Har competency ke liye kitne questions |
| Difficulty drift | Target mix se kitna door |

**Final Quality Score:**
```
100 - (25 × errors) - (8 × warnings) - (5 × duplicates)
```

Example: **84/100**

**Kyun important hai:**
System apne output ko blind publish nahi karta. Har weak point
surface karta hai.

---

### Step 7 — Explainability Report

**Kaun:** Python code  
**File:** `coverage.py`

Yeh **audit trail** hai. Har JD phrase ke liye:

```json
{
  "phrase": "Need Python, FastAPI, SQL, JWT and Git skills.",
  "raw_competency": "Python",
  "competency": "Python Programming",
  "confidence": 1.0,
  "question_count": 2,
  "questions": [
    "What are the main principles of OOP?",
    "Explain how Python decorators work"
  ],
  "status": "covered"
}
```

Aur ek **coverage heatmap**:

| Competency | Questions | Status |
|---|---|---|
| Python Programming | 2 | ✅ assessed |
| FastAPI and REST APIs | 1 | ⚠️ under_assessed |
| SQL and Databases | 1 | ⚠️ under_assessed |
| Authentication and JWT | 1 | ⚠️ under_assessed |
| Git and GitHub | 1 | ⚠️ under_assessed |

Agar candidate ya HR challenge kare "yeh question kyun aaya?" —
system exact JD phrase dikha sakta hai.

---

### Step 8 — Gap Filling (LLM Drafts)

**Kaun:** Gemini + Python  
**File:** `jd_analyzer.py`

Agar koi competency under_assessed hai (jaisa FastAPI, sirf 1
question), HR "Generate" button dabata hai.

System Gemini se naya question banwata hai:
- Scenario-based
- Job-relevant
- Non-discriminatory
- Duplicate-free

**Lekin auto-publish nahi hota.** HR ko dekhna padta hai, edit karna
padta hai, Approve ya Reject karna padta hai.

AI draft karta hai. **Human decide karta hai.**

---

### Step 9 — Database Mein Save

**Kaun:** Python + Supabase (Postgres)  
**File:** `repository.py`

Yeh data save hota hai:

| Table | Kya store hota hai |
|---|---|
| `job_descriptions` | Original JD + title |
| `competencies` | Master taxonomy list |
| `job_competencies` | Is job ke weights + evidence |
| `assessment_blueprints` | Blueprint header + JSON |
| `questions` | Question text + **embedding vector** |
| `question_competencies` | Question ↔ competency links |
| `blueprint_questions` | Position, marks per blueprint |

Har assessment **auditable** hai. Baad mein
`GET /assessments/{job_id}` se retrieve ho sakta hai.

---

## 🎯 Ek Line Mein Summary (Har Step)

| Step | Kya hota hai | Kaun karta hai |
|---|---|---|
| 1 | JD padhna, structured data banana | Gemini (LLM) |
| 2 | Seniority verify karna | Python |
| 3 | Skills ko taxonomy se match karna | Python |
| 4 | Weights + difficulty mix decide karna | Python |
| 5 | **RAG — semantic question retrieval** | Embeddings + pgvector |
| 6 | Quality checks | Python |
| 7 | Explainability report | Python |
| 8 | Gap questions generate (human review) | Gemini |
| 9 | Database mein save | Supabase |

---

## 🌟 Tumhare Project Ki 5 Unique Cheezein

### 1. Real RAG, Not Fake RAG
Keyword matching nahi. Embeddings + pgvector + cosine similarity.
Yeh genuinely semantic hai.

**Farak:**
- Fake RAG: `if "Python" in jd: return python_questions`
- Real RAG: `embed(jd) → cosine_similarity(question_vectors) → top_k`

### 2. LLM + Deterministic Hybrid
LLM sirf woh karta hai jo LLM achha karta hai (extraction,
generation). Baaki sab Python — weights, validation, coverage.

**Kyun:** LLM hallucinate kar sakta hai. Deterministic code testable
aur repeatable hai.

### 3. Adaptive Blueprint
Same JD, different seniority → different difficulty mix.

Senior: 15/50/35 (easy/medium/hard)  
Intern: 70/25/5

### 4. Self-Critique
System apne output ko check karta hai — duplicates, bias, keyword
overload, difficulty drift. Phir HR ko batata hai.

### 5. Full Explainability
Har decision traceable:
```
JD phrase → competency → weight → question
```

Yeh **audit-ready** hai.

---

## 🎤 30-Second Pitch (Kisi Ko Bhi Sunane Ke Liye)

> "Yeh system job description leta hai, aur 10 seconds mein ek ready
> assessment blueprint banata hai — with weights, difficulty mix,
> aur relevant questions.
>
> Do cheezein isko unique banati hain:
>
> **Ek** — yeh **RAG use karta hai**. Matlab questions semantic
> similarity se milte hain, keyword match se nahi. 'FastAPI' aur
> 'REST APIs' ko same cheez maanta hai.
>
> **Do** — yeh **explainable** hai. Har skill, har weight, har
> question ka **JD phrase se direct connection** hota hai. Aur
> system apne output ko check karta hai — duplicate, bias, coverage
> gaps — aur HR ko batata hai.
>
> AI draft karta hai. HR decide karta hai. Sab kuch audit-ready hai."

---

## 📊 Visual Flow (ASCII)

```
User uploads JD
       │
       ▼
┌──────────────────────┐
│  1. Gemini LLM       │ → structured JSON + evidence map
│  (jd_analyzer.py)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  2. Seniority check  │ → title vs LLM alignment
│  (validation.py)     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  3. Taxonomy match   │ → synonyms, duplicates, ambiguity
│  (taxonomy.py)       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  4. Blueprint        │ → weights + difficulty mix
│  (blueprint.py)      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  5. RAG retrieval    │ → semantic search via pgvector
│  (embeddings.py)     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  6. Quality checks   │ → duplicates, bias, coverage
│  (validation.py)     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  7. Explainability   │ → phrase → competency → question
│  (coverage.py)       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  8. Gap filling      │ → LLM drafts + human review
│  (jd_analyzer.py)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  9. Persist          │ → Supabase (Postgres + pgvector)
│  (repository.py)     │
└──────────────────────┘
```

---

## 🔧 Tech Stack (Ek Nazar Mein)

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | FastAPI |
| LLM | Google Gemini (2.0-flash) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector DB | Supabase Postgres + pgvector |
| PDF parsing | pypdf |

**One database** — koi extra vector DB nahi. Sab Postgres mein.

---

## ✅ Feature Checklist

**Core:**
- [x] JD parsing → skills, responsibilities, seniority
- [x] Taxonomy normalization + duplicate merge
- [x] Weighted blueprint with difficulty mix
- [x] Question tagging
- [x] Gap question generation + human review
- [x] Duplicate + difficulty + keyword checks
- [x] Explainability report

**Innovative:**
- [x] JD Evidence Map with confidence
- [x] Adaptive Blueprint
- [x] Coverage Heatmap
- [x] Semantic tagging (wrong-skill detection)
- [x] **RAG (embeddings + pgvector)**

**Concepts:**
- [x] Prompt engineering
- [x] **RAG with local repositories**
- [x] Embeddings + semantic similarity
- [x] Human-in-the-loop
- [x] Explainability + bias checks

---

## 🧪 Test Karne Ke Liye

Yeh JD paste karo:

```
We are looking for a Senior Python Developer to join our backend
team. You will design and build REST APIs using FastAPI, write
efficient SQL queries for PostgreSQL, implement JWT-based
authentication, and manage code with Git. You will also debug
production issues and mentor juniors.
```

**Expected output:**
- 5 competencies detected
- Weighted blueprint (total = 100%)
- 7 questions retrieved via RAG with similarity scores
- Coverage heatmap with assessed/under_assessed status
- Warnings: difficulty mix, keyword overload
- Quality score ~84/100
- Evidence coverage: every JD phrase traced

---

## 🎯 Bottom Line

Yeh **LLM + RAG + Deterministic Validation** ka hybrid hai.

- **LLM** extraction aur generation ke liye
- **RAG** semantic retrieval ke liye
- **Deterministic code** weighting, validation, explainability ke liye
- **Human** final decision ke liye

**Kuch bhi auto-publish nahi hota. Sab kuch traceable hai. Sab kuch
testable hai.**
