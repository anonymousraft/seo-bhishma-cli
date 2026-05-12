"""Core URL redirect mapping logic using NLP and TF-IDF similarity. No CLI dependencies."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import numpy as np
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from seo_bhishma.core._http import DEFAULT_TIMEOUT, requests_retry_session
from seo_bhishma.models.common import ProgressCallback
from seo_bhishma.models.redirection_genius import UrlMappingResult

logger = logging.getLogger(__name__)

_nlp_cache: dict[str, object] = {}
_nlp_lock = threading.Lock()


def _get_nlp(model_name: str = "en_core_web_sm"):
    """Lazy-load and cache a spaCy NLP model. Thread-safe."""
    cached = _nlp_cache.get(model_name)
    if cached is not None:
        return cached

    with _nlp_lock:
        cached = _nlp_cache.get(model_name)
        if cached is not None:
            return cached

        import spacy
        from spacy.cli import download

        try:
            nlp = spacy.load(model_name)
        except OSError:
            logger.info("Downloading spaCy model '%s'...", model_name)
            download(model_name)
            nlp = spacy.load(model_name)

        _nlp_cache[model_name] = nlp
        return nlp


def extract_slug(url: str) -> str:
    """Extract the path component (slug) from a URL."""
    return urlparse(url).path


def analyze_slug(slug: str, spacy_model: str = "en_core_web_sm") -> list[str]:
    """Analyze a URL slug using spaCy NLP to extract lemmatized tokens.

    Args:
        slug: URL path slug (e.g., "/my-blog-post").
        spacy_model: spaCy model name.

    Returns:
        List of lemmatized, non-stop, non-punct tokens.
    """
    nlp = _get_nlp(spacy_model)
    doc = nlp(slug.replace("-", " "))
    return [token.lemma_ for token in doc if not token.is_stop and not token.is_punct]


def tfidf_similarity(source_slugs: list[str], dest_slugs: list[str]) -> np.ndarray:
    """Compute TF-IDF cosine similarity between source and destination slug sets.

    Args:
        source_slugs: Lemmatized source URL slugs.
        dest_slugs: Lemmatized destination URL slugs.

    Returns:
        2D numpy array of shape (len(source), len(dest)) with similarity scores.
    """
    vectorizer = TfidfVectorizer()
    all_texts = source_slugs + dest_slugs
    vectors = vectorizer.fit_transform(all_texts).toarray()
    source_vectors = vectors[: len(source_slugs)]
    dest_vectors = vectors[len(source_slugs) :]
    return cosine_similarity(source_vectors, dest_vectors)


def _process_single_mapping(
    i: int,
    source_url: str,
    dest_urls: list[str],
    tfidf_scores: np.ndarray,
    use_web_content: bool,
    rate_limit: float,
    spacy_model: str,
) -> UrlMappingResult:
    """Map a single source URL to its best destination match."""
    try:
        best_idx = int(np.argmax(tfidf_scores))
        best_score = float(tfidf_scores[best_idx])
        remark = ""

        if use_web_content and best_score < 0.6:
            try:
                import time

                session = requests_retry_session()
                time.sleep(rate_limit)
                src_resp = session.get(source_url, timeout=DEFAULT_TIMEOUT)
                src_resp.raise_for_status()
                src_resp.encoding = src_resp.encoding or src_resp.apparent_encoding
                time.sleep(rate_limit)
                dst_resp = session.get(dest_urls[best_idx], timeout=DEFAULT_TIMEOUT)
                dst_resp.raise_for_status()
                dst_resp.encoding = dst_resp.encoding or dst_resp.apparent_encoding

                src_text = BeautifulSoup(src_resp.text, "html.parser").get_text(" ", strip=True)
                dst_text = BeautifulSoup(dst_resp.text, "html.parser").get_text(" ", strip=True)

                nlp = _get_nlp(spacy_model)
                src_doc = nlp(src_text[:10000])
                dst_doc = nlp(dst_text[:10000])
                best_score = float(
                    cosine_similarity([src_doc.vector], [dst_doc.vector])[0][0]
                )
                remark = "Check manually" if best_score < 0.6 else ""
            except Exception as exc:
                logger.debug("Content fetch for %s failed: %s", source_url, exc)
                remark = "Error"
        else:
            remark = "Check manually" if best_score < 0.6 else ""

        return UrlMappingResult(
            source=source_url,
            destination=dest_urls[best_idx],
            confidence_score=best_score,
            remark=remark,
        )
    except Exception as e:
        logger.error("Error mapping %s: %s", source_url, e)
        return UrlMappingResult(
            source=source_url,
            destination="",
            confidence_score=0.0,
            remark="Error",
        )


def map_urls(
    source_urls: list[str],
    dest_urls: list[str],
    use_web_content: bool = False,
    rate_limit: float = 0,
    max_workers: int = 10,
    spacy_model: str = "en_core_web_sm",
    on_progress: ProgressCallback | None = None,
) -> list[UrlMappingResult]:
    """Map source URLs to best-matching destination URLs using NLP similarity.

    Uses TF-IDF on URL slugs, with optional web content comparison for low-confidence matches.

    Args:
        source_urls: URLs that need redirects.
        dest_urls: Candidate destination URLs.
        use_web_content: If True, fetch page content for low-confidence matches.
        rate_limit: Delay in seconds between web content requests.
        max_workers: Thread pool size.
        spacy_model: spaCy model for NLP processing.
        on_progress: Optional progress callback.

    Returns:
        List of UrlMappingResult in same order as source_urls.
    """
    # Compute slug similarities
    source_slugs = [extract_slug(url) for url in source_urls]
    dest_slugs = [extract_slug(url) for url in dest_urls]

    source_lemmas = [" ".join(analyze_slug(s, spacy_model)) for s in source_slugs]
    dest_lemmas = [" ".join(analyze_slug(s, spacy_model)) for s in dest_slugs]

    sim_matrix = tfidf_similarity(source_lemmas, dest_lemmas)

    # Map URLs in parallel
    results: list[UrlMappingResult | None] = [None] * len(source_urls)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                _process_single_mapping,
                i,
                source_urls[i],
                dest_urls,
                sim_matrix[i],
                use_web_content,
                rate_limit,
                spacy_model,
            ): i
            for i in range(len(source_urls))
        }
        completed = 0
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()
            completed += 1
            if on_progress:
                on_progress(completed, len(source_urls))

    return results  # type: ignore[return-value]
