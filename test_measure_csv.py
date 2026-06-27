"""測定 → 工学値変換 → CSV 保存テスト（実機が必要）。

通常測定で数パケット取得し、AD 値と工学値（eng = AD * FS / 32000）を
それぞれ ``out/`` ディレクトリへ CSV 保存する。

使い方::

    python test_measure_csv.py --packets 5
"""

from __future__ import annotations

import argparse
import os

import numpy as np

from csv_utils import save_csv
from dpa06 import Dpa06


def main() -> int:
    parser = argparse.ArgumentParser(description="DPA-06 測定 CSV 保存テスト")
    parser.add_argument("--packets", type=int, default=5, help="取得パケット数")
    parser.add_argument("--timeout", type=float, default=2.0, help="1 パケットの待ち時間 [s]")
    parser.add_argument("--outdir", default="out", help="出力ディレクトリ")
    args = parser.parse_args()

    dpa = Dpa06()
    dpa.connect()
    try:
        print(f"接続: {dpa.get_serial()}  周波数 {dpa.get_frequency()} Hz")

        ad = dpa.measure(args.packets, timeout=args.timeout)
        fs = dpa._full_scale  # 測定開始時にキャッシュされた FS
        eng = dpa.ad_to_eng(ad)
        print(f"取得サンプル数: {ad.shape[0]}  FullScale: {fs}")

        ad_path = os.path.join(args.outdir, "measure_ad.csv")
        eng_path = os.path.join(args.outdir, "measure_eng.csv")
        save_csv(ad_path, ad, fmt="{:d}")
        save_csv(eng_path, eng, fmt="{:.4f}")

        print(f"\nAD 値  CSV: {os.path.abspath(ad_path)}")
        print(f"工学値 CSV: {os.path.abspath(eng_path)}")

        # 簡易検証
        assert os.path.getsize(ad_path) > 0
        assert os.path.getsize(eng_path) > 0
        # 1 サンプル目の工学値が式どおりか確認
        expected0 = ad[0].astype(float) * np.asarray(fs) / 32000.0
        assert np.allclose(eng[0], expected0)
        print("\n先頭サンプル AD : ", ad[0].tolist())
        print("先頭サンプル eng:  ", [f"{v:.4f}" for v in eng[0]])
        print("検証 OK")
    finally:
        dpa.disconnect()
        print("\n切断しました。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
