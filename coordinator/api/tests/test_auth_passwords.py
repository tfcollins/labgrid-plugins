from app.auth.passwords import hash_password, verify_password


def test_hash_and_verify_round_trip():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_hash_unique_per_call():
    assert hash_password("x") != hash_password("x")


def test_verify_handles_invalid_hash():
    assert verify_password("anything", "not-a-real-hash") is False
