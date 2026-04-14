"""SQLiteFingerprintRepo 测试"""
import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import SQLiteFingerprintRepo, new_connection
    conn = new_connection(":memory:")
    return SQLiteFingerprintRepo(conn)


def test_save_and_load(repo):
    repo.fingerprint_save("example.com", "#btn", {"tag": "button", "text": "Submit"})
    fp = repo.fingerprint_load("example.com", "#btn")
    assert fp is not None
    assert fp["tag"] == "button"


def test_load_not_found(repo):
    assert repo.fingerprint_load("x.com", "nope") is None


def test_domain_isolation(repo):
    repo.fingerprint_save("a.com", "#btn", {"v": 1})
    repo.fingerprint_save("b.com", "#btn", {"v": 2})
    assert repo.fingerprint_load("a.com", "#btn")["v"] == 1
    assert repo.fingerprint_load("b.com", "#btn")["v"] == 2


def test_delete(repo):
    repo.fingerprint_save("x.com", "#btn", {"v": 1})
    assert repo.fingerprint_delete("x.com", "#btn") is True
    assert repo.fingerprint_load("x.com", "#btn") is None
    assert repo.fingerprint_delete("x.com", "#btn") is False
