"""FTDI デバイス列挙 / オープン診断スクリプト。

DPA-06 が FTDI D2XX から見えているかを確認するための簡易ツール。
ライブラリ本体を使わず、接続トラブルの切り分けに用いる。

使い方::

    python _check_device.py
"""

from __future__ import annotations

from ftdi_comm import FtdiComm


def main() -> int:
    try:
        devices = FtdiComm.list_devices()
    except Exception as exc:  # noqa: BLE001 - 診断ツールなので全て表示
        print(f"デバイス列挙に失敗しました: {exc}")
        return 1

    if not devices:
        print("FTDI デバイスが見つかりません。")
        return 1

    print(f"FTDI デバイス {len(devices)} 台:")
    for dev in devices:
        print(
            f"  [{dev['index']}] description={dev['description']!r} "
            f"serial={dev['serial']!r} flags={dev['flags']}"
        )

    targets = FtdiComm.list_target_devices()
    print()
    if targets:
        print(f"DPA-06 候補 {len(targets)} 台:")
        for dev in targets:
            print(f"  [{dev['index']}] {dev['description']!r} (serial={dev['serial']!r})")
    else:
        print(f"Description に '{FtdiComm.DEVICE_NAME}' を含むデバイスはありません。")
        return 1

    # 実際にオープン/クローズできるか確認
    comm = FtdiComm()
    try:
        comm.open_by_description()
        print("\nオープン成功。USB パラメータ設定 OK。")
    except Exception as exc:  # noqa: BLE001
        print(f"\nオープンに失敗しました: {exc}")
        return 1
    finally:
        comm.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
