import json

import pytest

from app.recordings.writer import CastWriter


@pytest.mark.asyncio
async def test_writer_emits_valid_header(tmp_path):
    p = tmp_path / "x.cast"
    w = CastWriter(str(p), title="vcu118/serial")
    await w.start()
    await w.close()
    lines = p.read_text().splitlines()
    header = json.loads(lines[0])
    assert header["version"] == 2
    assert header["title"] == "vcu118/serial"


@pytest.mark.asyncio
async def test_writer_records_output_and_input(tmp_path):
    p = tmp_path / "x.cast"
    w = CastWriter(str(p), title="t")
    await w.start()
    await w.write_output(b"hello\n")
    await w.write_input(b"x")
    await w.close()
    lines = p.read_text().splitlines()
    assert len(lines) >= 3
    ev1 = json.loads(lines[1])
    ev2 = json.loads(lines[2])
    assert ev1[1] == "o" and "hello" in ev1[2]
    assert ev2[1] == "i" and ev2[2] == "x"


@pytest.mark.asyncio
async def test_writer_handles_non_utf8_bytes(tmp_path):
    p = tmp_path / "x.cast"
    w = CastWriter(str(p), title="t")
    await w.start()
    await w.write_output(b"\xff\xfe\xfd")
    await w.close()
    lines = p.read_text().splitlines()
    ev = json.loads(lines[1])
    assert ev[1] == "o"
    encoded = ev[2]
    assert isinstance(encoded, str)


@pytest.mark.asyncio
async def test_writer_byte_count(tmp_path):
    p = tmp_path / "x.cast"
    w = CastWriter(str(p), title="t")
    await w.start()
    await w.write_output(b"abc")
    await w.write_output(b"de")
    assert w.byte_count == 5
    await w.close()
