"""Source guards that prevent incomplete or substituted Rubarata videos."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import spotify_video_source as source


class SpotifySourceGuards(unittest.TestCase):
    def test_segments_cover_full_story_including_tiny_final_tail(self):
        for duration in (168.874, 180.001, 180.2, 360.0, 360.05, 540.9):
            count = source.segment_bounds(duration, 1)["totalParts"]
            parts = [source.segment_bounds(duration, part) for part in range(1, count + 1)]
            self.assertEqual(parts[0]["startSeconds"], 0)
            self.assertEqual(parts[-1]["endSeconds"], duration)
            for left, right in zip(parts, parts[1:]):
                self.assertEqual(left["endSeconds"], right["startSeconds"])
            self.assertTrue(all(0 < part["endSeconds"] - part["startSeconds"] <= 180.15 for part in parts))

    def test_out_of_order_part_beyond_episode_is_rejected(self):
        with self.assertRaises(source.SourceValidationError):
            source.segment_bounds(168.874, 2)

    def test_video_preview_with_sound_cannot_pass_as_full_episode(self):
        preview = {"videoDurationSeconds": 60.0, "audioDurationSeconds": 60.0}
        with self.assertRaises(source.SourceValidationError):
            source.validate_full_coverage(preview, 168.874)

    def test_one_truncated_stream_is_rejected(self):
        with self.assertRaises(source.SourceValidationError):
            source.validate_full_coverage({"videoDurationSeconds": 168.87, "audioDurationSeconds": 150}, 168.874)

    def test_encryption_is_a_block_not_a_fallback(self):
        manifest = {"contents": [{"encryption_infos": [{"key_system": "widevine"}], "end_time_millis": 168874}]}
        with self.assertRaises(source.SourceAccessRequired):
            source.native_manifest_selection(manifest, 168.874)

    def test_missing_original_video_or_audio_is_rejected(self):
        manifest = {"contents": [{"end_time_millis": 168874, "profiles": [{"mime_type": "audio/mp4"}]}]}
        with self.assertRaises(source.SourceValidationError):
            source.native_manifest_selection(manifest, 168.874)

    def test_unrelated_show_catalog_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps({"showId": "2lxmtcbizlC4eKhEa5HZ4I", "episodes": []}))
            with self.assertRaises(source.SourceValidationError):
                source.load_catalog(path)

    def test_reposted_facebook_account_cannot_be_a_creator_source(self):
        self.assertIsNone(source.canonical_creator_url("https://www.facebook.com/randomreposts/videos/1237986135113831/"))
        self.assertEqual(source.canonical_creator_url("https://www.facebook.com/HisYTStory/videos/story/1237986135113831/"),
                         "https://www.facebook.com/HisYTStory/videos/1237986135113831/")

    def test_other_hosts_and_deceptive_facebook_urls_are_rejected(self):
        for url in (
            "https://www.youtube.com/watch?v=1237986135113831",
            "https://youtu.be/1237986135113831",
            "https://vimeo.com/1237986135113831",
            "https://www.facebook.com.evil.example/HisYTStory/videos/1237986135113831/",
            "https://attacker@www.facebook.com/HisYTStory/videos/1237986135113831/",
            "http://www.facebook.com/HisYTStory/videos/1237986135113831/",
        ):
            self.assertIsNone(source.canonical_facebook_url(url), url)

    def test_creator_post_can_discover_but_cannot_claim_a_video_id(self):
        post = "https://www.facebook.com/HisYTStory/posts/story-title/948143861196751/"
        self.assertEqual(source.canonical_facebook_candidate_url(post),
                         "https://www.facebook.com/HisYTStory/posts/948143861196751/")
        self.assertIsNone(source.canonical_facebook_url(post))
        wrapped = '<a href="/l/?uddg=https%3A%2F%2Fwww.facebook.com%2FHisYTStory%2Fposts%2F948143861196751%2F">Story</a>'
        self.assertEqual(source.extract_facebook_urls(wrapped),
                         ["https://www.facebook.com/HisYTStory/posts/948143861196751/"])

    def test_catalog_candidate_urls_are_filtered_before_discovery(self):
        expected = "https://www.facebook.com/HisYTStory/posts/948143861196751/"
        episode = {"transportCandidates": ["https://youtu.be/123456", expected]}
        with patch.object(source, "search_transport_urls") as search:
            self.assertEqual(next(source.discover_transport_urls(episode)), expected)
            search.assert_not_called()

    def test_cached_url_cannot_change_uploader(self):
        url = "https://www.facebook.com/publiccopy/videos/4357183091258743/"
        episode = {"title": "Example Story", "durationMs": 115008,
                   "verifiedTransport": {"visualUrl": url, "uploaderId": "61562134240322"}}
        metadata = {"extractor": "facebook", "id": "4357183091258743", "uploader_id": "99999999",
                    "title": "Example Story", "duration": 115.008}
        with patch.object(source, "command", return_value=json.dumps(metadata).encode()) as cmd:
            with self.assertRaises(source.SourceValidationError):
                source.acquire_creator_video(episode, url, Path("/unused"))
            self.assertEqual(cmd.call_count, 1)

    def test_matching_title_duration_and_cache_flags_do_not_replace_full_audio_proof(self):
        episode = {"id": source.FIRST_EPISODE_ID, "durationMs": 168874}
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            with (patch.object(source, "discover_transport_urls", return_value=iter(["candidate"])),
                  patch.object(source, "spotify_rss_episode", return_value={"audioUrl": "audio"}),
                  patch.object(source, "spotify_preview", return_value={"url": "preview"}),
                  patch.object(source, "download_bytes", return_value=b"reference bytes"),
                  patch.object(source, "acquire_creator_video", return_value=(temp / "candidate.mp4", {})),
                  patch.object(source, "verify_full_audio", side_effect=source.SourceValidationError("Different sound")),
                  patch.object(source, "command") as cmd,
                  patch.object(source, "atomic_json") as save):
                with self.assertRaises(source.SourceValidationError):
                    source.acquire_verified_creator(episode, temp, temp / "catalog.json")
                cmd.assert_not_called()
                save.assert_not_called()
                self.assertFalse((temp / "full-source.mp4").exists())

    def test_pinned_rss_guid_cannot_be_reassigned_by_a_matching_title(self):
        episode = {"title": "Example Story", "releaseDate": "2026-03-11T07:35:00Z", "rssGuid": "original-guid"}
        with self.assertRaises(source.SourceValidationError):
            source.match_rss_episode(episode, [{"title": "Example Story", "releaseDate": "2026-03-11T07:35:00+00:00", "guid": "different-guid"}])

    def test_view_counts_do_not_break_exact_title_identity(self):
        self.assertTrue(source.creator_title_matches("His Mom Made Him Kneel On Broken Glass",
            "158K views | His Mom Made Him Kneel On Broken Glass 😰 This story may be based on real events | His Story"))
        self.assertFalse(source.creator_title_matches("His Mom Made Him Kneel On Broken Glass",
            "His Mother Made Him Kneel On Broken Glass | His Story"))
        self.assertTrue(source.creator_title_matches("Bad Roommates | Full Compilation", "14K views | Bad Roommates | Full Compilation | His Story"))

    def preview_with_padding(self, *, reference_samples=20002, padding_samples=20, codec="aac", wrong_sound=False):
        import numpy as np
        rng = np.random.default_rng(5)
        reference = rng.normal(size=reference_samples).astype(np.float32)
        declared = 20000
        preview = np.r_[reference[:declared], rng.normal(size=padding_samples)].astype(np.float32)
        if wrong_sound:
            preview = rng.normal(size=declared + padding_samples).astype(np.float32)
        frames = np.eye(4, dtype=np.float32)
        info = {"durationSeconds": 10.0, "audioDurationSeconds": 10.0,
                "audioCodec": codec, "audio": {"sample_rate": "48000"}}
        with (patch.object(source, "probe", return_value=info),
              patch.object(source, "audio_samples", side_effect=[reference, preview]),
              patch.object(source, "gray_frames", return_value=frames)):
            return source.verify_preview_frames(Path("video"), Path("audio"), Path("preview"), 10.0)

    def test_full_length_preview_allows_only_aac_padding_beyond_declared_end(self):
        proof = self.preview_with_padding()
        self.assertGreater(proof["previewAudioCorrelation"], 0.999)
        self.assertEqual(proof["previewAudioDecoderPaddingSeconds"], 0.01)
        self.assertEqual(proof["previewAudioComparedSeconds"], 10.0)
        self.assertEqual(proof["previewFramesCompared"], 4)

    def test_preview_padding_cannot_hide_reference_missing_declared_audio(self):
        with self.assertRaises(source.SourceValidationError):
            self.preview_with_padding(reference_samples=19999)

    def test_preview_padding_beyond_one_codec_frame_is_rejected(self):
        with self.assertRaises(source.SourceValidationError):
            self.preview_with_padding(padding_samples=400)

    def test_preview_padding_exception_does_not_apply_to_other_codecs(self):
        with self.assertRaises(source.SourceValidationError):
            self.preview_with_padding(codec="mp3")

    def test_padded_preview_with_different_sound_is_still_rejected(self):
        with self.assertRaises(source.SourceValidationError):
            self.preview_with_padding(wrong_sound=True)

    def test_public_sixty_second_clip_cannot_complete_a_longer_episode(self):
        episode = {"id": source.FIRST_EPISODE_ID, "durationMs": 60100}
        with patch.object(source, "probe") as probe:
            self.assertIsNone(source.acquire_complete_public_video(
                episode, Path("unused"), Path("catalog"), {}, {}, Path("audio"), Path("video")))
            probe.assert_not_called()

    def public_video_fixture(self):
        episode = {"id": source.FIRST_EPISODE_ID, "durationMs": 10000}
        asset = "a" * 32
        metadata = {"episodeId": episode["id"], "showId": source.SHOW_ID,
                    "embedUrl": f"https://open.spotify.com/embed/episode/{episode['id']}",
                    "url": f"https://smart-preview-clips.spotifycdn.com/previews/{asset}/0/{asset}.mp4"}
        media = {"durationSeconds": 10.0, "videoDurationSeconds": 10.0, "audioDurationSeconds": 10.0,
                 "video": {"start_time": "0"}, "audio": {"start_time": "0"}}
        rss = {"guid": "matched-guid", "audioUrl": "https://anchor.fm/s/10ff75318/podcast/play/example/audio.mp3"}
        return episode, metadata, media, rss

    def test_short_native_clip_cannot_substitute_for_complete_short_episode(self):
        episode, metadata, media, rss = self.public_video_fixture()
        media["videoDurationSeconds"] = media["audioDurationSeconds"] = 5.0
        with (patch.object(source, "probe", return_value=media),
              patch.object(source, "verify_full_audio") as verify):
            self.assertIsNone(source.acquire_complete_public_video(
                episode, Path("unused"), Path("catalog"), metadata, rss, Path("audio"), Path("video")))
            verify.assert_not_called()

    def test_complete_native_video_requires_the_exact_episode_and_show(self):
        episode, metadata, media, rss = self.public_video_fixture()
        for replacement in ({"episodeId": "different"}, {"showId": "different"},
                            {"url": metadata["url"].replace("spotifycdn.com", "spotifycdn.com.evil.example")}):
            with self.subTest(replacement=replacement), patch.object(source, "probe", return_value=media):
                with self.assertRaises(source.SourceValidationError):
                    source.acquire_complete_public_video(episode, Path("unused"), Path("catalog"),
                        {**metadata, **replacement}, rss, Path("audio"), Path("video"))

    def test_complete_public_video_does_not_invent_a_transport_preview_match(self):
        episode, metadata, media, rss = self.public_video_fixture()
        catalog = {"episodes": [dict(episode)]}
        sound = {"audioCorrelation": 0.999, "fullAudioCorrelation": 0.999,
                 "audioVerifiedDurationSeconds": 10.0}
        with (patch.object(source, "probe", return_value=media),
              patch.object(source, "verify_full_audio", return_value=sound) as verify,
              patch.object(source, "command"), patch.object(source, "sha256", return_value="0" * 64),
              patch.object(source, "load_catalog", return_value=catalog),
              patch.object(source, "atomic_json") as save):
            full, evidence = source.acquire_complete_public_video(episode, Path("unused"), Path("catalog"),
                metadata, rss, Path("audio"), Path("video"))
        verify.assert_called_once_with(Path("video"), Path("audio"), 10.0)
        self.assertEqual(full, Path("unused/full-source.mp4"))
        self.assertEqual(evidence["sourceAccessMethod"], "spotify-complete-public-video")
        proof = evidence["sourceVerification"]
        self.assertTrue(proof["fullNativeVideoVerified"])
        self.assertEqual(proof["nativeEmbedUrl"], metadata["embedUrl"])
        self.assertNotIn("previewFrameVerified", proof)
        self.assertIn("verifiedPublicVideo", catalog["episodes"][0])
        save.assert_called_once()

    def test_complete_native_video_with_wrong_sound_does_not_mux_or_cache(self):
        episode, metadata, media, rss = self.public_video_fixture()
        with (patch.object(source, "probe", return_value=media),
              patch.object(source, "verify_full_audio", side_effect=source.SourceValidationError("Different sound")),
              patch.object(source, "command") as mux, patch.object(source, "atomic_json") as save):
            with self.assertRaises(source.SourceValidationError):
                source.acquire_complete_public_video(episode, Path("unused"), Path("catalog"),
                    metadata, rss, Path("audio"), Path("video"))
            mux.assert_not_called()
            save.assert_not_called()

    def test_complete_native_video_cannot_start_in_the_middle(self):
        episode, metadata, media, rss = self.public_video_fixture()
        media["video"]["start_time"] = "0.5"
        with patch.object(source, "probe", return_value=media):
            with self.assertRaises(source.SourceValidationError):
                source.acquire_complete_public_video(episode, Path("unused"), Path("catalog"),
                    metadata, rss, Path("audio"), Path("video"))

    def test_spotify_embed_must_link_to_the_pinned_show(self):
        episode = {"id": source.FIRST_EPISODE_ID, "durationMs": 10000}
        entity = {"type": "episode", "id": episode["id"], "uri": f"spotify:episode:{episode['id']}",
                  "relatedEntityUri": "spotify:show:another-show", "duration": 10000,
                  "hasVideo": True, "videoPreview": {"url": "https://smart-preview-clips.spotifycdn.com/test.mp4"}}
        page = ('<script id="__NEXT_DATA__">' + json.dumps({"entity": entity}) + '</script>').encode()
        with patch.object(source, "download_bytes", return_value=page):
            with self.assertRaises(source.SourceValidationError):
                source.spotify_preview(episode)


if __name__ == "__main__":
    unittest.main()
