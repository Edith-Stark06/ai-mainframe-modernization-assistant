"""
Tests for :class:`~app.rag.embeddings.provider.SentenceTransformerProvider`.

Purpose:
    Verify the real, local embedding provider actually produces
    semantically meaningful vectors -- not just "doesn't crash": two
    sentences about the same topic must be closer together than two
    sentences about unrelated topics, which a hash-based fake provider
    could never demonstrate. Downloads and caches the model on first
    run (~80MB, ``all-MiniLM-L6-v2``); marked slow so routine runs of
    the rest of the suite are unaffected.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import math

import pytest

from app.rag.embeddings.provider import SentenceTransformerProvider

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def provider() -> SentenceTransformerProvider:
    return SentenceTransformerProvider()


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


def test_reports_expected_dimension(provider: SentenceTransformerProvider) -> None:
    assert provider.dimension == 384


def test_embed_returns_vector_of_reported_dimension(
    provider: SentenceTransformerProvider,
) -> None:
    vector = provider.embed("MOVE WS-BALANCE TO WS-TOTAL.")
    assert len(vector) == provider.dimension
    assert all(math.isfinite(v) for v in vector)


def test_same_text_is_deterministic(provider: SentenceTransformerProvider) -> None:
    v1 = provider.embed("PERFORM CALCULATE-INTEREST.")
    v2 = provider.embed("PERFORM CALCULATE-INTEREST.")
    assert v1 == v2


def test_embed_batch_matches_individual_embed(
    provider: SentenceTransformerProvider,
) -> None:
    texts = ["MOVE A TO B.", "CALL 'SUBRTN'."]
    batch = provider.embed_batch(texts)
    individual = [provider.embed(t) for t in texts]
    for b, i in zip(batch, individual):
        assert _cosine(b, i) > 0.999


def test_semantically_similar_sentences_are_closer_than_unrelated_ones(
    provider: SentenceTransformerProvider,
) -> None:
    """The actual point of a real embedding provider over a hash-based
    fake one: meaning, not just distinctness."""
    interest_a = provider.embed(
        "Calculate the monthly interest owed on the customer's account balance."
    )
    interest_b = provider.embed(
        "Compute the interest accrued each month against the account balance."
    )
    unrelated = provider.embed(
        "Print the mailing address on the shipping label for the warehouse order."
    )

    sim_related = _cosine(interest_a, interest_b)
    sim_unrelated_a = _cosine(interest_a, unrelated)
    sim_unrelated_b = _cosine(interest_b, unrelated)

    assert sim_related > sim_unrelated_a
    assert sim_related > sim_unrelated_b


def test_empty_batch_returns_empty_list(
    provider: SentenceTransformerProvider,
) -> None:
    assert provider.embed_batch([]) == []


def test_vectors_are_normalized(provider: SentenceTransformerProvider) -> None:
    """normalize_embeddings=True should yield unit vectors, so plain dot
    product (as ChromaDB's default cosine-adjacent distance assumes)
    behaves as expected."""
    vector = provider.embed("STOP RUN.")
    norm = math.sqrt(sum(v * v for v in vector))
    assert abs(norm - 1.0) < 1e-4
