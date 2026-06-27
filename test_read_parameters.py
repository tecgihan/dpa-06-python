"""パラメータ読み取りテスト（実機が必要・読み取り専用）。

校正値（FORCE_ZERO）、出力設定（LEVEL / FS）、
干渉補正行列（6x6）を読み取って表示する。デバイスへの書き込みは行わない。

使い方::

    python test_read_parameters.py
"""

from __future__ import annotations

from dpa06 import InCh, OutCh, Dpa06


def main() -> int:
    dpa = Dpa06()
    dpa.connect()
    try:
        print(f"接続: {dpa.get_serial()}  FW {dpa.get_version()}  状態 {dpa.get_status().name}")

        in_labels = [c.name for c in InCh]
        out_labels = [c.name for c in OutCh]

        print("\n== 校正値（入力ch順 Fx1,Fy1,Fz1,Fx2,Fy2,Fz2）==")
        for name, getter in (("FORCE_ZERO", dpa.get_force_zero),):
            values = getter()
            pairs = ", ".join(f"{lab}={v:g}" for lab, v in zip(in_labels, values))
            print(f"  {name:10s}: {pairs}")

        print("\n== 出力設定（出力ch順 Fx,Fy,Fz,Mx,My,Mz）==")
        for name, getter in (("LEVEL", dpa.get_level), ("FS", dpa.get_fs)):
            values = getter()
            pairs = ", ".join(f"{lab}={v:g}" for lab, v in zip(out_labels, values))
            print(f"  {name:10s}: {pairs}")

        print("\n== 干渉補正行列（行=出力ch, 列=入力ch）==")
        matrix = dpa.get_itf_matrix()
        header = "         " + "".join(f"{lab:>10s}" for lab in in_labels)
        print(header)
        for out_lab, row in zip(out_labels, matrix):
            cells = "".join(f"{v:10.4g}" for v in row)
            print(f"  {out_lab:6s}{cells}")
    finally:
        dpa.disconnect()
        print("\n切断しました。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
