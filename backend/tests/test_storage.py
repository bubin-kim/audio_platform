"""LocalStorage 라운드트립·안전성 테스트."""

from pathlib import Path

import pytest

from app.storage.local import LocalStorage


def test_save_and_read_bytes(storage: LocalStorage) -> None:
    logical = storage.save("uploads/1/a.wav", b"hello-audio")
    assert logical == "uploads/1/a.wav"
    assert storage.exists("uploads/1/a.wav")
    assert storage.read("uploads/1/a.wav") == b"hello-audio"


def test_save_from_path(storage: LocalStorage, tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    src.write_bytes(b"data")
    storage.save_from_path("segments/2/s.wav", src)
    assert storage.read("segments/2/s.wav") == b"data"


def test_local_path_is_real_file(storage: LocalStorage) -> None:
    storage.save("uploads/x.bin", b"abc")
    p = storage.local_path("uploads/x.bin")
    assert p.exists() and p.read_bytes() == b"abc"


def test_delete_is_idempotent(storage: LocalStorage) -> None:
    storage.save("uploads/del.bin", b"z")
    storage.delete("uploads/del.bin")
    assert not storage.exists("uploads/del.bin")
    storage.delete("uploads/del.bin")  # 없어도 예외 없음


def test_list_with_prefix(storage: LocalStorage) -> None:
    storage.save("segments/1/a.wav", b"1")
    storage.save("segments/1/b.wav", b"2")
    storage.save("uploads/c.wav", b"3")
    assert storage.list("segments") == ["segments/1/a.wav", "segments/1/b.wav"]
    assert len(storage.list()) == 3


def test_path_traversal_rejected(storage: LocalStorage) -> None:
    with pytest.raises(ValueError):
        storage.save("../escape.txt", b"nope")
