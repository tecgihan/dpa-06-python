"""FTDI D2XX communication helper for the DPA-06.

DPA-06 は FTDI の D2XX ドライバ経由で USB 通信を行う。
本モジュールは ``ftd2xx`` パッケージを薄くラップし、
DPA-06 のコマンドプロトコル（ASCII コマンド＋バイナリパケット）に
必要な送受信ユーティリティを提供する。
"""

from __future__ import annotations

import time
from typing import Optional

try:
    import ftd2xx
    import ftd2xx.defines as ftd_defines
except ImportError:  # pragma: no cover - ftd2xx 未インストール環境でのみ通る
    ftd2xx = None
    ftd_defines = None


class FtdiError(IOError):
    """FTDI 通信に関するエラー。"""


class FtdiComm:
    """DPA-06 用 FTDI D2XX 通信ラッパ。

    既存のテック技販製ライブラリと同様、デバイスは Description
    （既定で ``"DPA-06"``）でオープンする。
    """

    DEVICE_NAME = "DPA-06"
    LATENCY_MS = 1
    IN_TRANSFER_SIZE = 64 * 1024
    RX_TIMEOUT_MS = 1000
    TX_TIMEOUT_MS = 1000

    def __init__(self) -> None:
        self.device = None

    # ------------------------------------------------------------------
    # デバイス列挙
    # ------------------------------------------------------------------
    @staticmethod
    def _require_ftd2xx() -> None:
        if ftd2xx is None:
            raise FtdiError(
                "ftd2xx がインストールされていません。"
                "`pip install -r requirements.txt` を実行してください。"
            )

    @staticmethod
    def _decode(value) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    @classmethod
    def list_devices(cls) -> list[dict]:
        """接続されている全 FTDI デバイスの情報を返す。"""
        cls._require_ftd2xx()
        devices: list[dict] = []
        for index in range(ftd2xx.createDeviceInfoList()):
            info = ftd2xx.getDeviceInfoDetail(index)
            devices.append(
                {
                    "index": info["index"],
                    "serial": cls._decode(info.get("serial", "")),
                    "description": cls._decode(info.get("description", "")),
                    "flags": info.get("flags"),
                }
            )
        return devices

    @classmethod
    def list_target_devices(cls) -> list[dict]:
        """Description に ``DEVICE_NAME`` を含むデバイスのみ返す。"""
        return [
            d for d in cls.list_devices() if cls.DEVICE_NAME in d.get("description", "")
        ]

    # ------------------------------------------------------------------
    # オープン / クローズ
    # ------------------------------------------------------------------
    def open_by_description(self, description: Optional[str] = None) -> None:
        """Description でデバイスをオープンして USB パラメータを設定する。"""
        self._require_ftd2xx()
        if description is None:
            description = self.DEVICE_NAME
        self.close()
        self.device = ftd2xx.openEx(
            description.encode("utf-8"), ftd_defines.OPEN_BY_DESCRIPTION
        )
        self.configure()

    def open_by_index(self, index: int = 0) -> None:
        """インデックス指定でデバイスをオープンする。"""
        self._require_ftd2xx()
        self.close()
        self.device = ftd2xx.open(index)
        self.configure()

    def configure(self) -> None:
        """DPA-06 既定の USB パラメータを適用する。"""
        if self.device is None:
            return
        self.device.setTimeouts(self.RX_TIMEOUT_MS, self.TX_TIMEOUT_MS)
        self.device.setLatencyTimer(self.LATENCY_MS)
        self.device.setUSBParameters(self.IN_TRANSFER_SIZE, self.IN_TRANSFER_SIZE)
        self.purge()
        time.sleep(0.1)

    def close(self) -> None:
        if self.device is not None:
            try:
                self.purge()
                self.device.close()
            finally:
                self.device = None

    def is_open(self) -> bool:
        return self.device is not None

    def purge(self) -> None:
        """送受信バッファをクリアする。"""
        if self.device is not None:
            self.device.purge(ftd_defines.PURGE_RX | ftd_defines.PURGE_TX)

    # ------------------------------------------------------------------
    # 低レベル送受信
    # ------------------------------------------------------------------
    def write(self, data: bytes) -> None:
        if self.device is None:
            raise FtdiError("デバイスがオープンされていません。")
        written = self.device.write(data)
        if written != len(data):
            raise FtdiError(f"書き込み不足: {written}/{len(data)} バイト")

    def read(self, size: int) -> bytes:
        if self.device is None:
            raise FtdiError("デバイスがオープンされていません。")
        return self.device.read(size)

    def bytes_available(self) -> int:
        """受信キューにあるバイト数を返す。"""
        if self.device is None:
            return 0
        rx_queue, _tx_queue, _event = self.device.getStatus()
        return int(rx_queue)

    # ------------------------------------------------------------------
    # コマンド送受信
    # ------------------------------------------------------------------
    def send_command(self, command: str) -> None:
        """ASCII コマンドを LF 終端で送信する。"""
        if not command.endswith("\n"):
            command += "\n"
        self.write(command.encode("ascii"))

    def read_line(self, timeout: float = 1.0) -> str:
        """LF までの 1 行を読み取り、前後の空白を除いて返す。"""
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            if self.bytes_available() <= 0:
                time.sleep(0.001)
                continue
            chunk = self.read(1)
            if not chunk:
                continue
            buf += chunk
            if chunk == b"\n":
                return buf.decode("ascii", errors="replace").strip()
        raise TimeoutError("応答待ちタイムアウト")

    def command_reply(self, command: str, timeout: float = 1.0) -> str:
        """コマンドを送り、1 行の応答を返す。"""
        self.send_command(command)
        return self.read_line(timeout)

    def read_until_token(self, tokens: list[str], timeout: float = 2.0) -> str:
        """受信ストリームから ``tokens`` のいずれかが現れるまで読み飛ばす。

        測定中のバイナリ／ロボットモードのストリームと、制御コマンドの
        ASCII 応答が混在する状況で、応答トークン（例 ``STOP_OK``）を
        確実に拾うために使う。見つかったトークン文字列を返す。
        """
        token_bytes = [t.encode("ascii") for t in tokens]
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            available = self.bytes_available()
            if available <= 0:
                time.sleep(0.001)
                continue
            buf += self.read(available)
            for token, raw in zip(tokens, token_bytes):
                if raw in buf:
                    return token
            # バッファの肥大化を防ぐ（トークン途中の取りこぼし分だけ残す）
            cap = 65536
            if len(buf) > cap:
                keep = max(len(r) for r in token_bytes) - 1
                if keep > 0:
                    del buf[:-keep]
                else:
                    buf.clear()
        raise TimeoutError(f"トークン待ちタイムアウト: {tokens}")

    def read_exact(self, size: int, timeout: float = 1.0) -> bytes:
        """``size`` バイトちょうど読み取れるまで待つ。"""
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while len(buf) < size and time.monotonic() < deadline:
            available = self.bytes_available()
            if available <= 0:
                time.sleep(0.001)
                continue
            buf += self.read(min(size - len(buf), available))
        if len(buf) != size:
            raise TimeoutError(f"{size} バイト待ちタイムアウト（取得 {len(buf)}）")
        return bytes(buf)
