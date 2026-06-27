"""DPA-06 control library.

テック技販製 6 軸力覚センサ用アンプ **DPA-06** を Python から制御するための
メインモジュール。既存ライブラリ（forceplate-python / dss300-hr-python など）と
同じ作法で、FTDI D2XX 経由の ASCII コマンド／バイナリパケット通信を扱う。

このモジュールは段階的に拡張する。現時点では以下をサポートする:

* 接続 / 切断
* システムステータス取得
* デバイス情報（シリアル / レビジョン / バージョン / 周波数 / まとめ数）の読み取り
"""

from __future__ import annotations

import time
from enum import Enum, IntEnum
from typing import Optional

import numpy as np

from ftdi_comm import FtdiComm, FtdiError
from packet_parser import (
    NOW_SIZE,
    ad_to_eng,
    find_packet,
    packet_size,
    parse_now,
    parse_robot_hex,
)

# ロボット用機能が使えるファームウェアの最小バージョン
FOR_ROBOT_MIN_VERSION = (1, 3, 0)


class Dpa06Error(Exception):
    """DPA-06 ライブラリの基底例外。"""


class NotConnectedError(Dpa06Error):
    """未接続状態で操作しようとした。"""


class CommandError(Dpa06Error):
    """コマンドが NG 応答・想定外応答を返した。"""


class Status(Enum):
    """システムステータス（``GET_STATUS`` 応答に対応）。"""

    NO_DEVICE = "NO_DEVICE"   # 未接続（ライブラリ内部状態）
    IDLE = "STATUS_IDLE"      # 待機中
    EXT = "STATUS_EXT"        # 外部トリガ待ち受け中
    LEVEL = "STATUS_LEVEL"    # レベルトリガ待ち受け中
    MEASURE = "STATUS_MEASURE"  # 測定中
    ZERO = "STATUS_ZERO"      # ゼロ調整中
    ERR = "STATUS_ERR"        # エラー発生

    @classmethod
    def from_reply(cls, reply: str) -> "Status":
        for status in cls:
            if status.value == reply:
                return status
        raise CommandError(f"未知のステータス応答: {reply!r}")


class InCh(IntEnum):
    """入力チャンネル（ロードセル入力）。"""

    Fx1 = 0
    Fy1 = 1
    Fz1 = 2
    Fx2 = 3
    Fy2 = 4
    Fz2 = 5


class OutCh(IntEnum):
    """出力チャンネル（6 軸合力出力）。"""

    Fx = 0
    Fy = 1
    Fz = 2
    Mx = 3
    My = 4
    Mz = 5


# チャンネル数
IN_CH_COUNT = len(InCh)
OUT_CH_COUNT = len(OutCh)

# ファームウェアが受け付ける値（command.c より）
VALID_FREQUENCIES = (240, 100, 500, 1000, 5000, 10000)
VALID_MATOME = (24, 10, 50, 100, 500, 1000)


class Dpa06:
    """DPA-06 制御クラス。"""

    def __init__(self, reply_timeout: float = 1.0) -> None:
        self._comm = FtdiComm()
        self._reply_timeout = reply_timeout
        self._matome: Optional[int] = None
        self._full_scale: Optional[list[float]] = None
        self._rx_buffer = bytearray()

    # ------------------------------------------------------------------
    # 接続管理
    # ------------------------------------------------------------------
    @staticmethod
    def list_devices() -> list[dict]:
        """接続中の DPA-06 デバイス一覧を返す。"""
        return FtdiComm.list_target_devices()

    def connect(self, description: Optional[str] = None, index: Optional[int] = None) -> None:
        """デバイスへ接続する。

        ``index`` を指定するとインデックスで、そうでなければ Description
        （既定で ``"DPA-06"``）でオープンする。
        """
        if index is not None:
            self._comm.open_by_index(index)
        else:
            self._comm.open_by_description(description)

    def disconnect(self) -> None:
        """デバイスを切断する。"""
        self._comm.close()

    def is_open(self) -> bool:
        return self._comm.is_open()

    def __enter__(self) -> "Dpa06":
        if not self.is_open():
            self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # 低レベルコマンドヘルパ
    # ------------------------------------------------------------------
    def _ensure_open(self) -> None:
        if not self._comm.is_open():
            raise NotConnectedError("デバイスが接続されていません。")

    def _query(self, item: str) -> str:
        """``GET_<item>`` を送り、``<item>_<値>`` の値部分を返す。"""
        self._ensure_open()
        reply = self._comm.command_reply(f"GET_{item}", self._reply_timeout)
        prefix = f"{item}_"
        if not reply.startswith(prefix):
            raise CommandError(f"GET_{item} に対する想定外の応答: {reply!r}")
        return reply[len(prefix):]

    def _command_ok(self, name: str) -> None:
        """制御コマンド ``name`` を送り、``<name>_OK`` 応答を確認する。

        ``<name>_NG`` や想定外応答なら :class:`CommandError` を送出する。
        """
        self._ensure_open()
        reply = self._comm.command_reply(name, self._reply_timeout)
        if reply == f"{name}_OK":
            return
        if reply == f"{name}_NG":
            raise CommandError(f"{name} が拒否されました（{reply}）。"
                               "ステータスが IDLE か確認してください。")
        raise CommandError(f"{name} に対する想定外の応答: {reply!r}")

    # ------------------------------------------------------------------
    # ステータス / デバイス情報（読み取り専用）
    # ------------------------------------------------------------------
    def get_status(self) -> Status:
        """現在のシステムステータスを返す。"""
        self._ensure_open()
        reply = self._comm.command_reply("GET_STATUS", self._reply_timeout)
        return Status.from_reply(reply)

    def get_serial(self) -> str:
        """シリアル番号を返す。"""
        return self._query("SERIAL")

    def get_revision(self) -> str:
        """レビジョンを返す。"""
        return self._query("REVISION")

    def get_version(self) -> str:
        """ファームウェアバージョン文字列（例: ``Ver.1.3.0``）を返す。"""
        return self._query("VERSION")

    def get_frequency(self) -> int:
        """測定周波数 [Hz] を返す。"""
        return int(self._query("FREQUENCY"))

    def get_matome(self) -> int:
        """1 パケットあたりのまとめ数を返す。"""
        return int(self._query("MATOME"))

    @property
    def info(self) -> dict:
        """主要なデバイス情報をまとめて返す。"""
        return {
            "serial": self.get_serial(),
            "revision": self.get_revision(),
            "version": self.get_version(),
            "frequency": self.get_frequency(),
            "matome": self.get_matome(),
        }

    # ------------------------------------------------------------------
    # デバイスエラー（GET_ERROR でエラーキューを確認・排出）
    # ------------------------------------------------------------------
    def get_error(self) -> str:
        """エラーキューから 1 件取り出してエラー名を返す。

        デバイスは発生したエラーを RAM のキューに保持し、``GET_ERROR`` で
        1 件ずつ取り出すと消費される。キューが空のときは ``"NO_ERROR"`` を返す。
        応答 ``ERROR_<名前>`` の ``ERROR_`` を除いた名前（例 ``"DATA_ERROR"``）。
        """
        self._ensure_open()
        reply = self._comm.command_reply("GET_ERROR", self._reply_timeout)
        prefix = "ERROR_"
        if not reply.startswith(prefix):
            raise CommandError(f"GET_ERROR に対する想定外の応答: {reply!r}")
        return reply[len(prefix):]

    def has_error(self) -> bool:
        """キューにエラーがあるかを返す（1 件消費する点に注意）。"""
        return self.get_error() != "NO_ERROR"

    def clear_errors(self, limit: int = 10000) -> list[str]:
        """エラーキューを空になるまで読み出し、取り出したエラー名のリストを返す。

        ``limit`` は安全のための上限読み出し回数。戻り値が空なら元から
        エラーは無かったことを意味する。
        """
        errors: list[str] = []
        for _ in range(limit):
            name = self.get_error()
            if name == "NO_ERROR":
                break
            errors.append(name)
        return errors

    # ------------------------------------------------------------------
    # 現在値取得（NOW）
    # ------------------------------------------------------------------
    def get_now(self) -> np.ndarray:
        """現在の出力値を ``(6,)`` の符号付き int16 配列で返す。

        ``NOW`` コマンドはバイナリ 12 バイト（6ch × int16 LE）を返す。
        IDLE 以外のステータスではダミー（全 0）が返る点に注意。
        """
        self._ensure_open()
        self._comm.purge()
        self._comm.send_command("NOW")
        raw = self._comm.read_exact(NOW_SIZE, self._reply_timeout)
        return parse_now(raw)

    # ------------------------------------------------------------------
    # 測定制御
    # ------------------------------------------------------------------
    def start(self) -> None:
        """通常測定を開始する（``START``）。"""
        self._prepare_measure()
        self._command_ok("START")

    def stop(self, timeout: float = 2.0) -> None:
        """測定を停止する（``STOP``）。

        測定中はバイナリパケットやロボットモードのサンプルがストリーム
        送信されているため、それらを読み飛ばして ``STOP_OK`` を確実に拾う。
        停止後は受信バッファを破棄する。
        """
        self._ensure_open()
        self._comm.send_command("STOP")
        token = self._comm.read_until_token(["STOP_OK", "STOP_NG"], timeout)
        if token == "STOP_NG":
            raise CommandError("STOP が拒否されました（STOP_NG）。")
        # 残ったストリームデータを破棄
        self._rx_buffer.clear()
        self._comm.purge()

    def ext(self) -> None:
        """外部トリガ待ち受け状態へ移行する（``EXT``）。"""
        self._prepare_measure()
        self._command_ok("EXT")

    def level(self) -> None:
        """レベルトリガ待ち受け状態へ移行する（``LEVEL``）。"""
        self._prepare_measure()
        self._command_ok("LEVEL")

    def trig(self) -> None:
        """ソフトウェアトリガを出力する（``TRIG``）。"""
        self._command_ok("TRIG")

    def _prepare_measure(self) -> None:
        """測定開始前の準備：まとめ数・フルスケールをキャッシュしバッファを空にする。"""
        self._matome = self.get_matome()
        self._full_scale = self.get_fs()
        self._rx_buffer.clear()
        self._comm.purge()

    # ------------------------------------------------------------------
    # 測定データ取得
    # ------------------------------------------------------------------
    @property
    def matome(self) -> Optional[int]:
        """直近の測定開始時にキャッシュしたまとめ数。"""
        return self._matome

    def packet_size(self) -> int:
        """現在のまとめ数に対するパケットサイズ [byte]。"""
        if self._matome is None:
            raise Dpa06Error("まとめ数が未確定です。start()/ext() を先に呼んでください。")
        return packet_size(self._matome)

    def read_packet(self, timeout: float = 2.0) -> np.ndarray:
        """測定パケットを 1 つ読み取り ``(matome, 6)`` の int16 配列で返す。

        ヘッダ同期・フッタ検証を行う。タイムアウト時は :class:`TimeoutError`。
        """
        self._ensure_open()
        if self._matome is None:
            self._matome = self.get_matome()
        matome = self._matome
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data, consumed = find_packet(bytes(self._rx_buffer), matome)
            if consumed:
                del self._rx_buffer[:consumed]
            if data is not None:
                return data
            available = self._comm.bytes_available()
            if available > 0:
                self._rx_buffer += self._comm.read(available)
            else:
                time.sleep(0.001)
        raise TimeoutError("測定パケット待ちタイムアウト")

    def read_packets(self, count: int, timeout: float = 2.0) -> list[np.ndarray]:
        """``count`` 個のパケットを読み取って返す。"""
        return [self.read_packet(timeout) for _ in range(count)]

    def measure(self, num_packets: int, timeout: float = 2.0) -> np.ndarray:
        """START → ``num_packets`` 取得 → STOP を行い、連結データを返す。

        戻り値は ``(num_packets * matome, 6)`` の符号付き int16 配列。
        """
        self.start()
        try:
            packets = self.read_packets(num_packets, timeout)
        finally:
            self.stop()
        return np.concatenate(packets, axis=0)

    # ------------------------------------------------------------------
    # 工学値変換
    # ------------------------------------------------------------------
    def ad_to_eng(self, ad, full_scale: Optional[list[float]] = None) -> np.ndarray:
        """AD 値を工学値へ変換する（``eng = ad * FS / 32000``）。

        ``full_scale`` 省略時は直近の測定開始時にキャッシュした FS を使う。
        キャッシュが無く IDLE 状態であれば ``GET_FS`` で取得する。
        """
        if full_scale is None:
            full_scale = self._full_scale
            if full_scale is None:
                full_scale = self.get_fs()
                self._full_scale = full_scale
        return ad_to_eng(ad, full_scale)

    # ------------------------------------------------------------------
    # パラメータ読み取り（校正値・出力設定・干渉補正）
    # ------------------------------------------------------------------
    def _query_floats(self, item: str) -> list[float]:
        """``GET_<item>`` を送り、カンマ区切りの値群を float リストで返す。"""
        value = self._query(item)
        return [float(v) for v in value.split(",")]

    def get_force_zero(self) -> list[float]:
        """力覚センサ（ロードセル）ゼロ点 6 値を返す（読み取り専用）。"""
        return self._query_floats("FORCE_ZERO")

    def get_level(self) -> list[float]:
        """レベルトリガ値 6 値（出力チャンネル順）を返す。"""
        return self._query_floats("LEVEL")

    def get_fs(self) -> list[float]:
        """フルスケール 6 値（出力チャンネル順）を返す。"""
        return self._query_floats("FS")

    def get_itf(self, item: int) -> float:
        """干渉補正係数の 1 要素を返す（item: 0..35 = 出力ch * 6 + 入力ch）。

        内部的には ``GET_ITF_6X12_xx`` を送る（応答は ``ITF_6X12_<値>``）。
        item は 6 軸センサで有効な 6x6 の範囲（0..35）に対応し、これが実際の
        力演算（ファームウェアの CalcK）で使われる干渉補正行列。
        """
        if not 0 <= item <= 35:
            raise ValueError("ITF の item は 0..35（出力ch * 6 + 入力ch）の範囲です。")
        self._ensure_open()
        reply = self._comm.command_reply(f"GET_ITF_6X12_{item:02d}", self._reply_timeout)
        prefix = "ITF_6X12_"
        if not reply.startswith(prefix):
            raise CommandError(f"GET_ITF_6X12_{item:02d} に対する想定外の応答: {reply!r}")
        return float(reply[len(prefix):])

    def get_itf_matrix(self) -> np.ndarray:
        """干渉補正行列 6x6 を ``[out][in]`` の行列として返す。

        ``item = out * 6 + in`` で item 0..35 を読む（36 回 GET）。
        """
        values = [self.get_itf(out * IN_CH_COUNT + inp)
                  for out in range(OUT_CH_COUNT) for inp in range(IN_CH_COUNT)]
        return np.array(values, dtype=float).reshape(OUT_CH_COUNT, IN_CH_COUNT)

    # ------------------------------------------------------------------
    # 設定書き込み（SET 系）
    #   いずれも応答 SET_<BASE>_OK / SET_<BASE>_NG。
    #   校正・干渉補正・出力設定は IDLE 状態でのみ受け付けられる。
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_float(value: float) -> str:
        """SET コマンド用に float を精度を保って文字列化する。"""
        return format(float(value), ".9g")

    def _send_set(self, command: str, ok_base: str) -> None:
        self._ensure_open()
        reply = self._comm.command_reply(command, self._reply_timeout)
        if reply == f"SET_{ok_base}_OK":
            return
        if reply == f"SET_{ok_base}_NG":
            raise CommandError(
                f"{command} が拒否されました（SET_{ok_base}_NG）。"
                "値の範囲・チャンネル・ステータス(IDLE)を確認してください。"
            )
        raise CommandError(f"{command} に対する想定外の応答: {reply!r}")

    def set_frequency(self, freq: int) -> None:
        """測定周波数 [Hz] を設定する。"""
        if freq not in VALID_FREQUENCIES:
            raise ValueError(f"周波数は {VALID_FREQUENCIES} のいずれかです。")
        self._send_set(f"SET_FREQUENCY_{int(freq)}", "FREQUENCY")

    def set_matome(self, matome: int) -> None:
        """1 パケットあたりのまとめ数を設定する。"""
        if matome not in VALID_MATOME:
            raise ValueError(f"まとめ数は {VALID_MATOME} のいずれかです。")
        self._send_set(f"SET_MATOME_{int(matome)}", "MATOME")

    def set_level(self, value: float, outch: OutCh) -> None:
        """レベルトリガ値を設定する（IDLE 時のみ）。"""
        self._send_set(f"SET_LEVEL_{int(outch)}_{self._fmt_float(value)}", "LEVEL")

    def set_fs(self, value: float, outch: OutCh) -> None:
        """フルスケールを設定する（IDLE 時のみ、value > 0）。"""
        if value <= 0:
            raise ValueError("フルスケールは正の値です。")
        self._send_set(f"SET_FS_{int(outch)}_{self._fmt_float(value)}", "FS")

    def set_itf(self, value: float, item: int) -> None:
        """干渉補正係数の 1 要素を設定する（item: 0..35 = 出力ch * 6 + 入力ch、IDLE 時のみ）。

        内部的には ``SET_ITF_6X12_xx`` を送る。この書き込みでファームウェアが
        係数を再計算（CalcK）し、以降の測定出力に反映される。
        """
        if not 0 <= item <= 35:
            raise ValueError("ITF の item は 0..35（出力ch * 6 + 入力ch）の範囲です。")
        self._send_set(f"SET_ITF_6X12_{item:02d}_{self._fmt_float(value)}", "ITF_6X12")

    def set_itf_matrix(self, matrix) -> None:
        """干渉補正行列 6x6 を一括設定する（``item = out * 6 + in``、IDLE 時のみ）。

        Parameters
        ----------
        matrix:
            ``(6, 6)`` 形状の行列。行=出力ch（Fx,Fy,Fz,Mx,My,Mz）、
            列=入力ch（検査成績書の行列係数 εFx..εMz の順）。
        """
        mat = np.asarray(matrix, dtype=float)
        if mat.shape != (OUT_CH_COUNT, IN_CH_COUNT):
            raise ValueError(f"matrix は ({OUT_CH_COUNT}, {IN_CH_COUNT}) 形状が必要です。")
        for out in range(OUT_CH_COUNT):
            for inp in range(IN_CH_COUNT):
                self.set_itf(mat[out, inp], out * IN_CH_COUNT + inp)

    # ------------------------------------------------------------------
    # ゼロ調整（デバイス内のゼロ点を更新する破壊的操作）
    # ------------------------------------------------------------------
    def zero(self) -> None:
        """ゼロ調整を開始する（``ZERO``）。

        注意: デバイス内部のゼロ点（FORCE_ZERO）を更新する。IDLE 時のみ。
        """
        self._command_ok("ZERO")

    def zero_and_wait(self, timeout: float = 10.0, poll: float = 0.2) -> None:
        """ゼロ調整を開始し、IDLE に戻るまで待つ。"""
        self.zero()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.get_status()
            if status == Status.IDLE:
                return
            if status == Status.ERR:
                raise CommandError("ゼロ調整中にエラーが発生しました。")
            time.sleep(poll)
        raise TimeoutError("ゼロ調整の完了待ちタイムアウト")

    # ------------------------------------------------------------------
    # ロボット用機能（FW >= 1.3.0）
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_version(version: str) -> tuple[int, ...]:
        """``Ver.1.3.0`` 等から数値タプル ``(1, 3, 0)`` を取り出す。"""
        digits = version.lstrip("Ver.").strip()
        try:
            return tuple(int(x) for x in digits.split("."))
        except ValueError:
            return (0,)

    def is_for_robot_available(self) -> bool:
        """ファームウェアがロボット用機能に対応しているか。"""
        return self._parse_version(self.get_version()) >= FOR_ROBOT_MIN_VERSION

    def get_for_robot(self) -> bool:
        """ロボット用モードが有効かどうかを返す。"""
        return self._query("FOR_ROBOT") == "1"

    def set_for_robot(self, enabled: bool) -> None:
        """ロボット用モードの ON/OFF を設定する（FW >= 1.3.0、IDLE 時のみ）。

        有効時、測定中はデバイスが 1 サンプルを 16 進 ASCII でストリーム送信する。
        """
        self._send_set(f"SET_FOR_ROBOT_{1 if enabled else 0}", "FOR_ROBOT")

    def get_robot_sample(self, timeout: float = 2.0) -> np.ndarray:
        """ロボットモードの 1 サンプルを ``(6,)`` int16 で読み取る。"""
        self._ensure_open()
        line = self._comm.read_line(timeout)
        return parse_robot_hex(line)

    def get_robot_samples(self, count: int, timeout: float = 2.0) -> np.ndarray:
        """ロボットモードのサンプルを ``count`` 個読み取り ``(count, 6)`` で返す。"""
        return np.array([self.get_robot_sample(timeout) for _ in range(count)],
                        dtype=np.int16)
