import unittest
from unittest import mock

import numpy

import audio_samples


class LoadSampleTest(unittest.TestCase):
    def test_returns_file_converted_to_output_format(self):
        with mock.patch.object(audio_samples.wavfile, "read", return_value=(44100, "raw-data")) as read, \
             mock.patch.object(audio_samples, "to_int16", return_value="int16-data") as to_int16, \
             mock.patch.object(audio_samples, "to_stereo", return_value="stereo-data") as to_stereo, \
             mock.patch.object(audio_samples, "resample_to_output_rate", return_value="output-data") as resample:
            result = audio_samples.load_sample("/fake/sound.wav")

        read.assert_called_once_with("/fake/sound.wav")
        to_int16.assert_called_once_with("raw-data")
        to_stereo.assert_called_once_with("int16-data")
        resample.assert_called_once_with("stereo-data", 44100)
        self.assertEqual(result, "output-data")


class ToInt16Test(unittest.TestCase):
    def test_returns_int16_data_unchanged(self):
        data = numpy.array([-32768, 0, 32767], dtype=numpy.int16)

        numpy.testing.assert_array_equal(audio_samples.to_int16(data), data)

    def test_scales_float_data_to_full_range(self):
        data = numpy.array([-1.0, 0.0, 0.5, 1.0], dtype=numpy.float32)

        result = audio_samples.to_int16(data)

        self.assertEqual(result.dtype, numpy.int16)
        numpy.testing.assert_array_equal(result, [-32767, 0, 16384, 32767])

    def test_clips_float_data_beyond_full_scale(self):
        data = numpy.array([-1.5, 1.5], dtype=numpy.float64)

        numpy.testing.assert_array_equal(audio_samples.to_int16(data), [-32768, 32767])

    def test_centers_unsigned_8_bit_data(self):
        data = numpy.array([0, 128, 255], dtype=numpy.uint8)

        numpy.testing.assert_array_equal(audio_samples.to_int16(data), [-32768, 0, 32512])

    def test_keeps_high_16_bits_of_32_bit_data(self):
        data = numpy.array([-2147483648, 65536, 2147483647], dtype=numpy.int32)

        numpy.testing.assert_array_equal(audio_samples.to_int16(data), [-32768, 1, 32767])

    def test_rejects_unsupported_sample_type(self):
        with self.assertRaises(ValueError):
            audio_samples.to_int16(numpy.array([1 + 1j]))


class ToStereoTest(unittest.TestCase):
    def test_returns_stereo_data_unchanged(self):
        data = numpy.array([[1, 2], [3, 4]], dtype=numpy.int16)

        numpy.testing.assert_array_equal(audio_samples.to_stereo(data), data)

    def test_copies_one_dimensional_mono_to_both_channels(self):
        data = numpy.array([1, 2], dtype=numpy.int16)

        numpy.testing.assert_array_equal(audio_samples.to_stereo(data), [[1, 1], [2, 2]])

    def test_copies_single_channel_column_to_both_channels(self):
        data = numpy.array([[1], [2]], dtype=numpy.int16)

        numpy.testing.assert_array_equal(audio_samples.to_stereo(data), [[1, 1], [2, 2]])

    def test_rejects_more_than_two_channels(self):
        with self.assertRaises(ValueError):
            audio_samples.to_stereo(numpy.zeros((2, 3), dtype=numpy.int16))


class ResampleToOutputRateTest(unittest.TestCase):
    def test_returns_data_unchanged_at_output_rate(self):
        data = numpy.zeros((10, 2), dtype=numpy.int16)

        self.assertIs(audio_samples.resample_to_output_rate(data, audio_samples.OUTPUT_RATE), data)

    def test_returns_resampled_full_scale_floats_converted_to_int16(self):
        data = numpy.full((1470, 2), 32767, dtype=numpy.int16)

        with mock.patch.object(audio_samples, "to_int16", return_value="int16-data") as to_int16:
            result = audio_samples.resample_to_output_rate(data, 44100)

        (resampled,), _ = to_int16.call_args
        self.assertEqual(resampled.shape, (1600, 2))
        self.assertAlmostEqual(resampled[800, 0], 1.0, places=2)
        self.assertEqual(result, "int16-data")


if __name__ == "__main__":
    unittest.main()
