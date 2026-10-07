from harmonia.commands.parser import split_flags, tokenize


def test_plain_split():
    assert tokenize("a b c") == ["a", "b", "c"]


def test_double_quotes_group_spaces():
    assert tokenize('"hello world" again') == ["hello world", "again"]


def test_single_quotes_and_mixed():
    assert tokenize("'one two' three") == ["one two", "three"]


def test_empty_string_yields_no_tokens():
    assert tokenize("") == []


def test_empty_quotes_yield_an_empty_token():
    assert tokenize('""') == [""]


def test_unterminated_quote_keeps_the_rest():
    assert tokenize('"unterminated') == ["unterminated"]


def test_flags_split_from_positionals():
    positional, flags = split_flags(["--a=1", "--b", "c", "d"])
    assert positional == ["c", "d"]
    assert flags == {"a": "1", "b": True}


def test_flag_value_may_contain_spaces():
    positional, flags = split_flags([*tokenize('--reason="a b c"'), "bob"])
    assert positional == ["bob"]
    assert flags == {"reason": "a b c"}
