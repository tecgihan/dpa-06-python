"""外部トリガ待ち受け + ソフトウェアトリガ測定テスト（実機が必要）。

EXT で待ち受け状態にし、ソフトウェアトリガ（TRIG）を発行して測定を進め、
数パケット取得してから STOP する。

外部トリガ配線が無くても TRIG で測定を進められることを確認する用途。

使い方::

    python test_ext_trig.py --packets 3
"""

from __future__ import annotations

import argparse

import numpy as np

from dpa06 import Dpa06, Status


def main() -> int:
    parser = argparse.ArgumentParser(description="DPA-06 EXT + TRIG テスト")
    parser.add_argument("--packets", type=int, default=3, help="取得パケット数")
    parser.add_argument("--timeout", type=float, default=3.0, help="1 パケットの待ち時間 [s]")
    args = parser.parse_args()

    dpa = Dpa06()
    dpa.connect()
    try:
        print(f"接続: {dpa.get_serial()}  状態 {dpa.get_status().name}")

        print("\n== EXT（外部トリガ待ち受け）==")
        dpa.ext()
        status = dpa.get_status()
        print(f"  状態: {status.name}")
        if status != Status.EXT:
            print("  警告: EXT 状態になっていません。")

        print("\n== ソフトウェアトリガ発行 ==")
        dpa.trig()
        print("  TRIG OK")

        print(f"\n== パケット取得（{args.packets}）==")
        try:
            packets = dpa.read_packets(args.packets, timeout=args.timeout)
        finally:
            dpa.stop()
            print("  STOP OK")

        data = np.concatenate(packets, axis=0)
        print(f"\n取得サンプル数: {data.shape[0]}")
        print(f"  先頭サンプル: {data[0].tolist()}")
    finally:
        dpa.disconnect()
        print("\n切断しました。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
