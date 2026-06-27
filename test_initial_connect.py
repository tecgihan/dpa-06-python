"""初回接続テスト（実機が必要）。

デバイス列挙 → 接続 → デバイス情報読み取り → ステータス取得 → 切断
までを通しで確認する。

使い方::

    python test_initial_connect.py
"""

from __future__ import annotations

from dpa06 import Dpa06


def main() -> int:
    print("== DPA-06 デバイス列挙 ==")
    devices = Dpa06.list_devices()
    if not devices:
        print("DPA-06 が見つかりません。接続と D2XX ドライバを確認してください。")
        return 1
    for dev in devices:
        print(f"  [{dev['index']}] {dev['description']!r} serial={dev['serial']!r}")

    dpa = Dpa06()
    print("\n== 接続 ==")
    dpa.connect()
    print("接続成功")

    try:
        print("\n== デバイス情報 ==")
        info = dpa.info
        for key, value in info.items():
            print(f"  {key:10s}: {value}")

        print("\n== ステータス ==")
        print(f"  status: {dpa.get_status().name}")
    finally:
        dpa.disconnect()
        print("\n切断しました。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
