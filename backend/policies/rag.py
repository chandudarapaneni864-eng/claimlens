"""Retrieval over the policy knowledge base.

Default backend is TF-IDF (scikit-learn), which needs no downloads and works offline.
Set USE_SENTENCE_TRANSFORMERS=1 (and install sentence-transformers) for semantic embeddings.
Embeddings are cached in PolicyChunk.embedding so they are computed once per chunk.
"""
import logging

import numpy as np
from django.conf import settings

from .models import PolicyChunk

log = logging.getLogger(__name__)
_model = None
_model_failed = False


def _embedder():
    global _model, _model_failed
    if not settings.CLAIMS["USE_SENTENCE_TRANSFORMERS"] or _model_failed:
        return None
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as exc:  # pragma: no cover - optional dependency
            log.warning("sentence-transformers unavailable, falling back to TF-IDF: %s", exc)
            _model_failed = True
            return None
    return _model


def _rank_tfidf(query, texts):
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
    matrix = vectorizer.fit_transform(texts + [query])
    doc_vectors, query_vector = matrix[:-1], matrix[-1]
    return (doc_vectors @ query_vector.T).toarray().ravel()


def _rank_embeddings(model, query, chunks):
    missing = [c for c in chunks if not c.embedding]
    if missing:
        vectors = model.encode([c.text for c in missing], normalize_embeddings=True)
        for chunk, vec in zip(missing, vectors):
            chunk.embedding = vec.tolist()
        PolicyChunk.objects.bulk_update(missing, ["embedding"])
    doc = np.array([c.embedding for c in chunks])
    q = model.encode([query], normalize_embeddings=True)[0]
    return doc @ q


def search(query, policy_ids=None, top_k=5):
    chunks = PolicyChunk.objects.select_related("policy").filter(policy__is_active=True)
    if policy_ids is not None:
        chunks = chunks.filter(policy_id__in=list(policy_ids))
    chunks = list(chunks)
    if not chunks or not query.strip():
        return []

    model = _embedder()
    if model is not None:
        scores = _rank_embeddings(model, query, chunks)
        method = "embeddings"
    else:
        scores = _rank_tfidf(query, [c.text for c in chunks])
        method = "tfidf"

    order = np.argsort(-scores)[:top_k]
    results = []
    for idx in order:
        chunk = chunks[int(idx)]
        results.append(
            {
                "chunk_id": chunk.id,
                "policy_id": chunk.policy_id,
                "policy_code": chunk.policy.code,
                "policy_title": chunk.policy.title,
                "version": chunk.policy.version,
                "text": chunk.text,
                "score": round(float(scores[idx]), 4),
                "method": method,
            }
        )
    return results


def claim_query(claim):
    parts = [
        f"{claim.get_category_display()} expense reimbursement",
        claim.title or "",
        claim.description or "",
        f"city {claim.city}" if claim.city else "",
        f"grade {claim.employee.grade}",
        f"department {claim.employee.department}",
        "limit eligibility required documents approval submission",
    ]
    return " ".join(p for p in parts if p)
