from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"
PLAYER = ROOT / "frontend" / "src" / "screens" / "podcast" / "PodcastPlayerScreen.tsx"


def test_podcast_player_is_feature_owned_and_app_route_is_preserved():
    app = APP.read_text(encoding="utf-8")
    player = PLAYER.read_text(encoding="utf-8")

    assert "import PodcastPlayerScreen from './screens/podcast/PodcastPlayerScreen'" in app
    assert "function PodcastPlayerScreen(" not in app
    assert ">Speed</span>" not in app
    assert "// ─── PODCAST PLAYER" not in app
    assert "export default function PodcastPlayerScreen(" in player
    assert "case 'podcast-player':" in app
    assert "'podcast-player'" in app[app.index("const noNav"):app.index("const darkHomeIndicator")]


def test_player_keeps_audio_lifecycle_and_study_time_contracts():
    player = PLAYER.read_text(encoding="utf-8")

    for marker in (
        "prepza-podcast-position:",
        "prepza-open-material",
        "/study-time/heartbeat",
        "setInterval(ping, 20000)",
        "navigator.mediaSession",
        "seekbackward",
        "seekforward",
        "playbackRate = speed",
        "cacheReadyPodcastOffline(activeDocumentId, selectedPodcastMaterialId, podcastAudioPath",
        "getCachedPodcastAudio(podcastAudioPath)",
    ):
        assert marker in player


def test_player_external_dependencies_are_explicit_props():
    app = APP.read_text(encoding="utf-8")
    player = PLAYER.read_text(encoding="utf-8")

    for prop in (
        "generationRequest={generationRequest}",
        "cacheReadyPodcastOffline={cachePodcastReadyOffline}",
        "getCachedPodcastAudio={getCachedPodcastAudio}",
        "TopBar={TopBar}",
        "GenerationError={GenerationError}",
        "renderSponsoredOpportunities={campaigns =>",
    ):
        assert prop in app
    for prop in (
        "generationRequest:",
        "cacheReadyPodcastOffline:",
        "getCachedPodcastAudio:",
        "TopBar:",
        "GenerationError:",
        "renderSponsoredOpportunities:",
    ):
        assert prop in player
