"""パケット解析テスト（ハードウェア不要）。

合成したバイト列を使って、符号付き int16 の復元・ヘッダ／フッタ検証・
ストリーム同期（先頭のゴミ除去）が正しく動くことを確認する。

使い方::

    python test_packet_parser.py
"""

from __future__ import annotations

import struct

import numpy as np

import packet_parser as pp


def build_packet(samples: list[list[int]]) -> bytes:
    """``samples`` (各要素 6ch) からパケットバイト列を組み立てる。"""
    body = b"".join(struct.pack("<6h", *s) for s in samples)
    return pp.HEADER + body + pp.FOOTER


def test_parse_now_signed() -> None:
    raw = struct.pack("<6h", 0, 1, -1, 32767, -32768, 1234)
    arr = pp.parse_now(raw)
    assert arr.dtype == np.int16
    assert list(arr) == [0, 1, -1, 32767, -32768, 1234]
    print("  parse_now: OK")


def test_parse_packet_shape_and_values() -> None:
    matome = 3
    samples = [
        [1, 2, 3, 4, 5, 6],
        [-1, -2, -3, -4, -5, -6],
        [32767, -32768, 0, 100, -100, 200],
    ]
    raw = build_packet(samples)
    assert len(raw) == pp.packet_size(matome)
    data = pp.parse_packet(raw, matome)
    assert data.shape == (matome, pp.CH_COUNT)
    assert np.array_equal(data, np.array(samples, dtype=np.int16))
    print("  parse_packet: OK")


def test_bad_header_footer() -> None:
    matome = 2
    raw = bytearray(build_packet([[0] * 6, [0] * 6]))
    # ヘッダ破壊
    bad = bytes([0x00]) + bytes(raw[1:])
    try:
        pp.parse_packet(bad, matome)
    except pp.PacketError:
        print("  bad header detected: OK")
    else:
        raise AssertionError("ヘッダ不正を検出できませんでした")
    # フッタ破壊
    bad = bytes(raw[:-1]) + bytes([0x00])
    try:
        pp.parse_packet(bad, matome)
    except pp.PacketError:
        print("  bad footer detected: OK")
    else:
        raise AssertionError("フッタ不正を検出できませんでした")


def test_find_packet_with_garbage() -> None:
    matome = 2
    pkt = build_packet([[7, 8, 9, 10, 11, 12], [13, 14, 15, 16, 17, 18]])
    stream = b"\x12\x34garbage" + pkt + b"\xAA\xAA"  # 末尾に途中ヘッダ
    data, consumed = pp.find_packet(stream, matome)
    assert data is not None, "パケットを見つけられませんでした"
    assert np.array_equal(data[0], np.array([7, 8, 9, 10, 11, 12], dtype=np.int16))
    # 消費後の残りに次ヘッダ候補が残ること
    rest = stream[consumed:]
    assert rest == b"\xAA\xAA"
    print("  find_packet (sync over garbage): OK")


def test_parse_robot_hex() -> None:
    # 0001=1, FFFF=-1, 7FFF=32767, 8000=-32768, 0064=100, FF9C=-100
    line = "0001FFFF7FFF80000064FF9C"
    arr = pp.parse_robot_hex(line)
    assert arr.dtype == np.int16
    assert list(arr) == [1, -1, 32767, -32768, 100, -100], list(arr)
    print("  parse_robot_hex: OK")


def test_ad_to_eng() -> None:
    ad = np.array([[32000, -32000, 16000, 0, 1, -1]], dtype=np.int16)
    fs = [750, 750, 1500, 12, 12, 6]
    eng = pp.ad_to_eng(ad, fs)
    # 32000 が満点 → FS と一致
    assert np.isclose(eng[0, 0], 750.0)
    assert np.isclose(eng[0, 1], -750.0)
    assert np.isclose(eng[0, 2], 750.0)  # 16000/32000*1500
    print("  ad_to_eng: OK")


def main() -> int:
    print("== packet_parser テスト ==")
    test_parse_now_signed()
    test_parse_packet_shape_and_values()
    test_bad_header_footer()
    test_find_packet_with_garbage()
    test_parse_robot_hex()
    test_ad_to_eng()
    print("すべて成功しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
