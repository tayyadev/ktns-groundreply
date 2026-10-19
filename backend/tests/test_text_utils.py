import pytest

from app.text_utils import Evidence, chunk_text, evaluation_passed, should_escalate, vetted_citations, safety_flags


def sources():
    return [
        Evidence(id="K1", document_id="abc", title="Refunds", content="30 days after purchase", similarity=0.87),
        Evidence(id="K2", document_id="def", title="Shipping", content="Delivery takes 4 days", similarity=0.79),
    ]


def test_split_small_and_empty():
    assert chunk_text("") == []
    assert chunk_text("a paragraph") == ["a paragraph"]


def test_split_large_text_retains_sequence():
    data = "".join(str(i % 10) for i in range(3200))
    chunks = chunk_text(data, chunk_size=500, overlap=70)
    assert len(chunks) > 5
    assert chunks[0] == data[:500]
    for first, second in zip(chunks, chunks[1:]):
        assert first[-70:] == second[:70]
    assert chunks[-1] == data[-len(chunks[-1]):]


def test_reject_impossible_overlap():
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=10, overlap=10)


def test_untrusted_or_duplicate_citation_ids_are_removed():
    result = vetted_citations(["K9", "K2", "K2", "K1", "K0"], sources())
    assert [entry["ref"] for entry in result] == ["K2", "K1"]
    assert all("document_id" in entry and "excerpt" in entry for entry in result)


@pytest.mark.parametrize("no_sources,citations,supported,risky,expected", [
    (False, ["K1"], True, False, False),
    (True, [], True, False, True),
    (False, [], True, False, True),
    (False, ["K1"], False, False, True),
    (False, ["K1"], True, True, True),
])
def test_escalation_guards(no_sources, citations, supported, risky, expected):
    assert should_escalate(no_sources, citations, supported, risky) == expected


def test_evaluation_rejects_uncited_and_unexpected_answers():
    assert evaluation_passed("Return within 30 days", ["K1"], "30 days", False, False)
    assert not evaluation_passed("No relevant info", [], "30 days", False, False)
    assert not evaluation_passed("Return within 90 days", ["K1"], "30 days", False, False)
    assert evaluation_passed("Escalate to a human", [], None, True, True)
    assert not evaluation_passed("Possibly return", ["K1"], None, True, False)


def test_deterministic_sensitive_data_escalation():
    assert safety_flags("My SSN is 123-45-6789", "")
    assert safety_flags("Please change bank details", "")
    assert safety_flags("", "Use card number 4111 1111 1111 1111")
    assert not safety_flags("How long is shipping?", "Standard delivery is four days")


def test_eval_requires_positive_grounding_review():
    assert not evaluation_passed("30 days", ["K1"], "30 days", False, False, review_ok=False)
