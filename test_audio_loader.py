import unittest
from unittest import mock

import audio_loader


class SampleLoaderTest(unittest.TestCase):
    def test_loads_requested_files_in_order_and_returns_them_with_their_tags(self):
        with mock.patch.object(audio_loader, "load_sample", side_effect=["fake-samples-a", "fake-samples-b"]) as load_sample:
            loader = audio_loader.SampleLoader()
            loader.request("/fake/a.wav", "fake-tag-a")
            loader.request("/fake/b.wav", "fake-tag-b")
            loader.stop()

        self.assertEqual(load_sample.call_args_list, [mock.call("/fake/a.wav"), mock.call("/fake/b.wav")])
        self.assertEqual(loader.completed(), [
            audio_loader.LoadedSample("/fake/a.wav", "fake-tag-a", "fake-samples-a"),
            audio_loader.LoadedSample("/fake/b.wav", "fake-tag-b", "fake-samples-b"),
        ])

    def test_returns_each_completed_load_only_once(self):
        with mock.patch.object(audio_loader, "load_sample", return_value="fake-samples"):
            loader = audio_loader.SampleLoader()
            loader.request("/fake/a.wav", "fake-tag")
            loader.stop()

        loader.completed()

        self.assertEqual(loader.completed(), [])

    def test_reports_an_unreadable_file_without_samples_and_keeps_loading(self):
        with mock.patch.object(audio_loader, "load_sample", side_effect=[OSError("fake-error"), "fake-samples"]), \
             self.assertLogs(audio_loader.logger, level="ERROR") as logs:
            loader = audio_loader.SampleLoader()
            loader.request("/fake/missing.wav", "fake-tag-a")
            loader.request("/fake/b.wav", "fake-tag-b")
            loader.stop()

        self.assertIn("/fake/missing.wav", logs.output[0])
        self.assertEqual(loader.completed(), [
            audio_loader.LoadedSample("/fake/missing.wav", "fake-tag-a", None),
            audio_loader.LoadedSample("/fake/b.wav", "fake-tag-b", "fake-samples"),
        ])

    def test_reports_an_unsupported_file_without_samples(self):
        with mock.patch.object(audio_loader, "load_sample", side_effect=ValueError("fake-error")), \
             self.assertLogs(audio_loader.logger, level="ERROR"):
            loader = audio_loader.SampleLoader()
            loader.request("/fake/bad.wav", "fake-tag")
            loader.stop()

        self.assertEqual(loader.completed(), [audio_loader.LoadedSample("/fake/bad.wav", "fake-tag", None)])


if __name__ == "__main__":
    unittest.main()
