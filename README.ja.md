# satellite-landuse-toolkit（日本語）

**地球上の任意の地域**の土地被覆・森林減少・水域変化を、**無料・アカウント不要の
公開衛星データだけ**で解析するツールです。Earth Engine もAPIキーもクラウドも使わず、
ダウンロードしたタイルをローカルで処理します。

作った理由は、**この種の解析は決まった数個の間違いで簡単に嘘になる**からです。
その対策をコードに埋め込み、[docs/pitfalls_ja.md](docs/pitfalls_ja.md) に明文化してあります。

## できること

| コマンド | データ | 出力 |
|---|---|---|
| `slandu fetch` | AOIに必要なタイルを解決して取得 | ローカルGeoTIFF |
| `slandu landcover` | ESA WorldCover 10m | ゾーン別・クラス別の面積 |
| `slandu forest` | Hansen GFC 30m | 年次の樹冠消失、1kmホットスポット、閾値感度 |
| `slandu water` | JRC Global Surface Water 30m | 水域遷移クラス、シード点による湖体の切り出し |
| `slandu change` | Sentinel-2 L2A 10m | **共通有効画素**での2時期の裸地変化とクラスタ |

面積は `cos(緯度)` 近似ではなく、**球面の緯度帯の厳密式**で積算しています。

## インストール

```bash
git clone https://github.com/<owner>/satellite-landuse-toolkit.git
cd satellite-landuse-toolkit
pip install -r requirements.txt
```

Python 3.10以上、`rasterio` / `numpy` / `scipy` / `Pillow`。geopandas・shapely は不要です。

## 使い方

```bash
python -m slandu fetch --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --only hansen --download
python -m slandu forest --bbox 138.55 36.95 138.75 37.10 --data-dir data/rasters --out-dir out --hotspot-from 2016
```

`--bbox` の代わりに `--aoi 対象地域.geojson` を渡すと、**フィーチャごと（市区町村・
流域・保護区など）の表**になります。詳しい手順は
[examples/quickstart.md](examples/quickstart.md) を参照してください。

## 出力を正しく読むために

査読・レビューで必ず突かれる3点を、最初に潰してあります。

**1. Hansenのlossは再生を差し引かない。** サマリの列名は `no_loss_detected_ha` で、
「残存森林」ではありません。2005年に樹冠を失い、いま完全に樹木で覆われた画素も
lossとして数えられたままです。**「2000年に樹冠率30%超だった区域のうち、lossが
検出されていない面積」**と書いてください。

**2. 土地被覆は土地利用ではないし、権利でもない。** ESA WorldCoverの全球精度は
76.7%で、回転型・小規模農業の地域では `耕地` クラスが大幅に過小になります。
必ず統計と併記し、**収穫面積はフロー（二期作は2回数える）、土地被覆はストック**である
ことを明示してください。

**3. 雲マスクが答えを決める。** `slandu change` はSCLの4/5/7だけを有効とし、
水（クラス6）を除外し、**両日とも有効な画素だけ**で比較して `common_valid_pct` を
出力します。これをしないと、雲量の差がそのまま「変化」になります。

## データ出典

すべて無料・認証不要です。版・URL規則・ライセンス・必須の引用表記・各データの
落とし穴は [docs/data_catalog_ja.md](docs/data_catalog_ja.md) にまとめています。

**公開物の出典表記は利用者の責任です。** 特に、自分で解析したSentinel-2の成果に
`processed by ESA` を付けないでください（正しくは
`Contains modified Copernicus Sentinel data [年].`）。

行政界データは同梱していません。geoBoundaries を使う場合、**レベルごとに出所も
ライセンスも違う**ことがあり（同じ国のADM1とADM2が別提供元）、その結果
**国全体の合計と下位区分の合計が一致しません**。APIのメタデータを確認し、
差分を脚注に書いてください。

## 制限事項

- ゾーン集計は経緯度ラスタのみ（Sentinel-2の処理はUTM対応）
- AOIの再投影はしません。EPSG:4326で渡してください
- マスク用のunionは単なるポリゴンの集合で、位相的なディゾルブではありません
- タイルは丸ごと取得します（Sentinel-2の1バンド約150MB、Hansenのtreecover2000約140MB）
- GDALの `/vsicurl` は意図的に使っていません（環境によってハングするため）

## ライセンス

コードは [MIT](LICENSE)。ダウンロードされるデータは各提供元のライセンスに従います。
