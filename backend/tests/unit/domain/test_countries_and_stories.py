from datetime import UTC, datetime, timedelta

import pytest

from argus.domain.countries import country_index
from argus.domain.news import Article, NewsCategory, Ownership
from argus.domain.news_sources import DEFAULT_SOURCES
from argus.domain.stories import cluster, jaccard, tokens

T0 = datetime(2026, 9, 27, 12, tzinfo=UTC)
SOURCES = {s.id: s for s in DEFAULT_SOURCES}


class TestCountries:
    def test_dataset_is_complete_enough(self) -> None:
        index = country_index()
        assert len(index) >= 240
        france = index.get("fr")
        assert france is not None
        assert france.name == "France"
        assert -90 <= france.centroid.lat <= 90

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Russian strikes hit Kyiv as Ukraine seeks air defence", ("RU", "UA")),
            ("South Sudan and Sudan hold talks", ("SS", "SD")),
            ("US and UK sanction Iranian drone makers", ("US", "GB", "IR")),
            ("Houthis target ship off Yemen", ("YE",)),
            ("Turkey's president meets Chad's leader in Niger", ("TR", "TD", "NE")),
            ("Georgia votes on abortion law", ()),  # too ambiguous with the US state
            ("Bussiness as usual in Brussels", ("BE",)),
            ("", ()),
        ],
    )
    def test_mentions(self, text: str, expected: tuple[str, ...]) -> None:
        assert country_index().mentions(text) == expected

    @pytest.mark.parametrize(
        ("place", "expected"),
        [
            ("124 km SSE of Ugashik, Alaska", "US"),
            ("5 km NW of The Geysers, CA", "US"),
            ("Milan, Lombardia, Italy", "IT"),
            ("London, Ontario, Canada", "CA"),  # the first segment is not trusted
            ("Gaza, Israel (general), Israel", "PS"),  # geocoder files Gaza under Israel
            ("off the coast of Honshu, Japan", "JP"),
            ("somewhere in the ocean", None),
            (None, None),
        ],
    )
    def test_country_of_place(self, place: str | None, expected: str | None) -> None:
        assert country_index().country_of_place(place) == expected

    def test_mentions_need_whole_words(self) -> None:
        assert country_index().mentions("Omani and Omanis, but not Romania's roman ruins") == (
            "OM",
            "RO",
        )


def article(
    i: str, title: str, source: str = "bbc", minutes: int = 0, countries: tuple[str, ...] = ()
) -> Article:
    return Article(
        id=i,
        source_id=source,
        title=title,
        url=f"https://x.test/{i}",
        published_at=T0 + timedelta(minutes=minutes),
        countries=countries,
    )


class TestClustering:
    def test_tokens_drop_stopwords_and_add_countries(self) -> None:
        t = tokens(article("1", "Israel says it will strike back", countries=("IL",)))
        assert t == frozenset({"israel", "strike", "back", "@IL"})
        assert jaccard(frozenset(), t) == 0.0

    def test_same_event_from_different_outlets_forms_one_story(self) -> None:
        stories = cluster(
            [
                article(
                    "1", "Earthquake of magnitude 7.1 strikes off Japan coast", "tass", 0, ("JP",)
                ),
                article(
                    "2", "Magnitude 7.1 earthquake strikes off coast of Japan", "bbc", 10, ("JP",)
                ),
                article("3", "Tsunami warning after Japan earthquake", "dw", 30, ("JP",)),
                article("4", "Chip maker unveils new processor", "the-record", 5),
            ],
            SOURCES,
        )
        assert len(stories) == 2
        quake = max(stories, key=lambda s: len(s.articles))
        # The tsunami warning shares enough vocabulary to join the same story.
        assert [a.id for a in quake.articles] == ["1", "2", "3"]
        # The title comes from the most reliable outlet, not the first to publish.
        assert quake.title == "Magnitude 7.1 earthquake strikes off coast of Japan"
        assert [s.id for s in quake.sources] == ["bbc", "dw", "tass"]
        assert quake.state_media_only is False
        assert quake.countries == ("JP",)
        assert quake.first_seen == T0
        assert quake.last_updated == T0 + timedelta(minutes=30)

    def test_state_media_only_is_flagged(self) -> None:
        [story] = cluster(
            [article("1", "Kremlin denounces new sanctions package", "tass")], SOURCES
        )
        assert story.state_media_only is True
        assert story.sources[0].ownership is Ownership.STATE
        assert story.category is NewsCategory.WORLD

    def test_articles_far_apart_in_time_are_separate(self) -> None:
        stories = cluster(
            [
                article("1", "Parliament votes on budget deal", minutes=0),
                article("2", "Parliament votes on budget deal", "dw", minutes=60 * 48),
            ],
            SOURCES,
        )
        assert len(stories) == 2

    def test_clustering_is_deterministic(self) -> None:
        items = [article(str(i), f"Storm {i % 3} hits coast region", minutes=i) for i in range(12)]
        first = [s.id for s in cluster(items, SOURCES)]
        assert first == [s.id for s in cluster(list(reversed(items)), SOURCES)]

    def test_unknown_sources_are_tolerated(self) -> None:
        [story] = cluster(
            [
                article("1", "Something happened somewhere", "bbc"),
                article("2", "Something happened somewhere", "ghost", 1),
            ],
            SOURCES,
        )
        assert [s.id for s in story.sources] == ["bbc"]
