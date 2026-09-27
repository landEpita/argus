from datetime import UTC, datetime

from argus.domain.search import DocKind, Document, Match, bm25, cosine, fold, fuse, semantic, tokens

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)


def doc(i: str, title: str, text: str = "") -> Document:
    return Document(
        id=i, kind=DocKind.STORY, title=title, text=text, source="BBC", url=f"https://x/{i}",
        at=NOW, unverified=False,
    )  # fmt: skip


DOCS = [
    doc("1", "Houthi attack on a tanker in the Red Sea"),
    doc("2", "Red Sea shipping insurance rises", "Insurers price the Red Sea risk"),
    doc("3", "Élection à Paris : résultats"),
    doc("4", "Ukraine air defence intercepts drones"),
]


def test_words_are_folded_and_filtered() -> None:
    assert fold("Élysée") == "elysee"
    assert tokens("The Red Sea, la mer Rouge!") == ["red", "sea", "mer", "rouge"]


def test_bm25_ranks_by_term_weight_and_frequency() -> None:
    ranked = bm25("red sea", DOCS)
    assert [i for i, _ in ranked] == ["2", "1"]
    assert bm25("election paris", DOCS)[0][0] == "3"  # accents do not matter
    assert bm25("the", DOCS) == []
    assert bm25("volcano", DOCS) == []


def test_cosine_and_semantic_floor() -> None:
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([1, 0], [0, 1]) == 0
    assert cosine([0, 0], [1, 0]) == 0
    ranked = semantic([1, 0], {"a": [0.9, 0.1], "b": [0, 1], "c": [0.5, 0.5]}, floor=0.5)
    assert [i for i, _ in ranked] == ["a", "c"]


def test_fusion_rewards_agreement_and_labels_the_match() -> None:
    documents = {d.id: d for d in DOCS}
    hits = fuse(documents, [("1", 3.0), ("2", 2.0)], [("2", 0.9), ("4", 0.8)], limit=3)
    assert [(h.document.id, h.match) for h in hits] == [
        ("2", Match.BOTH),
        ("1", Match.LEXICAL),
        ("4", Match.SEMANTIC),
    ]
