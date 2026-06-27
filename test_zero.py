"""ゼロ調整テスト（実機が必要）。

ゼロ調整（ZERO）を実行し、前後の力覚センサゼロ点（FORCE_ZERO）を表示する。
無負荷状態で実行すること。

使い方::

    python test_zero.py
"""

from __future__ import annotations

from dpa06 import Dpa06


def main() -> int:
    dpa = Dpa06()
    dpa.connect()
    try:
        print(f"接続: {dpa.get_serial()}  状態 {dpa.get_status().name}")
        before = dpa.get_force_zero()
        print(f"調整前のゼロ点 FORCE_ZERO: {before}")

        print("\nゼロ調整を実行します...")
        dpa.zero_and_wait()
        after = dpa.get_force_zero()
        print(f"完了。状態 {dpa.get_status().name}")
        print(f"調整後のゼロ点 FORCE_ZERO: {after}")
    finally:
        dpa.disconnect()
        print("\n切断しました。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
