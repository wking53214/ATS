"""
ats_embeddings.py

Embedding-backed semantic scorer. Drop-in replacement for the TF-IDF
SemanticScorer in ats_statistics.py.

WHY THIS EXISTS
---------------
TF-IDF is lexical. In testing, a genuine resume that wrote "forecast accuracy",
"shrinkage anomalies", and "vendor drift" scored only 19/100 against a job
asking for "forecasting", "anomaly detection", and "vendor management", because
the exact words differed. A human reads those as matches. Embeddings score on
meaning, so they match. This module closes that specific gap.

WHAT IT DOES vs WHAT IT DOES NOT
--------------------------------
  + Per-requirement semantic matching. Each required skill is matched against
    the resume by meaning, producing an interpretable result: "semantically
    matched 4 of 5 requirements", with the per-requirement scores exposed.
  + Pluggable backend. sentence-transformers (local), OpenAI, Voyage, or any
    callable that maps texts -> vectors. Identical interface for all.
  + Optional graceful fallback to TF-IDF when no backend is configured, so the
    same code path runs in environments without model access.

  - It does NOT defeat keyword stuffing on its own. A bare list of the job's
    terms is still semantically near the job, so it would score high. The
    keyword-density veto in ATS.apply_to_job still carries stuffing defense;
    sophisticated AI-generated resumes require AI-text detection or downstream
    verification. Embeddings improve MATCH QUALITY, not fraud resistance. Do not
    conflate the two.

SANDBOX NOTE
------------
Real backends require model or API access that this build environment does not
have (no model registry reachable, no embedding endpoint). The scoring logic and
plumbing in this file are tested with a deterministic MockBackend. The real
backends are structurally complete and activate unchanged when run somewhere
with access; their output QUALITY has not been exercised here, only their wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional, Sequence
import hashlib
import re
import math

import numpy as np

# Reuse the exact result type the rest of the system already consumes, so this is
# a true drop-in: ATS.apply_to_job only reads `.similarity` and `.confidence`.
from ats_statistics import ScoreResult


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

class EmbeddingBackend:
    """Interface: map a list of texts to a list of equal-length float vectors."""
    name: str = "abstract"

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        raise NotImplementedError


class SentenceTransformerBackend(EmbeddingBackend):
    """
    Local model via sentence-transformers. Free, no API key, runs offline once
    the model is cached. Recommended default for self-hosted deployments.

        backend = SentenceTransformerBackend("all-MiniLM-L6-v2")
    """
    name = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None  # lazy: import only when first used

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # lazy import
            self._model = SentenceTransformer(self.model_name)

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        self._ensure()
        vecs = self._model.encode(list(texts), normalize_embeddings=False)
        return [list(map(float, v)) for v in vecs]


class OpenAIEmbeddingBackend(EmbeddingBackend):
    """
    OpenAI embeddings. Reads OPENAI_API_KEY from the environment.

        backend = OpenAIEmbeddingBackend("text-embedding-3-small")
    """
    name = "openai"

    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self._client = None

    def _ensure(self):
        if self._client is None:
            from openai import OpenAI  # lazy import
            self._client = OpenAI()

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        self._ensure()
        resp = self._client.embeddings.create(model=self.model, input=list(texts))
        return [d.embedding for d in resp.data]


class VoyageEmbeddingBackend(EmbeddingBackend):
    """
    Voyage AI embeddings (Anthropic's recommended embedding partner). Reads
    VOYAGE_API_KEY from the environment.

        backend = VoyageEmbeddingBackend("voyage-3")
    """
    name = "voyage"

    def __init__(self, model: str = "voyage-3"):
        self.model = model
        self._client = None

    def _ensure(self):
        if self._client is None:
            import voyageai  # lazy import
            self._client = voyageai.Client()

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        self._ensure()
        result = self._client.embed(list(texts), model=self.model, input_type="document")
        return result.embeddings


class CallableBackend(EmbeddingBackend):
    """Wrap any function texts -> vectors. Useful for custom or internal models."""
    name = "callable"

    def __init__(self, fn: Callable[[Sequence[str]], List[List[float]]], name: str = "callable"):
        self.fn = fn
        self.name = name

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return self.fn(texts)


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

@dataclass
class RequirementMatch:
    requirement: str
    best_similarity: float
    matched: bool
    best_evidence: str  # the resume chunk that best matched this requirement


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def _split_chunks(text: str) -> List[str]:
    """Sentence-ish chunks, dependency-free. Falls back to the whole text."""
    parts = re.split(r"(?<=[.!?;\n])\s+", text.strip())
    chunks = [p.strip() for p in parts if p.strip()]
    return chunks if chunks else [text.strip()]


class EmbeddingScorer:
    """
    Semantic resume-to-job scorer using an embedding backend.

    Per-requirement matching: each required skill is embedded and compared to the
    most similar chunk of the resume. A requirement counts as matched when its
    best chunk similarity clears `match_threshold`. The overall similarity is the
    mean of per-requirement best similarities, which is what `.similarity` returns
    for downstream decision logic.

    Args
    ----
    backend:           an EmbeddingBackend. If None and fallback_to_tfidf is True,
                       the scorer transparently uses the TF-IDF SemanticScorer and
                       marks every result note accordingly.
    match_threshold:   per-requirement cosine cutoff to count a requirement matched.
    decision_threshold:overall-similarity band center used only to set the low/high
                       confidence flag for boundary cases.
    boundary_band:     +/- window around decision_threshold flagged low-confidence.
    fallback_to_tfidf: if True, run without a backend by delegating to TF-IDF.
    """

    def __init__(
        self,
        backend: Optional[EmbeddingBackend] = None,
        match_threshold: float = 0.5,
        decision_threshold: float = 0.5,
        boundary_band: float = 0.07,
        fallback_to_tfidf: bool = True,
    ):
        self.backend = backend
        self.match_threshold = match_threshold
        self.decision_threshold = decision_threshold
        self.boundary_band = boundary_band
        self.fallback_to_tfidf = fallback_to_tfidf
        self._cache: Dict[str, List[float]] = {}
        self._tfidf = None  # lazy

        if backend is None and not fallback_to_tfidf:
            raise ValueError(
                "No embedding backend configured and fallback disabled. "
                "Pass a backend (SentenceTransformer/OpenAI/Voyage/Callable) "
                "or set fallback_to_tfidf=True."
            )

    # -- embedding with caching ------------------------------------------------
    def _embed(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[Optional[List[float]]] = [None] * len(texts)
        to_compute, idx_map = [], []
        for i, t in enumerate(texts):
            key = hashlib.sha256(t.encode("utf-8")).hexdigest()
            if key in self._cache:
                out[i] = self._cache[key]
            else:
                to_compute.append(t)
                idx_map.append((i, key))
        if to_compute:
            vecs = self.backend.embed(to_compute)
            for (i, key), v in zip(idx_map, vecs):
                self._cache[key] = v
                out[i] = v
        return [v for v in out]  # type: ignore

    # -- public API ------------------------------------------------------------
    def score(self, resume_text: str, job_keywords: List[str], job_description: str = "") -> ScoreResult:
        detail = self.score_detailed(resume_text, job_keywords, job_description)
        matches: List[RequirementMatch] = detail["matches"]
        matched_terms = [m.requirement for m in matches if m.matched]
        missing_terms = [m.requirement for m in matches if not m.matched]
        sim = detail["overall_similarity"]
        near = abs(sim - self.decision_threshold) <= self.boundary_band
        confidence = "low" if near else "high"

        return ScoreResult(
            similarity=round(sim, 4),
            score_0_100=round(min(1.0, max(0.0, sim)) * 100, 1),
            matched_terms=matched_terms,
            missing_terms=missing_terms,
            confidence=confidence,
            note=detail["note"],
        )

    def score_detailed(self, resume_text: str, job_keywords: List[str], job_description: str = "") -> Dict[str, Any]:
        assert isinstance(resume_text, str) and resume_text.strip(), "resume_text required"
        assert job_keywords, "job_keywords required"

        # Fallback path: no backend -> lexical TF-IDF, clearly labelled.
        if self.backend is None:
            if self._tfidf is None:
                from ats_statistics import SemanticScorer
                self._tfidf = SemanticScorer(decision_threshold=0.2)
            r = self._tfidf.score(resume_text, job_keywords, job_description)
            fake_matches = [
                RequirementMatch(kw, r.similarity, kw in r.matched_terms, "")
                for kw in job_keywords
            ]
            return {
                "overall_similarity": r.similarity,
                "matches": fake_matches,
                "backend": "tfidf-fallback",
                "note": "NO EMBEDDING BACKEND: lexical TF-IDF fallback in use. "
                        "Configure a backend for semantic matching.",
            }

        # Embedding path.
        chunks = _split_chunks(resume_text)
        # Embed requirements and resume chunks together (one backend round-trip).
        reqs = list(job_keywords)
        all_texts = reqs + chunks
        vecs = self._embed(all_texts)
        req_vecs = vecs[: len(reqs)]
        chunk_vecs = vecs[len(reqs):]

        matches: List[RequirementMatch] = []
        for req, rv in zip(reqs, req_vecs):
            best_sim, best_chunk = -1.0, ""
            for ch, cv in zip(chunks, chunk_vecs):
                s = _cosine(rv, cv)
                if s > best_sim:
                    best_sim, best_chunk = s, ch
            matches.append(
                RequirementMatch(
                    requirement=req,
                    best_similarity=round(best_sim, 4),
                    matched=best_sim >= self.match_threshold,
                    best_evidence=best_chunk,
                )
            )

        overall = sum(m.best_similarity for m in matches) / len(matches)
        n_matched = sum(1 for m in matches if m.matched)
        return {
            "overall_similarity": round(overall, 4),
            "matches": matches,
            "backend": self.backend.name,
            "note": f"Semantic match ({self.backend.name}): "
                    f"{n_matched}/{len(matches)} requirements >= {self.match_threshold}.",
        }


# ---------------------------------------------------------------------------
# Tests (deterministic mock backend - exercises logic, not model quality)
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    # A controlled semantic space so synonyms share direction. This verifies the
    # per-requirement matching LOGIC. It is a stand-in for a real model, not proof
    # of real-world embedding quality.
    _CONCEPTS = {
        # forecasting cluster
        "forecast": [1, 0, 0, 0], "forecasting": [1, 0, 0, 0], "accuracy": [0.9, 0.1, 0, 0],
        "capacity": [0.8, 0.2, 0, 0], "planning": [0.8, 0.1, 0, 0],
        # anomaly cluster
        "anomaly": [0, 1, 0, 0], "anomalies": [0, 1, 0, 0], "shrinkage": [0, 0.9, 0.1, 0],
        "outlier": [0, 0.9, 0, 0], "detection": [0.1, 0.9, 0, 0],
        # vendor cluster
        "vendor": [0, 0, 1, 0], "drift": [0, 0, 0.9, 0.1], "management": [0, 0, 0.85, 0.15],
        # sql/data cluster
        "sql": [0, 0, 0, 1], "queries": [0, 0, 0.1, 0.9], "audited": [0, 0.2, 0, 0.8],
        "data": [0, 0, 0, 0.9],
    }

    def _mock_embed(texts):
        out = []
        for t in texts:
            words = re.findall(r"[a-z]+", t.lower())
            vs = [_CONCEPTS.get(w) for w in words if w in _CONCEPTS]
            if vs:
                v = np.mean([np.asarray(x, dtype=float) for x in vs], axis=0)
            else:
                # deterministic small vector for unknown text
                h = int(hashlib.sha256(t.encode()).hexdigest(), 16)
                rng = np.random.default_rng(h % (2**32))
                v = rng.normal(0, 0.01, size=4)
            out.append(list(map(float, v)))
        return out

    mock = CallableBackend(_mock_embed, name="mock-concepts")
    scorer = EmbeddingScorer(backend=mock, match_threshold=0.6)

    print("=" * 70)
    print("EMBEDDING SCORER - LOGIC TEST (deterministic mock backend)")
    print("=" * 70)

    job_kw = ["forecasting", "anomaly detection", "vendor management", "SQL"]
    job_desc = "Workforce role: forecasting, anomaly detection, vendor management, SQL."

    # The genuine resume uses DIFFERENT words than the requirements - the exact
    # case TF-IDF failed on. Semantic matching should still connect them.
    genuine = (
        "Improved forecast accuracy across centers. "
        "Investigated shrinkage outliers in the data. "
        "Managed vendor drift and ran SQL queries to audit performance."
    )
    detail = scorer.score_detailed(genuine, job_kw, job_desc)
    print(f"\nGenuine resume (synonyms, not exact terms):  backend={detail['backend']}")
    for m in detail["matches"]:
        flag = "MATCH" if m.matched else "miss "
        print(f"  [{flag}] {m.requirement:20s} sim={m.best_similarity:.2f}  <- \"{m.best_evidence[:48]}\"")
    print(f"  overall similarity = {detail['overall_similarity']:.3f}")

    res = scorer.score(genuine, job_kw, job_desc)
    print(f"  ScoreResult: similarity={res.similarity} score={res.score_0_100}/100 "
          f"matched={res.matched_terms}")

    # Compare against TF-IDF fallback on the SAME input to show the difference the
    # embedding path is meant to make. (Fallback runs for real here.)
    print("\n" + "-" * 70)
    print("Same resume through TF-IDF fallback (no backend):")
    tfidf_scorer = EmbeddingScorer(backend=None, fallback_to_tfidf=True)
    tf = tfidf_scorer.score(genuine, job_kw, job_desc)
    print(f"  similarity={tf.similarity}  matched_terms={tf.matched_terms}")
    print(f"  note: {tf.note}")
    print("\n  -> The mock embedding path connects forecast/forecasting, shrinkage/anomaly,")
    print("     drift/management as meaning-matches; exact-string scoring does not.")
    print("     (Mock proves the LOGIC; a real backend supplies real meaning.)")

    # Cache check
    print("\n" + "-" * 70)
    before = len(scorer._cache)
    scorer.score_detailed(genuine, job_kw, job_desc)  # repeat
    print(f"Cache entries after repeat call (no growth = caching works): {len(scorer._cache)} (was {before})")
