"""CSV 保存ユーティリティ。

測定データ（AD 値・工学値）を CSV へ書き出すための補助関数。
テストスクリプトおよび利用者の簡易保存用途を想定する。
"""

from __future__ import annotations

import csv
import os
from typing import Optional, Sequence

import numpy as np

# 出力チャンネルの既定ヘッダ（Fx, Fy, Fz, Mx, My, Mz）
DEFAULT_OUT_COLUMNS = ("Fx", "Fy", "Fz", "Mx", "My", "Mz")


def save_csv(
    path: str,
    data: np.ndarray,
    columns: Optional[Sequence[str]] = None,
    index: bool = True,
    fmt: str = "{:g}",
) -> None:
    """2 次元配列 ``data`` を CSV に保存する。

    Parameters
    ----------
    path:
        出力ファイルパス（親ディレクトリが無ければ作成する）。
    data:
        ``(N, C)`` 形状のデータ。
    columns:
        各列のヘッダ。省略時は ``DEFAULT_OUT_COLUMNS``（6 列のとき）。
    index:
        先頭に 0 始まりのサンプル番号列を付けるか。
    fmt:
        数値の書式文字列。
    """
    arr = np.asarray(data)
    if arr.ndim != 2:
        raise ValueError("data は 2 次元配列である必要があります。")
    n_rows, n_cols = arr.shape

    if columns is None:
        columns = DEFAULT_OUT_COLUMNS if n_cols == len(DEFAULT_OUT_COLUMNS) else \
            [f"ch{i + 1}" for i in range(n_cols)]
    if len(columns) != n_cols:
        raise ValueError("columns の数が data の列数と一致しません。")

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)

    header = (["index"] if index else []) + list(columns)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i, row in enumerate(arr):
            cells = [str(i)] if index else []
            cells += [fmt.format(v) for v in row]
            writer.writerow(cells)
