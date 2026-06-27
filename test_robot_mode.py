"""ロボットモード測定テスト（実機が必要・FW >= 1.3.0）。

ロボット用モードを一時的に ON にして測定を開始し、16 進 ASCII の
サンプルを数個取得してから停止する。最後に必ず元の設定へ戻す。

使い方::

    python test_robot_mode.py --samples 10
"""

from __future__ import annotations

import argparse

from dpa06 import Dpa06


def main() -> int:
    parser = argparse.ArgumentParser(description="DPA-06 ロボットモードテスト")
    parser.add_argument("--samples", type=int, default=10, help="取得サンプル数")
    parser.add_argument("--timeout", type=float, default=2.0, help="1 サンプルの待ち時間 [s]")
    args = parser.parse_args()

    dpa = Dpa06()
    dpa.connect()
    try:
        print(f"接続: {dpa.get_serial()}  FW {dpa.get_version()}")
        if not dpa.is_for_robot_available():
            print("このファームウェアはロボット用機能に対応していません。")
            return 1

        original = dpa.get_for_robot()
        print(f"現在のロボットモード: {original}")

        print("\n== ロボットモード ON で測定 ==")
        dpa.set_for_robot(True)
        try:
            dpa.start()
            print(f"  START OK（{args.samples} サンプル取得）")
            try:
                samples = dpa.get_robot_samples(args.samples, timeout=args.timeout)
            finally:
                dpa.stop()
                print("  STOP OK")
            print(f"\n取得サンプル数: {samples.shape[0]}")
            for i, s in enumerate(samples[:5]):
                print(f"  sample[{i}]: {s.tolist()}")
        finally:
            dpa.set_for_robot(original)
            print(f"\nロボットモードを元に戻しました: {dpa.get_for_robot()}")
    finally:
        dpa.disconnect()
        print("切断しました。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
