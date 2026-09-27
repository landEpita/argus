"""
Live TV news channels and city webcams: a curated list of public streams.

Each entry lists its streams in order of preference: the broadcaster's own
HLS stream first, then a YouTube video or channel embed. The browser plays
them straight from the broadcaster and moves to the next stream when one
fails. Argus does not check that a stream is live; the player says when one
does not load. Streams refused outside their country (BBC, ZDF) and channels
banned from broadcast in the EU (RT) are left out rather than routed around.

Sources: worldmonitor's live-video list (streams checked on 2026-09-27).
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.geo import GeoPoint
from argus.domain.news import Ownership


class StreamKind(StrEnum):
    HLS = "hls"
    YOUTUBE = "youtube"


class Stream(DomainModel):
    kind: StreamKind
    url: str = Field(description="What the player loads: an .m3u8, or a YouTube embed URL")
    page: str = Field(description="Where to watch it at the source")


class Channel(DomainModel):
    id: str
    name: str
    country: str | None = Field(default=None, description="ISO2 of the owning state or HQ")
    language: str = Field(description="ISO 639-1")
    ownership: Ownership
    streams: tuple[Stream, ...]


class Webcam(DomainModel):
    id: str
    name: str
    position: GeoPoint | None = Field(default=None, description="None for views from orbit")
    streams: tuple[Stream, ...]


_VIDEO_ID = re.compile(r"^[\w-]{11}$")
_CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")


def stream(url: str) -> Stream:
    """A stream from an .m3u8 URL, a YouTube watch URL or a YouTube channel URL."""
    if url.startswith("https://") and ".m3u8" in url:
        return Stream(kind=StreamKind.HLS, url=url, page=url)
    if m := re.fullmatch(r"https://www\.youtube\.com/watch\?v=([\w-]+)", url):
        vid = m.group(1)
        if _VIDEO_ID.match(vid):
            return Stream(
                kind=StreamKind.YOUTUBE,
                url=f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&mute=1",
                page=url,
            )
    if m := re.fullmatch(r"https://www\.youtube\.com/channel/([\w-]+)", url):
        cid = m.group(1)
        if _CHANNEL_ID.match(cid):
            return Stream(
                kind=StreamKind.YOUTUBE,
                url=f"https://www.youtube.com/embed/live_stream?channel={cid}&autoplay=1&mute=1",
                page=f"{url}/live",
            )
    raise ValueError(f"not a stream URL: {url}")


PRIV, PUB, STATE = Ownership.PRIVATE, Ownership.PUBLIC, Ownership.STATE


def _channel(
    id: str, name: str, country: str | None, language: str, ownership: Ownership, *urls: str
) -> Channel:
    return Channel(
        id=id, name=name, country=country, language=language, ownership=ownership,
        streams=tuple(stream(u) for u in urls),
    )  # fmt: skip


def _webcam(id: str, name: str, at: tuple[float, float] | None, *urls: str) -> Webcam:
    position = GeoPoint(lat=at[0], lon=at[1]) if at else None
    return Webcam(id=id, name=name, position=position, streams=tuple(stream(u) for u in urls))


YT = "https://www.youtube.com/watch?v="
YC = "https://www.youtube.com/channel/"

CHANNELS: tuple[Channel, ...] = (
    _channel("bloomberg", "Bloomberg TV", "US", "en", PRIV,
             f"{YT}QB5BNdBFujE", f"{YC}UCIALMKvObZNtJ6AmdCLP7Lg"),
    _channel("sky", "Sky News", "GB", "en", PRIV,
             "https://linear901-oo-hls0-prd-gtm.delivery.skycdp.com/17501/sde-fast-skynews/master.m3u8",
             f"{YT}xDWQ3LkccY8"),
    _channel("dw", "DW News", "DE", "en", PUB,
             "https://dwamdstream103.akamaized.net/hls/live/2015526/dwstream103/master.m3u8",
             f"{YT}LuKwFajn37U", f"{YC}UCknLrEdhRCp1aegoMqRaCZg"),
    _channel("france24", "France 24 English", "FR", "en", PUB,
             "https://amg00106-france24-france24-samsunguk-qvpp8.amagi.tv/playlist/amg00106-france24-france24-samsunguk/playlist.m3u8",
             f"{YT}HvZt-nh9sGg"),
    _channel("france24-fr", "France 24", "FR", "fr", PUB, f"{YT}a47ckXKZjxI"),
    _channel("bfmtv", "BFM TV", "FR", "fr", PRIV,
             "https://live-cdn-stream-euw1.bfmtv.bct.nextradiotv.com/master.m3u8"),
    _channel("euronews", "Euronews", "FR", "en", PRIV, f"{YT}pykpO5kQJ98"),
    _channel("euronews-fr", "Euronews (français)", "FR", "fr", PRIV, f"{YT}NiRIbKwAejk"),
    _channel("cnn", "CNN", "US", "en", PRIV, f"{YT}GotlA1KKWoo"),
    _channel("cbs-news", "CBS News", "US", "en", PRIV,
             "https://cbsn-us.cbsnstream.cbsnews.com/out/v1/55a8648e8f134e82a470f83d562deeca/master.m3u8"),
    _channel("abc-news", "ABC News", "US", "en", PRIV, f"{YC}UCBi2mrWuNuyYy4gbM6fU18Q"),
    _channel("nbc-news", "NBC News", "US", "en", PRIV, f"{YC}UCeY0bbntWzzVIaj2z3QigXg"),
    _channel("fox-news", "Fox News", "US", "en", PRIV,
             "https://247preview.foxnews.com/hls/live/2020027/fncv3preview/primary.m3u8"),
    _channel("newsmax", "Newsmax", "US", "en", PRIV,
             "https://nmxlive.akamaized.net/hls/live/529965/Live_1/index.m3u8", f"{YT}RNNFrG4KbH0"),
    _channel("aljazeera", "Al Jazeera English", "QA", "en", STATE,
             "https://live-hls-apps-aje-fa.getaj.net/AJE/index.m3u8", f"{YT}gCNeDWCI0vo",
             f"{YC}UCNye-wNBqNL5ZzHSJj3l8Bg"),
    _channel("aljazeera-arabic", "Al Jazeera Arabic", "QA", "ar", STATE,
             "https://live-hls-web-aja.getaj.net/AJA/index.m3u8", f"{YT}bNyUyrR0PHo"),
    _channel("alarabiya", "Al Arabiya", "SA", "ar", STATE,
             "https://live.alarabiya.net/alarabiapublish/alarabiya.smil/playlist.m3u8",
             f"{YT}n7eQejkXbnM"),
    _channel("i24-news", "i24NEWS (Hebrew)", "IL", "he", PRIV,
             "https://i24newshebrew-cdn.encoders.immergo.tv/master.m3u8"),
    _channel("iran-intl", "Iran International", "GB", "fa", PRIV,
             "https://live.livetvstream.co.uk/LS-63503-4/index.m3u8", f"{YT}5JDxjsAVaGk"),
    _channel("press-tv", "Press TV", "IR", "en", STATE, "https://live.presstv.co.uk/hls/presstv.m3u8"),
    _channel("trt-world", "TRT World", "TR", "en", STATE, "https://tv-trtworld.medya.trt.com.tr/master.m3u8"),
    _channel("tagesschau24", "tagesschau24", "DE", "de", PUB,
             "https://tagesschau.akamaized.net/hls/live/2020115/tagesschau/tagesschau_1/master.m3u8"),
    _channel("rtve", "RTVE 24h", "ES", "es", PUB,
             "https://rtvelivestream.rtve.es/rtvesec/24h/24h_main_dvr.m3u8"),
    _channel("dw-espanol", "DW Español", "DE", "es", PUB,
             "https://dwamdstream104.akamaized.net/hls/live/2015530/dwstream104/stream04/streamPlaylist.m3u8"),
    _channel("ert-news", "ERT News", "GR", "el", PUB,
             "https://ert-ucdn.broadpeak-aas.com/bpk-tv/ERTNews/default/index.m3u8"),
    _channel("nhk-world", "NHK World", "JP", "en", PUB,
             "https://masterpl.hls.nhkworld.jp/hls/w/live/master.m3u8",
             f"{YC}UCSPEjw8F2nQDtmUKPFNF7_A"),
    _channel("arirang", "Arirang News", "KR", "en", PUB,
             "https://amdlive-ch01-ctnd-com.akamaized.net/arirang_1ch/smil:arirang_1ch.smil/playlist.m3u8"),
    _channel("cgtn", "CGTN", "CN", "en", STATE,
             "https://english-livebkali.cgtn.com/live/encgtn.m3u8", f"{YT}0i7n3r01L2U"),
    _channel("cna", "CNA", "SG", "en", STATE, f"{YT}XWq5kBlakcQ"),
    _channel("wion", "WION", "IN", "en", PRIV, f"{YT}X-7LAkvfA5s"),
    _channel("india-today", "India Today", "IN", "en", PRIV,
             "https://indiatodaylive.akamaized.net/hls/live/2014320/indiatoday/indiatodaylive/playlist.m3u8",
             f"{YT}sYZtOFzM78M"),
    _channel("nasa", "NASA TV", "US", "en", PUB, f"{YT}fO9e9jnhYK8"),
)  # fmt: skip

WEBCAMS: tuple[Webcam, ...] = (
    _webcam("jerusalem", "Jerusalem", (31.778, 35.235), f"{YT}zp6LNSoq000"),
    _webcam("mecca", "Mecca", (21.4225, 39.8262), f"{YT}eC4LfEVxvKg"),
    _webcam("medina", "Medina", (24.4672, 39.6112), f"{YT}naaOMgZbIHQ"),
    _webcam("istanbul", "Istanbul", (41.0082, 28.9784), f"{YT}bbVe5h7X3uw"),
    _webcam("kyiv", "Kyiv and other Ukrainian cities", (50.4501, 30.5234), f"{YT}e2gC37ILQmk"),
    _webcam("paris", "Paris", (48.8584, 2.2945), f"{YT}-xzg3wujOVM"),
    _webcam("london", "London", (51.5007, -0.1246), f"{YT}zMCea32gpmg"),
    _webcam("st-petersburg", "Saint Petersburg", (59.9343, 30.3351), f"{YT}CjtIYbmVfck"),
    _webcam("washington", "Washington, D.C.", (38.8899, -77.0091), f"{YT}oDCAAfOSqvA"),
    _webcam("new-york", "New York", (40.758, -73.9855), f"{YT}JQ_jwk_7OVE", f"{YT}VGnFLdQW39A"),
    _webcam("los-angeles", "Los Angeles", (34.0522, -118.2437), f"{YT}EO_1LWqsCNE"),
    _webcam("miami", "Miami Beach", (25.7907, -80.13), f"{YT}WT69M210Z18", f"{YT}bi7B4EmyHHs"),
    _webcam("taipei", "Taipei", (25.033, 121.5654), f"{YT}z_fY1pj1VBw"),
    _webcam("shanghai", "Shanghai", (31.2304, 121.4737), f"{YT}Z-g8M1QGKbg"),
    _webcam("tokyo", "Tokyo", (35.6595, 139.7005), f"{YT}_k-5U7IeK8g"),
    _webcam("seoul", "Seoul", (37.5665, 126.978), f"{YT}vk5BHoDxXf0"),
    _webcam("sydney", "Sydney", (-33.8568, 151.2153), f"{YT}5uZa3-RMFos"),
    _webcam("starbase", "Starbase, Texas", (25.997, -97.157),
            f"{YT}mhJRzQsLZGg", f"{YT}Jm8wRjD3xVA"),
    _webcam("iss", "Earth from the ISS", None, f"{YT}awQzjn72bI0", f"{YT}M3HKLzjvKPc"),
)  # fmt: skip
