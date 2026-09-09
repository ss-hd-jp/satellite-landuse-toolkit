# satellite-landuse-toolkit（日本語）

**無料・アカウント不要の公開衛星データ**（ESA WorldCover、Hansen Global Forest
Change、JRC Global Surface Water、Sentinel-2 L2A）から、土地被覆・樹冠消失・水域変化を
ローカルで再現可能に集計するツールです。Earth Engine もAPIキーも使いません。

**出力は「地図上の分類画素の面積」です。** 統計的な面積推定でも、土地*利用*でも、
権利でも、原因や適法性の証拠でもありません。このツールの役目は、その集計を正しく
行うことと、読み過ぎを防ぐことです。レビューで必ず突かれる解釈上のルールは
[docs/pitfalls_ja.md](docs/pitfalls_ja.md) にまとめています。

**状態：** 公開前（v1.0.0候補）。外部レビューで初期ドラフトの不具合（複数タイル、
期間終端、タイル命名、Sentinel-2の位置合わせとオフセット、AOIマスク）が見つかり、
修正して `tests/` で担保しました。対応範囲は「ほぼ全球」であって「任意の地域」では
ありません（*制限事項* 参照）。

## できること

| コマンド | データ | 出力 |
|---|---|---|
| `slandu fetch` | — | AOIにかかるタイルの解決と取得（`curl`）、Sentinel-2のシーン検索 |
| `slandu landcover` | ESA WorldCover 10m（2021） | ゾーン別・クラス別の面積 |
| `slandu forest` | Hansen GFC 30m（2001-2025） | 年次の樹冠消失、タイル被覆率、閾値感度、約1kmのホットスポットセル |
| `slandu water` | JRC GSW v1.5 30m（1984-2024） | 遷移クラス、シード点を含む連結水域 |
| `slandu change` | Sentinel-2 L2A | 2時期の裸地変化（**同一基準グリッド・共通有効画素**）、実行マニフェスト |

AOIにかかる**全タイルを合算**し、タイルがAOIをどれだけ覆ったかを毎回出力します。
経緯度画素の面積は球面の緯度帯式で積算します（画素セルの面積であって、分類精度ではありません）。

## インストール

```bash
git clone https://github.com/ss-hd-jp/satellite-landuse-toolkit.git
cd satellite-landuse-toolkit
pip install -r requirements.txt
python -m pytest tests -q
```

Python 3.10以上、`rasterio` / `numpy` / `scipy` / `Pillow`、外部コマンド **`curl`**。
geopandas・shapely は不要です。

## 使い方

```bash
python -m slandu fetch --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --only hansen --download
python -m slandu forest --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --out-dir out --hotspot-from 2016
```

`--aoi 対象地域.geojson`（EPSG:4326）にすると、`change` を含む全コマンドで
フィーチャごとの表になります。手順の全体は [examples/quickstart.md](examples/quickstart.md)。

## 出力を正しく読むために

**1. Hansenのlossは再生を差し引かない。** 列名は `no_loss_detected_ha` で、
「残存森林」ではありません。「2000年に樹冠率30%超だった区域のうち、lossが検出されて
いない面積」と書いてください。提供元自身が「loss画素数から確定的な面積推定をしない」
「センサーやアルゴリズムの変更で期間の比較には注意」と明記しています。
`annual_mean_first10` と `last10` の比較は記述的な目安にとどめてください。

**2. 土地被覆 ≠ 土地利用 ≠ 権利。** WorldCover 2021の全球精度76.7%は全クラス・全球の
値で、地域別・クラス別の精度ではありません。回転型・小規模農業の地域では耕地の過小
分類が*起こりうる*——実際に起きているかは現地検証が要ります。統計の収穫面積は
フロー（二期作は2回数える）、土地被覆はストックで、別の量です。

**3. 2時期の変化は、位置合わせ・スケーリング・マスクで決まる。** `slandu change` は
両シーンを1つの基準グリッドに再投影し、反射率のスケーリングをシーンごとにSTACの
サイドカーから決めて**水域画素で検算**し（オフセットの二重適用なら停止）、SCLの
4/5/7だけを有効とし、両日とも有効な画素だけを比較します（`common_valid_pct`）。
残留する薄雲・影・季節・観測条件の差は消せません——1組の日付は候補であって結論ではありません。

## データ出典

版・URL規則・ライセンス・必須の引用と表示クレジット・各データの落とし穴は
[docs/data_catalog_ja.md](docs/data_catalog_ja.md)。

- ESA WorldCover 10m 2021 v200 — CC BY 4.0
- Hansen GFC 2025 v1.13 — CC BY 4.0、表示クレジット `Source: Hansen/UMD/Google/USGS/NASA`
- JRC GSW v1.5（1984-2024）— Copernicus条件、クレジット `Source: EC JRC/Google`
- Sentinel-2 L2A（AWS Open Data / Earth Search）— `Contains modified Copernicus Sentinel data [年].`
- Esri 10m Annual Land Cover（v003パス、2017-2023）— URL解決のみ

**公開物の出典表記は利用者の責任です。** 自分の解析に `processed by ESA` を付けないでください。

行政界は同梱していません。geoBoundaries はレベルごとに出所・ライセンスが異なることが
あり、その場合は国全体と下位区分の合計が一致しません。メタデータを確認して脚注に書いてください。

## 制限事項

- ゾーン集計は経緯度ラスタのみ。`change` はシーンのUTMで処理し、後期シーンのグリッドへ再投影します。
- AOIはEPSG:4326。重なるゾーンは後のものが前を上書きします。
- Hansenは北緯80°〜南緯60°。日付変更線をまたぐAOIは未対応。
- `change` は10mバンドを `stride`×10m（既定20m）のグリッドに最近傍で載せます（全10m画素の集約ではない）。
  シーンのフットプリントは検査しません——両シーンがAOIを覆うことを確認してください。
- ホットスポットのセルは経緯度グリッド上の画素ブロック（赤道付近で約1km）。CSVには実セル面積を出します。
- タイルは丸ごと取得します。`/vsicurl` は意図的に使いません。

## 引用

Zenodoでアーカイブした版（[CITATION.cff](CITATION.cff)）と、使った各データセットを別々に引用してください。

## ライセンス

コードは [MIT](LICENSE)。ダウンロードされるデータは各提供元のライセンスに従います。
