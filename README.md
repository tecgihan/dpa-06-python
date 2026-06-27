# DPA-06 Python ライブラリ

テックギハン製 6 軸力覚センサ用アンプ **DPA-06** を Python から制御するためのライブラリです。
FTDI **D2XX** ドライバ経由で USB 通信を行い、既存のテックギハン製 Python ライブラリ
（`forceplate-python` / `dss300-hr-python` など）と同じ作法で利用できます。

## 主な機能

- FTDI D2XX による接続（Description `"DPA-06"` でオープン）
- デバイス情報の読み取り（シリアル / レビジョン / バージョン / 周波数 / まとめ数）
- 現在値取得（`NOW`）
- 測定制御（`START` / `STOP` / `EXT` / `LEVEL` / `TRIG`）とパケット解析（ヘッダ／フッタ検証）
- レベルトリガのしきい値（トリガレベル）の読み書き（`GET_LEVEL` / `SET_LEVEL`）
- 校正・出力・干渉補正パラメータの読み書き（FORCE_ZERO / FS / 干渉補正行列）
- 測定周波数・まとめ数の設定
- ゼロ調整（`ZERO`）
- ロボット用モード（FW >= 1.3.0、16 進 ASCII ストリーム）
- 工学値変換（`eng = AD * FullScale / 32000`）と CSV 保存

## ファイル構成

| ファイル | 説明 |
|---|---|
| `dpa06.py` | メインクラス `Dpa06` |
| `ftdi_comm.py` | FTDI D2XX 通信ヘルパ |
| `packet_parser.py` | NOW・測定パケット解析、ロボット16進解析、工学値変換 |
| `csv_utils.py` | CSV 保存ヘルパ |
| `_check_device.py` | FTDI デバイス列挙／オープン診断 |
| `test_initial_connect.py` | 接続＋デバイス情報読み取り |
| `test_packet_parser.py` | パケット解析の単体テスト（実機不要） |
| `test_measure.py` | START/STOP 短時間測定 |
| `test_ext_trig.py` | EXT 待ち受け＋ソフトウェアトリガ測定 |
| `test_read_parameters.py` | 校正値・出力設定・干渉補正行列の読み取り |
| `test_set_frequency.py` | 周波数／まとめ数の設定（リードバック検証） |
| `test_zero.py` | ゼロ調整 |
| `test_robot_mode.py` | ロボットモード測定 |
| `test_measure_csv.py` | 測定→工学値→CSV 保存 |
| `requirements.txt` / `pyproject.toml` | 依存・パッケージ定義 |

## インストール

### Windows

1. FTDI の D2XX ドライバをインストールする。
2. 依存パッケージをインストールする。

```powershell
pip install -r requirements.txt
```

ローカル開発用にインストールする場合:

```powershell
pip install -e .
```

### Linux (Ubuntu/Debian)

1. FTDI の libftd2xx を導入する。
2. `pip install -r requirements.txt`
3. 仮想 COM ポートのカーネルモジュールを解除する（D2XX と競合するため）:

```bash
sudo rmmod ftdi_sio usbserial
```

### WSL2

`usbipd-win` で USB デバイスを WSL2 へアタッチしてから上記 Linux 手順を実施する。

## 基本的な使い方

```python
from dpa06 import Dpa06

dpa = Dpa06()
dpa.connect()
try:
    print(dpa.info)              # シリアル/バージョン/周波数/まとめ数 など
    print(dpa.get_now().tolist())  # 現在値（符号付き int16 × 6ch）

    ad = dpa.measure(num_packets=5)   # START → 5 パケット取得 → STOP
    eng = dpa.ad_to_eng(ad)            # 工学値へ変換（FS / 32000）
    print(ad.shape, eng[0])
finally:
    dpa.disconnect()
```

`with` 文にも対応しています。

```python
with Dpa06() as dpa:
    print(dpa.info)
```

取得される測定値・NOW 値はいずれも DPA-06 出力の符号付き 16bit 値です。
工学値は `eng = AD * FullScale / 32000` で求まります（チャンネル順 Fx, Fy, Fz, Mx, My, Mz）。

## 6軸センサ接続時の設定

新しい 6 軸力覚センサを DPA-06 に接続したら、そのセンサの**検査成績書**に記載された
値をアンプへ書き込みます。書き込んだ値はアンプの EEPROM に保存され、次回以降も保持されます
（設定は **IDLE 状態** でのみ受け付けられます）。

検査成績書のうち、力の演算に使われる設定は次の 2 つです。

| 検査成績書の項目 | 設定先 | API |
|---|---|---|
| **4. 定格容量**（Rated Capacity） | フルスケール FS | `set_fs(value, OutCh.*)` |
| **11. 行列係数**（Coefficient of Matrix） | 干渉補正行列 | `set_itf_matrix(matrix)` |

### 例：`USX10-H10-1.5KN-H`（S/N SL260101）検査成績書

検査成績書の **定格容量** と **行列係数** をそのまま書き込みます。
行列係数は「行 = 補正後の出力（FHx, FHy, FHz, MHx, MHy, MHz = Fx, Fy, Fz, Mx, My, Mz）」、
「列 = ひずみ出力（εFx, εFy, εFz, εMx, εMy, εMz = 入力ch Fx1〜Fz2）」の順です。

```python
import numpy as np
from dpa06 import Dpa06, OutCh

# --- 検査成績書 4. 定格容量（Rated Capacity）---
#        Fx    Fy    Fz    Mx  My  Mz
rated = [750,  750,  1500, 12, 12, 6]   # N, N, N, N·m, N·m, N·m

# --- 検査成績書 11. 行列係数（Coefficient of Matrix）---
# 行=出力(Fx..Mz), 列=入力(εFx..εMz)
itf = np.array([
    [ 0.80000, -0.02718,  0.01341,  0.00513,  0.09174,  0.07604],  # FHx
    [ 0.02470,  0.82796,  0.01261, -0.06270,  0.00894,  0.00877],  # FHy
    [-0.00800, -0.02280,  0.95838, -0.00042, -0.00725,  0.01120],  # FHz
    [-0.00007,  0.00240,  0.00004,  0.00495,  0.00003, -0.00025],  # MHx
    [-0.00233, -0.00012,  0.00014, -0.00001,  0.00499, -0.00007],  # MHy
    [-0.00001,  0.00003,  0.00002,  0.00000,  0.00003,  0.00171],  # MHz
])

with Dpa06() as dpa:
    # 必ず IDLE 状態で設定する
    for ch, fs in zip(OutCh, rated):
        dpa.set_fs(fs, ch)               # フルスケール（定格容量）
    dpa.set_itf_matrix(itf)              # 干渉補正行列（36要素を書き込み）

    # 読み戻して確認
    print("FS        :", dpa.get_fs())
    print("ITF matrix:\n", dpa.get_itf_matrix())
```

設定後はセンサを無負荷にして `zero_and_wait()` でゼロ調整を行い、
`measure()` → `ad_to_eng()` で工学値（N / N·m）が得られます。

> 個別要素だけを書き換えたい場合は `set_itf(value, item)`（`item = 出力ch * 6 + 入力ch`、0〜35）、
> 読み取りは `get_itf(item)` を使います。

### 例：3軸センサ `USL06-H5-500N-E` を 2 個接続

3 軸力覚センサ（Fx, Fy, Fz の 3 軸）を 2 個つなぐと、合計 **6 入力・6 出力** として DPA-06 で扱えます。
チャンネルの割り当ては次のとおりです（入力配線に合わせる）。

| | 入力ch | 出力ch |
|---|---|---|
| 1 個目のセンサ | Fx1, Fy1, Fz1 | 出力ch 1〜3（Fx, Fy, Fz） |
| 2 個目のセンサ | Fx2, Fy2, Fz2 | 出力ch 4〜6（DPA-06 上は Mx, My, Mz の枠） |

設定のポイント:

- **定格容量（FS）**: 各センサの定格容量を並べる。USL06-H5-500N-E は Fx=250, Fy=250, Fz=500 [N]。
- **干渉補正行列**: 各センサの検査成績書の **3×3 行列係数** を、6×6 の **対角ブロック** に配置する。
  2 つのセンサは独立しており相互干渉が無いため、非対角ブロックは **0** にする。

```python
import numpy as np
from dpa06 import Dpa06, OutCh

# 各 3 軸センサの定格容量（Fx, Fy, Fz）
rated = [250, 250, 500,    # 1 個目（出力ch 1〜3）
         250, 250, 500]    # 2 個目（出力ch 4〜6）

# 1 個目（S/N UL260308）の 3x3 行列係数
itf1 = np.array([
    [ 0.22376, -0.00631, -0.00480],
    [ 0.00311,  0.23149,  0.00403],
    [ 0.00099,  0.00425,  0.25989],
])
# 2 個目（S/N UL260309）の 3x3 行列係数
itf2 = np.array([
    [ 0.23474, -0.00282,  0.00328],
    [-0.00066,  0.23690,  0.00195],
    [-0.00004,  0.00257,  0.26520],
])

# 6x6 ブロック対角行列を組み立て（センサ間の干渉は 0）
itf = np.zeros((6, 6))
itf[0:3, 0:3] = itf1   # 1 個目: 出力ch 1〜3 × 入力ch 1〜3
itf[3:6, 3:6] = itf2   # 2 個目: 出力ch 4〜6 × 入力ch 4〜6

with Dpa06() as dpa:
    # 必ず IDLE 状態で設定する
    for ch, fs in zip(OutCh, rated):
        dpa.set_fs(fs, ch)
    dpa.set_itf_matrix(itf)

    print("FS        :", dpa.get_fs())
    print("ITF matrix:\n", dpa.get_itf_matrix())
```

ゼロ調整・測定・工学値変換は 6 軸センサの場合と同じです。測定値は
出力ch 1〜3 が 1 個目の力（N）、出力ch 4〜6 が 2 個目の力（N）になります。

## 動作確認

```powershell
python _check_device.py          # FTDI から DPA-06 が見えるか
python test_packet_parser.py     # 実機不要のパケット解析テスト
python test_initial_connect.py   # 接続＋デバイス情報
python test_measure.py --packets 5
python test_measure_csv.py --packets 5
```

ゼロ調整はデバイス内部のゼロ点（FORCE_ZERO）を更新します（無負荷状態で実行）。

```powershell
python test_zero.py            # ゼロ調整を実行
```

## 対応コマンド

- 読み取り: `GET_STATUS`, `GET_SERIAL`, `GET_REVISION`, `GET_VERSION`, `GET_FREQUENCY`,
  `GET_MATOME`, `GET_FORCE_ZERO`, `GET_LEVEL`, `GET_FS`,
  `GET_ITF_6X12`, `GET_FOR_ROBOT`, `GET_ERROR`, `NOW`
- 制御: `START`, `STOP`, `EXT`, `LEVEL`, `TRIG`, `ZERO`
- 設定: `SET_FREQUENCY`, `SET_MATOME`, `SET_LEVEL`, `SET_FS`,
  `SET_ITF_6X12`, `SET_FOR_ROBOT`

設定可能値: 周波数 = 240 / 100 / 500 / 1000 / 5000 / 10000 [Hz]、
まとめ数 = 24 / 10 / 50 / 100 / 500 / 1000。

## ライセンス

MIT License（`LICENSE` を参照）。
