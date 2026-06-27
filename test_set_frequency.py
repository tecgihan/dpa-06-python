"""設定書き込みテスト：周波数・まとめ数（実機が必要）。

副作用を最小化するため「現在値を読む → 同じ値を書く → OK とリードバック一致」
を基本に検証する。``--change`` を付けた場合のみ、別の有効値へ一時的に変更し、
最後に必ず元の値へ戻す。

使い方::

    python test_set_frequency.py            # 現在値の書き直し検証のみ（無害）
    python test_set_frequency.py --change   # 別値へ変更→復元まで検証
"""

from __future__ import annotations

import argparse

from dpa06 import Dpa06, VALID_FREQUENCIES, VALID_MATOME


def _verify_same(dpa: Dpa06) -> None:
    freq = dpa.get_frequency()
    matome = dpa.get_matome()
    print(f"  現在値: frequency={freq}, matome={matome}")

    dpa.set_frequency(freq)
    dpa.set_matome(matome)
    assert dpa.get_frequency() == freq, "周波数リードバック不一致"
    assert dpa.get_matome() == matome, "まとめ数リードバック不一致"
    print("  同値書き込み → OK・リードバック一致")


def _verify_change(dpa: Dpa06) -> None:
    orig_freq = dpa.get_frequency()
    orig_matome = dpa.get_matome()
    new_freq = next(f for f in VALID_FREQUENCIES if f != orig_freq)
    new_matome = next(m for m in VALID_MATOME if m != orig_matome)
    print(f"  変更: frequency {orig_freq}→{new_freq}, matome {orig_matome}→{new_matome}")
    try:
        dpa.set_frequency(new_freq)
        dpa.set_matome(new_matome)
        assert dpa.get_frequency() == new_freq, "周波数変更が反映されていません"
        assert dpa.get_matome() == new_matome, "まとめ数変更が反映されていません"
        print("  変更反映を確認")
    finally:
        dpa.set_frequency(orig_freq)
        dpa.set_matome(orig_matome)
        print(f"  復元: frequency={dpa.get_frequency()}, matome={dpa.get_matome()}")
        assert dpa.get_frequency() == orig_freq
        assert dpa.get_matome() == orig_matome


def main() -> int:
    parser = argparse.ArgumentParser(description="DPA-06 周波数/まとめ数 設定テスト")
    parser.add_argument("--change", action="store_true",
                        help="別の有効値へ一時変更してから復元する")
    args = parser.parse_args()

    dpa = Dpa06()
    dpa.connect()
    try:
        print(f"接続: {dpa.get_serial()}  状態 {dpa.get_status().name}")
        print("\n== 同値書き込み検証 ==")
        _verify_same(dpa)
        if args.change:
            print("\n== 変更→復元検証 ==")
            _verify_change(dpa)
    finally:
        dpa.disconnect()
        print("\n切断しました。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
