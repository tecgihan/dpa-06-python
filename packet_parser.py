"""DPA-06 の NOW 応答・測定パケットの解析。

測定パケットのフォーマット（ファームウェア ``buffer.c`` で確定）::

    [0xAA × 4]                       ヘッダ
    [6ch × 符号付き int16 LE] × まとめ数   ボディ
    [0x55 × 4]                       フッタ

    packet_size = 4 + 6 * 2 * matome + 4

* 値は符号付き 16bit（FW の ``short``、ADCGetDAData の出力）。
* バッファオーバーフロー時、デバイスは全 0 のパケット（ヘッダ無し）を返す。
* NOW 応答は 6ch × int16 LE の 12 バイト（ヘッダ／フッタ無し）。
"""

from __future__ import annotations

import numpy as np

# 定数
CH_COUNT = 6
HEADER = b"\xAA\xAA\xAA\xAA"
FOOTER = b"\x55\x55\x55\x55"
HEADER_SIZE = len(HEADER)
FOOTER_SIZE = len(FOOTER)
NOW_SIZE = CH_COUNT * 2  # 12 バイト

# 工学値変換の満点（DPA-06 のサンプルソフトに準拠：AD 値 32000 がフルスケール）
FULL_SCALE_COUNT = 32000.0


def ad_to_eng(ad, full_scale) -> np.ndarray:
    """AD 値を工学値（物理量）へ変換する。

    DPA-06 標準ソフトの換算式に準拠::

        eng = ad * full_scale / 32000

    Parameters
    ----------
    ad:
        ``(..., 6)`` 形状の AD 値（符号付き int16 想定）。
    full_scale:
        出力チャンネル順（Fx, Fy, Fz, Mx, My, Mz）のフルスケール 6 値。
    """
    fs = np.asarray(full_scale, dtype=float)
    if fs.shape[-1] != CH_COUNT:
        raise ValueError(f"full_scale は {CH_COUNT} 要素必要です。")
    return np.asarray(ad, dtype=float) * fs / FULL_SCALE_COUNT


class PacketError(Exception):
    """パケット解析に関するエラー。"""


def packet_size(matome: int) -> int:
    """まとめ数からパケット全体のバイト数を求める。"""
    return HEADER_SIZE + CH_COUNT * 2 * matome + FOOTER_SIZE


def body_size(matome: int) -> int:
    """ボディ（AD 値部）のバイト数を求める。"""
    return CH_COUNT * 2 * matome


def parse_robot_hex(line: str) -> np.ndarray:
    """ロボットモードの 1 サンプル（16進 ASCII）を ``(6,)`` int16 で返す。

    ファームウェア ``measure.c`` の ``ToStr`` は、各チャンネル（符号付き
    16bit）を上位ニブルから 4 桁の大文字 16 進で出力する。6ch で 24 文字。
    """
    line = line.strip()
    if len(line) != CH_COUNT * 4:
        raise PacketError(f"ロボットサンプル長が不正です: {len(line)} (期待値 {CH_COUNT * 4})")
    values = []
    for i in range(CH_COUNT):
        word = int(line[i * 4:i * 4 + 4], 16)
        if word >= 0x8000:  # 2 の補数で符号付き化
            word -= 0x10000
        values.append(word)
    return np.array(values, dtype=np.int16)


def parse_now(raw: bytes) -> np.ndarray:
    """NOW 応答（12 バイト）を ``(6,)`` の符号付き int16 配列に変換する。"""
    if len(raw) != NOW_SIZE:
        raise PacketError(f"NOW データ長が不正です: {len(raw)} (期待値 {NOW_SIZE})")
    return np.frombuffer(raw, dtype="<i2").copy()


def parse_packet(raw: bytes, matome: int) -> np.ndarray:
    """1 パケットを ``(matome, 6)`` の符号付き int16 配列に変換する。

    ヘッダ／フッタを検証する。``raw`` はちょうど 1 パケット分であること。
    """
    expected = packet_size(matome)
    if len(raw) != expected:
        raise PacketError(f"パケット長が不正です: {len(raw)} (期待値 {expected})")
    if raw[:HEADER_SIZE] != HEADER:
        raise PacketError(f"ヘッダ不正: {raw[:HEADER_SIZE].hex()}")
    if raw[-FOOTER_SIZE:] != FOOTER:
        raise PacketError(f"フッタ不正: {raw[-FOOTER_SIZE:].hex()}")

    body = raw[HEADER_SIZE:HEADER_SIZE + body_size(matome)]
    values = np.frombuffer(body, dtype="<i2")
    return values.reshape(matome, CH_COUNT).copy()


def find_packet(buffer: bytes, matome: int) -> tuple[np.ndarray | None, int]:
    """バイト列の先頭からヘッダを探し、見つかれば 1 パケットを解析する。

    Returns
    -------
    (data, consumed):
        ``data`` は解析できたパケット（``None`` ならまだ揃っていない）。
        ``consumed`` は ``buffer`` から消費してよいバイト数。
    """
    size = packet_size(matome)
    idx = buffer.find(HEADER)
    if idx < 0:
        # ヘッダが無い。末尾の途中ヘッダ可能性分だけ残して破棄。
        keep = HEADER_SIZE - 1
        return None, max(0, len(buffer) - keep)
    if len(buffer) - idx < size:
        # ヘッダ位置以降のゴミだけ捨てる
        return None, idx
    raw = buffer[idx:idx + size]
    data = parse_packet(raw, matome)
    return data, idx + size
