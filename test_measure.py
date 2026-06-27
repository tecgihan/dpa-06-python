"""基本測定テスト（実機が必要）。

NOW の確認 → START → 数パケット取得（ヘッダ/フッタ/サイズ検証）→ STOP。

使い方::

    python test_measure.py            # 既定 5 パケット
    python test_measure.py --packets 10
"""

from __future__ import annotations

import argparse

import numpy as np

from dpa06 import Dpa06


def main() -> int:
    parser = argparse.ArgumentParser(description="DPA-06 基本測定テスト")
    parser.add_argument("--packets", type=int, default=5, help="取得パケット数")
    parser.add_argument("--timeout", type=float, default=2.0, help="1 パケットの待ち時間 [s]")
    args = parser.parse_args()

    dpa = Dpa06()
    dpa.connect()
    try:
        print(f"接続: {dpa.get_serial()}  FW {dpa.get_version()}")
        print(f"周波数 {dpa.get_frequency()} Hz / まとめ {dpa.get_matome()}")

        print("\n== NOW ==")
        now = dpa.get_now()
        print(f"  現在値(int16): {now.tolist()}")

        print(f"\n== 測定（{args.packets} パケット）==")
        dpa.start()
        print(f"  START OK  packet_size={dpa.packet_size()} byte  matome={dpa.matome}")
        try:
            packets = dpa.read_packets(args.packets, timeout=args.timeout)
        finally:
            dpa.stop()
            print("  STOP OK")

        data = np.concatenate(packets, axis=0)
        print(f"\n取得サンプル数: {data.shape[0]} (= {len(packets)} パケット × {dpa.matome})")
        print(f"  各チャンネル min: {data.min(axis=0).tolist()}")
        print(f"  各チャンネル max: {data.max(axis=0).tolist()}")
        print(f"  先頭サンプル   : {data[0].tolist()}")
    finally:
        dpa.disconnect()
        print("\n切断しました。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
