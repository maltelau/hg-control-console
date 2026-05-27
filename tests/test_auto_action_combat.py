import unittest

from src.simkeys_app.simkeys_script_host import AutoActionScript, parse_chat_line_event


class FakeClient:
    pid = 1234
    display_name = "PlayerCharacter"
    character_name = "PlayerCharacter"
    query = {}


class FakeHost:
    def __init__(self):
        self.client = FakeClient()
        self.latest_sequence = 0
        self.events = []
        self.chats = []
        self.recovery_active = False

    def emit(self, level, message, script_id=None):
        self.events.append((level, message, script_id))

    def notify_state_changed(self):
        pass

    def is_shifter_recovery_active(self):
        return self.recovery_active


class TestAutoActionCombat(unittest.TestCase):
    def setUp(self):
        self.host = FakeHost()
        self.config = {"mode": "Knockdown", "cooldown_seconds": 1.0}
        self.script = AutoActionScript(self.host.client, self.config, self.host)
        self.script.enabled = True

    def test_combat_tracking(self):
        self.assertEqual(self.script.last_combat_at, 0.0)

        event = parse_chat_line_event(1, "PlayerCharacter attacks Aboleth")
        self.script.on_chat_event(event)

        self.assertGreater(self.script.last_combat_at, 0.0)

        self.script.last_combat_at = 0.0
        event = parse_chat_line_event(2, "PlayerCharacter attacks FriendlyNPC")
        self.script.on_chat_event(event)
        self.assertEqual(self.script.last_combat_at, 0.0)

        event = parse_chat_line_event(3, "OtherPlayer attacks Aboleth")
        self.script.on_chat_event(event)
        self.assertEqual(self.script.last_combat_at, 0.0)

    def test_damage_tracking(self):
        event = parse_chat_line_event(1, "PlayerCharacter damages Aboleth: 10 (10 physical)")
        self.script.on_chat_event(event)

        self.assertGreater(self.script.last_combat_at, 0.0)

    def test_combat_window_uses_six_second_minimum(self):
        self.script.last_combat_at = 100.0

        self.assertEqual(self.script._combat_window_seconds(), 6.0)
        self.assertTrue(self.script._combat_is_recent(now=105.9))
        self.assertFalse(self.script._combat_is_recent(now=106.1))

    def test_combat_window_extends_for_longer_cooldowns(self):
        self.script.config["cooldown_seconds"] = 12.5
        self.script.last_combat_at = 100.0

        self.assertEqual(self.script._combat_window_seconds(), 12.5)
        self.assertTrue(self.script._combat_is_recent(now=112.4))
        self.assertFalse(self.script._combat_is_recent(now=112.6))
