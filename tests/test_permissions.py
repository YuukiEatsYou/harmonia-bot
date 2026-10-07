from harmonia.permissions import Permissions as P


def test_from_value_parses_decimal_string():
    assert P.from_value("2") == P.SEND_MESSAGES
    assert P.from_value(2081) == P.from_value("2081")
    assert P.from_value(None) == P.NONE


def test_to_value_round_trips():
    value = P.VIEW_CHANNELS | P.SEND_MESSAGES | P.MANAGE_MESSAGES
    assert P.from_value(value.to_value()) == value


def test_has_requires_every_flag():
    combined = P.VIEW_CHANNELS | P.SEND_MESSAGES
    assert combined.has(P.VIEW_CHANNELS, P.SEND_MESSAGES)
    assert not combined.has(P.VIEW_CHANNELS, P.BAN_MEMBERS)


def test_administrator_implies_everything():
    assert P.ADMINISTRATOR.has(P.BAN_MEMBERS, P.MANAGE_SERVER)
    assert P.from_value(P.ADMINISTRATOR.to_value()).has(P.MANAGE_ROLES)


def test_unknown_bits_are_preserved():
    # A flag a newer server knows that this framework does not.
    unknown = 1 << 20
    parsed = P.from_value(unknown)
    assert int(parsed) == unknown


def test_empty_check_passes():
    assert P.NONE.has()
