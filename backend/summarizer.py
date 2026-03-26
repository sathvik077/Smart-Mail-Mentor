"""
Email summarization engine.

Three strategies, selected via the SUMMARIZER_MODEL environment variable:

  textrank   (default) — pure Python TextRank, no downloads, ~5ms per email.
  distilbart           — sshleifer/distilbart-cnn-6-6, ~300 MB, ~1-3s per email.
  flan-t5              — google/flan-t5-small, ~300 MB, ~1-2s per email.

The transformer models are loaded once at startup and kept in memory.
If loading fails (model not downloaded, transformers not installed, etc.)
the engine silently falls back to TextRank so the API stays up.
"""
import logging
import os
import re
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)
MODEL_ENV = os.getenv("SUMMARIZER_MODEL", "textrank").lower()


class EmailSummarizer:
    """
    Instantiate once at app startup.  `summarize()` is thread-safe for
    TextRank; transformer pipelines are not thread-safe by default but
    uvicorn's single-worker mode is fine.
    """

    def __init__(self):
        self.model_name = MODEL_ENV
        self._pipe = None
        if MODEL_ENV in ("distilbart", "flan-t5"):
            self._load_transformer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summarize(self, text: str, max_sentences: int = 3) -> str:
        if not text or not text.strip():
            return ""
        text = _clean(text)
        if not text.strip():
            return ""
        if self._pipe:
            return self._transformer_summarize(text)
        return _textrank(text, max_sentences)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_transformer(self) -> None:
        try:
            from transformers import pipeline  # type: ignore

            model_ids = {
                "distilbart": "sshleifer/distilbart-cnn-6-6",
                "flan-t5": "google/flan-t5-small",
            }
            model_id = model_ids[MODEL_ENV]
            logger.info("Loading %s … (first run downloads ~300 MB)", model_id)

            task = "text2text-generation" if MODEL_ENV == "flan-t5" else "summarization"
            kwargs = {"model": model_id, "device": -1}  # -1 = CPU; set 0 for CUDA
            if MODEL_ENV == "flan-t5":
                kwargs["max_new_tokens"] = 128

            self._pipe = pipeline(task, **kwargs)
            logger.info("Model ready: %s", model_id)
        except ImportError:
            logger.warning(
                "transformers is not installed.  Run: pip install torch transformers\n"
                "Falling back to TextRank."
            )
            self.model_name = "textrank"
        except Exception as exc:
            logger.warning("Could not load transformer (%s).  Using TextRank.", exc)
            self.model_name = "textrank"

    def _transformer_summarize(self, text: str) -> str:
        # Cap input so we don't blow the token limit
        chunk = text[:1800]
        try:
            if MODEL_ENV == "flan-t5":
                prompt = f"Summarize this email concisely in 2-3 sentences:\n\n{chunk}"
                out = self._pipe(prompt)[0]["generated_text"]
            else:
                out = self._pipe(
                    chunk,
                    max_length=140,
                    min_length=28,
                    do_sample=False,
                    truncation=True,
                )[0]["summary_text"]
            return out.strip()
        except Exception as exc:
            logger.warning("Transformer inference failed (%s).  Falling back.", exc)
            return _textrank(text, 3)


# ------------------------------------------------------------------
# TextRank (no external model download required)
# ------------------------------------------------------------------

def _textrank(text: str, n: int = 3) -> str:
    """
    Extractive summarization via TextRank.
    Builds a TF-IDF sentence graph, runs PageRank, returns top-n sentences
    in their original order.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
        import networkx as nx  # type: ignore
    except ImportError:
        # Last-resort: just return the first n sentences
        sents = _split_sentences(text)
        return " ".join(sents[:n])

    sents = _split_sentences(text)
    if len(sents) <= n:
        return text

    # Keep only sentences with at least 4 words
    indexed = [(i, s) for i, s in enumerate(sents) if len(s.split()) >= 4]
    if len(indexed) <= n:
        return " ".join(sents[:n])

    idxs, valid = zip(*indexed)

    try:
        vec = TfidfVectorizer(stop_words="english", min_df=1)
        mat = vec.fit_transform(valid)
        sim = cosine_similarity(mat, mat)
        np.fill_diagonal(sim, 0.0)

        g = nx.from_numpy_array(sim)
        scores = nx.pagerank(g, max_iter=300, tol=1e-5)

        top_local = sorted(scores, key=scores.get, reverse=True)[:n]
        top_orig = sorted(idxs[i] for i in top_local)
        return " ".join(sents[i] for i in top_orig)
    except Exception:
        return " ".join(sents[:n])


def _split_sentences(text: str):
    """
    Lightweight sentence splitter — no NLTK dependency.
    Splits on .  !  ?  followed by whitespace + capital letter,
    and on standalone newlines that look like paragraph breaks.
    """
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", text)
    out = []
    for chunk in raw:
        for sub in chunk.split("\n"):
            sub = sub.strip()
            if sub:
                out.append(sub)
    return out or [text]


def _clean(text: str) -> str:
    """Strip URLs, unsubscribe footers, excessive whitespace."""
    text = re.sub(r"https?://\S+", "", text)
    lines = text.splitlines()
    clean = []
    for line in lines:
        stripped = line.strip()
        # Stop at signature dividers
        if stripped in ("--", "---", "___", "——"):
            break
        # Skip footer/legal boilerplate lines
        if re.match(
            r"^(unsubscribe|view in browser|manage preferences|privacy policy"
            r"|terms of (use|service)|©|all rights reserved)",
            stripped.lower(),
        ):
            continue
        if stripped:
            clean.append(stripped)
    return re.sub(r"\s+", " ", " ".join(clean)).strip()
