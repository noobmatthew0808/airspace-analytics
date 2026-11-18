import unittest
from unittest.mock import patch
from backend import live_terminal

class Stub:
    def send_json(self, data, code=200):
        self.answer = data, code

class TestLiveTerminal(unittest.TestCase):
    def test_command_cannot_be_set_from_browser(self):
        self.assertEqual(live_terminal.COMMAND,
            ('docker', 'exec', '-e', 'TERM=xterm', '-t', 'ultrafeeder', 'viewadsb'))
        self.assertGreater(live_terminal.COLS, 100)

    def test_unavailable_docker_is_nonfatal(self):
        handler=Stub()
        with patch.object(live_terminal.shutil,'which',return_value=None), \
             patch.object(live_terminal.subprocess,'Popen') as start:
            live_terminal.stream(handler)
            start.assert_not_called()
        self.assertEqual(handler.answer[1], 503)

    def test_explanatory_footer_removed(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1] / 'frontend' / 'live-terminal.js').read_text()
        self.assertNotIn('live-terminal-note', js)
        self.assertIn('Docker permission denied', js)
