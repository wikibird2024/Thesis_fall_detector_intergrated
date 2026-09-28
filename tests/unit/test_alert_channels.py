"""Telegram and Asterisk channels, with their network clients replaced by fakes."""

import pytest
from telegram.error import NetworkError, TelegramError

from fall_detector.alerts.ami_trigger import AMITrigger, is_success, one_line
from fall_detector.alerts.base import AlertChannel, AlertDeliveryError
from fall_detector.alerts.telegram_bot import TelegramBot
from fall_detector.domain import Alert, EventSource, FallEvent

EVENT = FallEvent(source=EventSource.CAMERA, entity_id="camera_person_1")


# ---------------------------------------------------------------- Telegram


class FakeTelegramApi:
    def __init__(self, photo_error=None, text_error=None, init_error=None):
        self.photo_error, self.text_error, self.init_error = photo_error, text_error, init_error
        self.photos, self.texts = [], []

    async def initialize(self):
        if self.init_error:
            raise self.init_error

    async def send_photo(self, chat_id, photo, caption):
        if self.photo_error:
            raise self.photo_error
        self.photos.append((chat_id, caption))

    async def send_message(self, chat_id, text):
        if self.text_error:
            raise self.text_error
        self.texts.append((chat_id, text))

    async def shutdown(self):
        pass


def telegram(api) -> TelegramBot:
    return TelegramBot("token", "42", send_startup_message=False, bot=api)


def test_channels_follow_the_protocol():
    assert isinstance(telegram(FakeTelegramApi()), AlertChannel)


async def test_telegram_sends_photo_when_image_exists():
    api = FakeTelegramApi()
    await telegram(api).send(Alert(EVENT, image_jpeg=b"jpeg"))
    assert api.photos == [("42", EVENT.alert_text())] and api.texts == []


async def test_telegram_sends_text_without_image():
    api = FakeTelegramApi()
    await telegram(api).send(Alert(EVENT))
    assert api.texts == [("42", EVENT.alert_text())]


async def test_telegram_falls_back_to_text_when_photo_fails():
    api = FakeTelegramApi(photo_error=TelegramError("photo too big"))
    await telegram(api).send(Alert(EVENT, image_jpeg=b"jpeg"))
    assert len(api.texts) == 1


async def test_telegram_raises_when_text_fails_so_dispatcher_retries():
    api = FakeTelegramApi(text_error=NetworkError("offline"))
    with pytest.raises(NetworkError):
        await telegram(api).send(Alert(EVENT))


async def test_telegram_start_survives_network_problem():
    await telegram(FakeTelegramApi(init_error=NetworkError("offline"))).start()


async def test_telegram_start_sends_startup_message():
    api = FakeTelegramApi()
    await TelegramBot("token", "42", bot=api).start()
    assert "started" in api.texts[0][1]


# ---------------------------------------------------------------- Asterisk


class FakeManager:
    def __init__(self, connect_error=None, replies=None, **kwargs):
        self.connect_error = connect_error
        self.replies = replies or {}  # (action, extension) -> reply
        self.actions = []
        self.connects = 0

    async def connect(self):
        self.connects += 1
        if self.connect_error:
            raise self.connect_error

    async def send_action(self, action):
        self.actions.append(action)
        extension = (action.get("Channel") or action.get("To")).split("/")[-1].split(":")[-1]
        reply = self.replies.get((action["Action"], extension), {"Response": "Success"})
        if isinstance(reply, Exception):
            raise reply
        return reply

    def close(self):
        pass


def asterisk(manager, extensions=("6001", "6002")) -> AMITrigger:
    return AMITrigger(
        "127.0.0.1",
        5038,
        "user",
        "secret",
        extensions=extensions,
        caller_id="Alert",
        cleanup_delay_s=0,
        manager_factory=lambda **kw: manager,
    )


async def test_asterisk_calls_and_messages_every_extension():
    manager = FakeManager()
    await asterisk(manager).send(Alert(EVENT))
    kinds = sorted((a["Action"], a.get("Channel") or a["To"]) for a in manager.actions)
    assert kinds == [
        ("MessageSend", "pjsip:6001"),
        ("MessageSend", "pjsip:6002"),
        ("Originate", "PJSIP/6001"),
        ("Originate", "PJSIP/6002"),
    ]


async def test_asterisk_text_is_single_line():
    # AMI header values end at a line break; multi-line text would corrupt the action.
    manager = FakeManager()
    await asterisk(manager).send(Alert(EVENT))
    assert all("\n" not in str(value) for action in manager.actions for value in action.values())


async def test_asterisk_partial_failure_still_counts_as_delivered():
    failure = {"Response": "Error"}
    manager = FakeManager(replies={("Originate", "6001"): failure, ("MessageSend", "6001"): failure})
    await asterisk(manager).send(Alert(EVENT))  # 6002 reached: no exception


async def test_asterisk_raises_when_no_extension_reached():
    failure = {"Response": "Error"}
    replies = {(kind, ext): failure for kind in ("Originate", "MessageSend") for ext in ("6001", "6002")}
    with pytest.raises(AlertDeliveryError):
        await asterisk(FakeManager(replies=replies)).send(Alert(EVENT))


async def test_asterisk_raises_when_cannot_connect():
    with pytest.raises(AlertDeliveryError):
        await asterisk(FakeManager(connect_error=ConnectionRefusedError())).send(Alert(EVENT))


async def test_asterisk_reconnects_after_action_error():
    manager = FakeManager(replies={("Originate", "6001"): ConnectionResetError()})
    trigger = asterisk(manager, extensions=["6001"])
    await trigger.send(Alert(EVENT))  # message still succeeded
    assert not trigger.is_connected
    await trigger.send(Alert(EVENT))
    assert manager.connects == 2


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ({"Response": "Success"}, True),
        ({"Response": "Error"}, False),
        ([{"Response": "Error"}, {"Response": "Success"}], True),
        ([], False),
    ],
)
def test_is_success_reads_dict_and_list_replies(reply, expected):
    assert is_success(reply) is expected


def test_one_line_joins_lines():
    assert one_line("a\n\n b \nc") == "a | b | c"
