# ClaimLens: Intelligent Employee Claim Verification and Settlement System

Employees submit expense claims with bills. The system reads the documents, finds the policy
version that applies, checks limits, required documents, mismatches, conflicts and duplicates,
explains every finding with policy evidence, routes the claim to the right approvers, and tracks
payment to settlement.

**Stack:** React 18 + Vite (plain CSS) · Django 5 + Django REST Framework · MySQL · local `media/` storage

---

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.10 – 3.13 | `python --version` |
| Node.js | 18 or newer | `node --version` |
| MySQL | 8.x (MariaDB 10.5+ also works) | `mysql --version` |

## 2. Create the MySQL database

Open the MySQL shell (`mysql -u root -p`) and run:

```sql
CREATE DATABASE claimlens CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'claimlens'@'localhost' IDENTIFIED BY 'claimlens123';
GRANT ALL PRIVILEGES ON claimlens.* TO 'claimlens'@'localhost';
FLUSH PRIVILEGES;
```

(You can use `root` instead; just put its password in `.env`.)

## 3. Backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate      macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# Windows: copy .env.example .env     macOS/Linux: cp .env.example .env
# then edit .env -> DB_USER, DB_PASSWORD

python manage.py migrate
python manage.py seed_demo          # demo users, policies, rules, claims, sample PDFs
python manage.py createsuperuser    # optional, for /admin
python manage.py runserver
```

API: http://127.0.0.1:8000/api/  ·  Django admin: http://127.0.0.1:8000/admin/

`python manage.py seed_demo --reset` wipes and rebuilds all demo data.

## 4. Frontend

```bash
cd frontend
npm install
# Windows: copy .env.example .env     macOS/Linux: cp .env.example .env
npm run dev
```

Open http://localhost:5173

## 5. Demo accounts (password `Pass@123`)

| Username | Role | Use it to |
|---|---|---|
| `ananya` | Employee (L2, Engineering) | Submit claims, fix claims sent back |
| `karthik` | Employee (L1, Engineering) | Has a duplicate-invoice claim |
| `sneha` | Employee (L2, Sales) | Medical claim waiting for a prescription |
| `ravi.manager` | Manager | First approver for Ananya and Karthik |
| `vikram.manager` | Manager | First approver for Sneha |
| `arjun.head` | Department head | Extra level for high-value / high-risk claims |
| `meera.hr` | HR | Medical claims and policy conflicts |
| `priya.finance` | Finance | Final check, payments, analytics |
| `admin` | Administrator | Policies, approval rules, people, everything |

### A 5-minute demo script

1. **ravi.manager** → Approvals → *Hotel stay for client workshop in Mumbai*. The verification report shows an
   amount mismatch (₹13,500 typed vs ₹12,992 on the invoice), a per-night limit violation with the policy clause
   quoted, and an HR-vs-Finance policy conflict. Approve ₹12,000.
2. Same queue → *Hotel in Mumbai* by Karthik: duplicate invoice, identical file, name on invoice is Ananya.
   Risk 100, "Likely reject", routed through four levels. Reject it with a reason.
3. **meera.hr** → approve the Mumbai hotel (HR level added because of the conflict).
4. **priya.finance** → approve → Payments → initiate → mark paid with a reference number.
5. **ananya** → New claim → Food, ₹640, date and vendor from `sample_documents/README.txt`, upload
   `try_it_food_bill.pdf` as a Bill. Watch the policy panel tick off documents, then submit. Try ₹1,500 to see a
   violation and mismatch.
6. **admin** → Policies → *Ask the policies* (the RAG retrieval on its own) and *Conflicts*.
   Approval levels → add a rule, e.g. "Amount ≥ 5000 adds HR".

---

## 6. How verification works

```
upload ─► extraction.py ─► fields (amount, invoice no., date, vendor, name, txn id, check-in/out)
                │             pdfplumber text  →  Tesseract OCR (optional)  →  regex rules  →  Gemini (optional)
submit ─► engine.py
          ├─ applicability.py  which policy version applies (category, grade, department, expense date)
          ├─ rag.py            retrieve the relevant policy passages (TF-IDF, or sentence embeddings)
          ├─ checks.py         basics · mismatches · limits/deadlines/pre-approval · required documents
          │                    · policy conflicts · outdated versions · duplicates
          ├─ explain.py        risk score, recommendation, plain-language summary
          └─ routing.py        approval chain from configurable RoutingRule rows
```

Design choice worth defending in a viva: **the LLM never decides**. Limits, dates and required documents are
deterministic Python so results are repeatable and auditable. Retrieval supplies the exact policy wording as
evidence; the optional LLM only extracts fields and writes the summary. A human always approves.

| Requirement | Where |
|---|---|
| Claim submission, document upload | `claims/views.py` (ClaimViewSet, `documents` action), `ClaimForm.jsx` |
| OCR / NLP extraction | `claims/verification/extraction.py` |
| Claim vs document validation, cross-document mismatch | `checks.check_mismatches` |
| Policy knowledge base | `policies/models.py`, chunked by `policies/chunking.py` |
| RAG retrieval | `policies/rag.py` |
| Applicable policy version | `policies/applicability.applicable_policies` |
| Missing documents | `checks.check_policies` (required docs + pre-approval) |
| Policy conflicts | `applicability.detect_conflicts`, `knowledge_base_conflicts` |
| Violations | `checks.check_policies` (limits per claim/day/night/month, deadlines) |
| Duplicates | `checks.check_duplicates` (invoice no., SHA-256, perceptual hash, text similarity, amount+date+vendor) |
| Explainable verification | `Finding.evidence` + `policy_excerpt`, receipt panel in `ClaimDetail.jsx` |
| Dynamic verification level | `verification/routing.py` + `RoutingRule` (Approval levels page) |
| Human-in-the-loop | `services.act` (approve / reject / request correction / request documents) |
| Audit trail | `ClaimEvent`, written by `services.log` on every action |
| Employee tracking | Pipeline, approval route and activity on the claim page |
| Payment + delay tracking | `Payment` model, `services.initiate_payment` / `complete_payment`, `PAYMENT_PERIOD_DAYS` |
| Analytics dashboard | `AnalyticsView`, `Analytics.jsx` |

## 7. Optional upgrades

**OCR for photos and scanned PDFs.** Text PDFs work without it.
Install Tesseract (Windows: the UB Mannheim installer; macOS: `brew install tesseract`; Ubuntu:
`sudo apt install tesseract-ocr`) and on Windows set `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe` in `.env`.

**Gemini.** Put a key from Google AI Studio in `GEMINI_API_KEY`. Extraction gets smarter on messy bills and the
summary becomes an LLM-written paragraph. Without a key everything still works.

**Semantic retrieval.** `pip install sentence-transformers`, set `USE_SENTENCE_TRANSFORMERS=1`. Embeddings are
cached per policy passage in MySQL (JSON column), so they are computed once.

## 8. API overview

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/login/` | JWT login, returns user |
| GET | `/api/dashboard/` | Personal summary |
| GET/POST | `/api/claims/?scope=mine\|team\|all` | List / create |
| GET/PATCH/DELETE | `/api/claims/{id}/` | Detail / edit draft / delete draft |
| POST | `/api/claims/{id}/documents/` | Upload (multipart: `file`, `doc_type`) |
| POST | `/api/claims/{id}/submit/` | Verify and route |
| POST | `/api/claims/{id}/decide/` | `{action, comment, approved_amount}` |
| POST | `/api/claims/{id}/reverify/` | Re-run checks (HR/Finance/Admin) |
| POST | `/api/claims/{id}/payment/initiate/` · `/payment/complete/` | Settlement |
| GET | `/api/approvals/` · `?view=history` | Approver queue |
| GET | `/api/payments/` | Finance list |
| GET | `/api/analytics/` | Management dashboard |
| CRUD | `/api/policies/`, `/api/routing-rules/`, `/api/auth/users/` | Admin data |
| GET | `/api/policies/search/?q=` · `/applicable/` · `/conflicts/` | RAG playground, live policy panel, conflict scan |

## 9. Notes and limits

- Verification runs synchronously on submit (1–2 s per claim). For heavy OCR at scale, move
  `verify_claim` into a Celery task.
- Uploaded files are served by Django only while `DEBUG=1`. In production serve `media/` through
  your web server behind authentication.
- Text-based PDFs are read directly. Images need Tesseract (see above).

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `Access denied for user` | Wrong `DB_USER` / `DB_PASSWORD` in `backend/.env` |
| `Unknown database 'claimlens'` | Run the SQL in step 2 |
| `cryptography package is required` | `pip install cryptography` (MySQL 8 auth) |
| Frontend says it can't reach the server | Django not running, or `VITE_API_URL` in `frontend/.env` is wrong |
| CORS error in the browser console | Add your frontend URL to `CORS_ALLOWED_ORIGINS` in `backend/.env` |
| Photo uploads say "couldn't read" | Install Tesseract (section 7) |
| Want a clean slate | `python manage.py seed_demo --reset` |
