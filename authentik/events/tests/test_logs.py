"""Test log capturing"""

from threading import Event, Thread

from django.test import SimpleTestCase
from structlog import get_config
from structlog.stdlib import get_logger

from authentik.events.logs import LogEvent, capture_logs

LOGGER = get_logger()
TIMEOUT = 10


class TestCaptureLogs(SimpleTestCase):
    """Test capture_logs"""

    def test_capture(self):
        """Entries logged in the block are captured"""
        with capture_logs() as logs:
            LOGGER.warning("captured", foo="bar")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].event, "captured")
        self.assertEqual(logs[0].log_level, "warning")
        self.assertEqual(logs[0].attributes["foo"], "bar")

    def test_nested(self):
        """A nested block captures its own entries, and the outer block
        captures them once they are logged again"""
        with capture_logs() as outer:
            LOGGER.warning("outer")
            with capture_logs() as inner:
                LOGGER.warning("inner")
            self.assertEqual([log.event for log in inner], ["inner"])
            for log in inner:
                log.log()
        self.assertEqual([log.event for log in outer], ["outer", "inner"])

    def test_overlapping_threads(self):
        """Blocks overlapping on two threads each capture their own entries
        and leave the structlog configuration untouched"""
        processors = get_config()["processors"].copy()
        first_in, second_in, first_out = Event(), Event(), Event()
        captured: dict[str, list[LogEvent]] = {}

        def first():
            with capture_logs() as logs:
                LOGGER.warning("first")
                first_in.set()
                second_in.wait(TIMEOUT)
            captured["first"] = logs
            first_out.set()

        def second():
            first_in.wait(TIMEOUT)
            with capture_logs() as logs:
                second_in.set()
                first_out.wait(TIMEOUT)
                LOGGER.warning("second")
            captured["second"] = logs

        threads = [Thread(target=first), Thread(target=second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(TIMEOUT)

        self.assertEqual([log.event for log in captured["first"]], ["first"])
        self.assertEqual([log.event for log in captured["second"]], ["second"])
        self.assertEqual(get_config()["processors"], processors)
