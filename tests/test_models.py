from harmonia.models import Message, Poll, User


def test_user_from_dict_and_fallbacks():
    user = User.from_dict(
        {"id": "1", "username": "bob", "displayName": None, "accountType": "bot"}
    )
    assert user.name == "bob"
    assert user.is_bot
    assert user.mention == "@bob"


def test_message_from_dict_models_relations():
    message = Message.from_dict(
        {
            "id": "m1",
            "channelId": "c1",
            "author": {"id": "u1", "username": "bob"},
            "content": "hello",
            "replyTo": {"id": "m0", "author": None, "content": "", "deleted": True},
            "reactions": [{"emoji": "👍", "count": 2, "me": False}],
            "poll": {"question": "Q?", "options": [{"id": "o1", "text": "A", "count": 3}]},
        }
    )
    assert message.author.username == "bob"
    assert message.reply_to.deleted is True
    assert message.reactions[0].count == 2
    assert isinstance(message.poll, Poll)
    assert message.poll.options[0].text == "A"


def test_message_tolerates_absent_relations():
    message = Message.from_dict({"id": "m1", "channelId": "c1", "content": ""})
    assert message.author is None
    assert message.reply_to is None
    assert message.attachments == []


def test_poll_closed_flag():
    assert Poll.from_dict({"closedAt": "2026-01-01T00:00:00Z"}).is_closed
    assert not Poll.from_dict({}).is_closed
