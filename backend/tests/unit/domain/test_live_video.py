import pytest

from argus.domain.live_video import CHANNELS, WEBCAMS, StreamKind, stream


def test_stream_urls_become_players() -> None:
    hls = stream("https://tv-trtworld.medya.trt.com.tr/master.m3u8")
    assert (hls.kind, hls.url) == (StreamKind.HLS, hls.page)
    video = stream("https://www.youtube.com/watch?v=QB5BNdBFujE")
    assert video.url == "https://www.youtube-nocookie.com/embed/QB5BNdBFujE?autoplay=1&mute=1"
    channel = stream("https://www.youtube.com/channel/UCIALMKvObZNtJ6AmdCLP7Lg")
    assert "live_stream?channel=UCIALMKvObZNtJ6AmdCLP7Lg" in channel.url
    assert channel.page.endswith("/live")
    for bad in (
        "http://x.test/a.m3u8",
        "https://www.youtube.com/watch?v=short",
        "https://evil.test",
    ):
        with pytest.raises(ValueError, match="not a stream"):
            stream(bad)


def test_catalog_ids_are_unique_and_every_entry_has_a_stream() -> None:
    for entries in (CHANNELS, WEBCAMS):
        ids = [e.id for e in entries]
        assert len(ids) == len(set(ids))
        assert all(e.streams for e in entries)
    assert not any("rttv.com" in s.url for c in CHANNELS for s in c.streams)
