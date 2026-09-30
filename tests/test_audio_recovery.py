import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.ai.transcriber import IncompleteAudioError, NoAudioStreamError, Transcriber
from src.pipeline.lecture_runner import LectureRunner
from src.runtime.scheduler import AudioDownloader


def truncated(seconds, expected, text):
    return IncompleteAudioError('truncated', seconds, expected, text,
                                [{'start_ms': 0, 'end_ms': int(seconds * 1000), 'text': text}])


class AudioRecoveryTest(unittest.TestCase):
    def runner(self, outcomes):
        runner = object.__new__(LectureRunner)
        runner._client = Mock()
        runner._db = Mock()
        runner._reporter = Mock()
        runner._official_cache = {}
        runner._transcriber = Mock()
        pending = iter(outcomes)
        def consume(*args, **kwargs):
            outcome = next(pending)
            if isinstance(outcome, Exception):
                raise outcome
            runner._transcriber._last_duration = max(
                (s['end_ms'] for s in outcome[1]), default=0) / 1000
            return outcome
        runner._transcriber.transcribe_tail.side_effect = consume
        handle = SimpleNamespace(path='audio.raw', process=Mock(), stderr_chunks=[])
        downloader = Mock()
        downloader.get.return_value = handle
        runner._scheduler = SimpleNamespace(audio_downloader=downloader)
        return runner

    @patch('src.pipeline.lecture_runner.config.USE_OFFICIAL_TRANSCRIPT', False)
    def test_two_truncated_downloads_resume_and_preserve_the_whole_transcript(self):
        runner = self.runner([
            truncated(4065, 10027, 'head'), truncated(4000, 5962, 'middle'),
            ('tail', [{'start_ms': 0, 'end_ms': 1962000, 'text': 'tail'}]),
        ])
        text, segments = runner._get_transcript(None, '37234', 'lecture')
        self.assertEqual(text, 'head middle tail')
        self.assertEqual([s['start_ms'] for s in segments], [0, 4065000, 8065000])
        self.assertEqual(segments[-1]['end_ms'], 10027000)
        runner._db.update_transcript.assert_called_once_with('lecture', text)
        offsets = [c.kwargs.get('start_seconds', 0) for c in runner._scheduler.audio_downloader.schedule.call_args_list]
        self.assertEqual(offsets, [0, 4065, 8065])

    @patch('src.pipeline.lecture_runner.config.USE_OFFICIAL_TRANSCRIPT', False)
    def test_exhausted_recovery_never_persists_a_partial_transcript(self):
        runner = self.runner([truncated(10, 1000, 'partial')] * 3)
        self.assertEqual(runner._get_transcript(None, '38723', 'lecture'), (None, None))
        self.assertEqual(runner._transcriber.transcribe_tail.call_count, 3)
        runner._db.update_transcript.assert_not_called()
        runner._db.update_error.assert_called_once()

    def test_resumed_completeness_compares_to_the_remaining_duration(self):
        transcriber = Transcriber()
        transcriber._media_duration = 10027
        transcriber._last_duration = 5962
        transcriber._check_completeness('tail', [], start_seconds=4065)
        transcriber._last_duration = 4000
        with self.assertRaises(IncompleteAudioError) as error:
            transcriber._check_completeness('partial', [], start_seconds=4065)
        self.assertEqual(error.exception.expected_duration, 5962)

    @patch('src.pipeline.lecture_runner.config.USE_OFFICIAL_TRANSCRIPT', False)
    def test_retry_without_duration_header_cannot_persist_short_tail(self):
        runner = self.runner([truncated(4065, 10027, 'head'),
                              ('short', [{'start_ms': 0, 'end_ms': 1000, 'text': 'short'}]),
                              ('short', [{'start_ms': 0, 'end_ms': 1000, 'text': 'short'}])])
        self.assertEqual(runner._get_transcript(None, '37234', 'lecture'), (None, None))
        runner._db.update_transcript.assert_not_called()

    @patch('src.pipeline.lecture_runner.config.USE_OFFICIAL_TRANSCRIPT', False)
    def test_empty_retry_retries_at_same_offset(self):
        runner = self.runner([truncated(4065, 10027, 'head'), truncated(0, 0, ''),
                              ('tail', [{'start_ms': 0, 'end_ms': 5962000, 'text': 'tail'}])])
        text, _ = runner._get_transcript(None, '37234', 'lecture')
        self.assertEqual(text, 'head tail')
        offsets = [c.kwargs.get('start_seconds', 0) for c in runner._scheduler.audio_downloader.schedule.call_args_list]
        self.assertEqual(offsets, [0, 4065, 4065])

    @patch('src.pipeline.lecture_runner.config.USE_OFFICIAL_TRANSCRIPT', False)
    def test_initial_empty_response_preserves_known_duration(self):
        runner = self.runner([truncated(0, 10027, ''),
                              ('short', [{'start_ms': 0, 'end_ms': 1000, 'text': 'short'}]),
                              ('short', [{'start_ms': 0, 'end_ms': 1000, 'text': 'short'}])])
        self.assertEqual(runner._get_transcript(None, '37234', 'lecture'), (None, None))
        runner._db.update_transcript.assert_not_called()

    @patch('src.pipeline.lecture_runner.config.USE_OFFICIAL_TRANSCRIPT', False)
    def test_missing_tail_audio_does_not_mark_a_partial_lecture_processed(self):
        runner = self.runner([truncated(4065, 10027, 'head'), NoAudioStreamError('no tail')])
        with self.assertRaises(RuntimeError):
            runner._get_transcript(None, '37234', 'lecture')
        runner._db.mark_processed.assert_not_called()
        runner._db.update_transcript.assert_not_called()

    def test_resume_refreshes_the_source_and_seeks_before_input(self):
        with tempfile.TemporaryDirectory() as folder:
            downloader = AudioDownloader(folder, max_concurrent=1)
            process = Mock()
            process.stderr = iter([])
            process.wait.return_value = 0
            client = Mock()
            client.get_video_url.return_value = 'https://example.invalid/fresh.mp4'
            client.get_stream_params.return_value = ('https://example.invalid/fresh.mp4', 'test-header')
            with patch('src.runtime.scheduler.subprocess.Popen', return_value=process) as spawn:
                downloader.schedule(client, '37234', 'lecture', start_seconds=4065)
                self.assertIsNotNone(downloader.get('lecture', timeout=2))
                cmd = spawn.call_args.args[0]
                self.assertEqual(cmd[cmd.index('-ss') + 1], '4065')
                self.assertLess(cmd.index('-ss'), cmd.index('-i'))
                client.get_video_url.assert_called_once_with('37234', 'lecture')


if __name__ == '__main__':
    unittest.main()
