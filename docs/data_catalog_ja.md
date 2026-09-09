# データカタログ — URL・ライセンス・引用表記・落とし穴

すべて**無料・認証不要**。2026-08〜09 に実接続を確認した経路のみ載せる。**版は更新される。公開前に最新版を確認する。**
本ツールの実行で得た数値は *（実測）* と条件付きで示す。定数ではなく例として読む。

## 1. ESA WorldCover 10m（土地被覆・単年）

- URL：`https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{TILE}_Map.tif`
- タイル＝3°×3°、命名は**南西角**：`N00E120` は 0-3°N / 120-123°E。緯度は3の倍数、経度も3の倍数。
- 11クラス：10樹林 / 20低木林 / 30草地 / 40耕地 / 50市街地 / 60裸地 / 70雪氷 / 80恒久水域 /
  90草本湿地 / 95マングローブ / 100コケ地衣。公式カラーテーブルあり。
- ライセンス：**CC BY 4.0**
- 地図クレジット：`© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium`
- データ引用：Zanaga, D. et al. (2022) *ESA WorldCover 10 m 2021 v200*, doi:10.5281/zenodo.7254221
- **落とし穴**：公表されている全球のoverall accuracyは76.7%——全クラス・全球の値であって、
  地域別・クラス別の精度でも面積誤差率でもない。回転型・小規模農業の地域では耕地の
  過小分類が**起こりうる**が、実際に起きているかは現地検証が要る。統計の作付面積は
  フロー（複数回作を重複計上）、土地被覆はストックで、別の量であり検証にはならない。
  v100(2020)とv200(2021)はアルゴリズムが違うので**年差を変化として読まない**。

## 2. Hansen Global Forest Change（森林減少・年次）

- URL：`https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_{LAYER}_{TILE}.tif`
  （LAYER＝`treecover2000` / `lossyear` / `datamask` / `gain` / `last`。TILE＝`10N_120E` 形式＝**北西角**、10°刻み）
- 版は毎年更新される。**最新版のバージョン文字列を必ず確認**（v1.13＝2000-2025）。
- 対象範囲は北緯80°〜南緯60°。`lossyear`：0=なし、1..25＝2001..2025。`datamask`：0=nodata,1=陸,2=恒久水域。
- ライセンス：**CC BY 4.0**
- 地図クレジット：`Source: Hansen/UMD/Google/USGS/NASA`
- 引用：`Hansen, M. C. et al. (2013) "High-Resolution Global Maps of 21st-Century Forest Cover Change." Science 342: 850-853.`
- 提供元の利用上の注意（要旨）：センサー・データ量・アルゴリズムの変更があるため期間をまたぐ
  比較には注意すること。**「loss画素数から確定的な面積推定を行ってはならない」**——地図は
  確率標本の層化には使えるが、画素集計は統計的な面積推定ではない。
- **落とし穴**：lossは「樹高5m以上の植生のstand-replacement disturbance」。**再生を差し引かない**ので
  「残存森林＝2000年森林−loss」とは書けない。植林・樹木作物も樹冠として数える。
  違法性・原因は一切示さない。

## 3. JRC Global Surface Water（水域・1984-）

- **最新 v1.5（1984-2024）**：`https://storage.googleapis.com/water-world/download2024/VER1-5/{PROD}/{PROD}_{LON}_{LAT}_v1_5_2024.tif`
  PROD＝`occurrence` / `change` / `seasonality` / `recurrence` / `transitions` / `extent`。
  タイル＝10°、命名は**北西角**（例 `120E_10N`）。★アンダースコアの位置がv1.4と違う。
  **★ゼロ埋めしない**：`0E_10N`／`10E_10N`／`10W_10S`（実測2026-09：`000E_10N`・`010E_10N` は404）。Hansenの規則を流用しない。
- 旧 v1.4（1984-2021）：`https://storage.googleapis.com/global-surface-water/downloads2021/{PROD}/{PROD}_{LON}_{LAT}v1_4_2021.tif`
- transitionsのクラス：1恒久 2新規恒久 3消失恒久 4季節 5新規季節 6消失季節 7季節→恒久
  8恒久→季節 9一過性恒久 10一過性季節。
- 利用条件：Copernicusプログラムの成果物。「free of charge, without restriction of use」
- 表示クレジット：`Source: EC JRC/Google`
- 引用：`Pekel, J-F., Cottam, A., Gorelick, N., Belward, A. S. (2016) High-resolution mapping of global surface water and its long-term changes. Nature 540: 418-422.`
- **落とし穴**：年次分類は上記バケットには無い。JRC自身のサーバ（`jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GSWE/YearlyClassification/`）で配布されているが、本ツールでは扱っていない。
  v1.5はLandsat Collection 1（〜2021）と2（2022-24）の混在で、提供元は残留する位置ずれを
  「**通常はサブピクセルだが、一部のpath/rowでは1画素（30m）に達するか超える**」と注記し、
  2016-2021年のseasonalityを再処理している（上限1画素という意味ではない）。v1.4とv1.5の差には
  これらの変更が含まれるので、**版間の差を「2021年以降の変化」として引用しない**。
  occurrence≥5%の連結領域は提供元のMaximum Water Extentレイヤ**ではない**。
  「新規恒久水域」は池・ダム・河道変化・潮汐を**全部含む**。必ず画像で目視確認してから
  水体の種類を呼ぶこと。

## 4. Sentinel-2 L2A（10m・現地読み）

- 検索：STAC `https://earth-search.aws.element84.com/v1/search`（collection `sentinel-2-l2a`）。
  POSTで `intersects`（点でよい）＋`datetime`＋`query.eo:cloud_cover`＋`sortby` を投げる。
- 取得：`https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/{utm}/{lat}/{sq}/{Y}/{M}/{ID}/{BAND}.tif`
  （B02/B03/B04/B08 各150MB前後、TCI 200MB、SCL 1MB弱）
- 引用：`Contains modified Copernicus Sentinel data [年].`
  ★自社で解析したものに `processed by ESA` を付けない（ESAが解析したように読める）。
- SCLクラス：3雲影 / 4植生 / 5非植生 / 6水 / 7**未分類**（「晴天」ではない） / 8雲中 / 9雲高 / 10巻雲 / 11雪。
- **反射率のスケーリング——必読。** 処理ベースライン04.00（2022-01-25）以降のL2AにはBOAの
  加算オフセット（−1000 DN）がある。Earth Search公式は「一部のItemには（COG変換時に）適用済み」
  とし、`raster:bands` のscale/offsetを確認せよとしている。Itemのメタデータが内部で矛盾する例が
  ある *（実測2026-09：Item `S2B_51NUA_20260118_0_L2A`、ベースライン05.11で
  `earthsearch:boa_offset_applied: true` **と** `raster:bands.offset: -0.1` が同一アセットに併存）*。
  このItemでは画素もフラグと同じ方向を示した：SCL水域のNIR生DN中央値146→素の×1e-4で0.015、
  さらに−0.1を重ねると−0.085。植生のNIR DN 2772→0.277。強い負の水域中央値は二重適用を
  **疑う**有力な根拠にはなるが、処理履歴の証明ではない。ごく暗い対象では負の地表面反射率の
  **推定値**が生じうる（オフセットは負値の符号化も目的の一つ。Sentinel-2 L2A Data Quality
  Report参照）。決定的な確認は、元のESA/Sinergise製品の同一地上画素との比較である。
  ここで用いた手順：SCL=6の画素の生DNを読み、中央値を取り、候補となる各スケーリングを
  適用して、澄んだ水のNIRの範囲と比較する。
  `slandu change` はしたがって (a) STAC Itemをサイドカーとしてバンド画像と一緒に保持し、
  (b) シーンごと・バンドごとに判定する——提供元フラグがあればそれに従う（矛盾する
  `raster:bands` のoffsetは記録するだけで適用しない）、フラグなしでベースライン04.00未満なら
  オフセットなし、それ以外（サイドカーなし、04.00以降でフラグなし、`false` でベースライン不明）
  は**停止**し、製品を確認したうえで `--offset-a` / `--offset-b` = `applied | apply | none` を
  指定するよう求める。(c) SCL水域セルのNIR中央値を計算し、50セル以上あって中央値が −0.01未満
  または0.15超なら「確認が必要」として停止する。このメッセージはスケーリングまたはシーン品質の
  確認を求めるものであり、どの補正を使うべきかは指示しない。判定とその根拠は実行マニフェストに書く。
- **落とし穴**：①シーン雲量が低くても局所は厚い雲（マスク必須）。②**旧ベースラインのシーンでは
  海面のNIRが澄んだ水の値よりはるかに高いことがある** *（実測：ベースライン02.13のシーンで
  水域NIR中央値DN 613）*。SCL=6を残すと海が裸地に分類されるので、SCL=6も除外する。

## 5. Esri 10m Annual Land Cover（年次・2017-2023）

- URL：`https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003/lc{Y}/{ZONE}_{Y}0101-{Y+1}0101.tif`
  （**v003パスは2017-2023**。2024年以降は同パスでは404＝製品全体の未公開を意味しない。1ファイル 100-200MB）
- **★★ZONE＝UTMゾーン番号 ＋ MGRS緯度帯の文字。半球の N/S ではない**（`geo_util.esri_tile()`）。
  8°刻みで C…X（I と O は欠番）。例：北緯0.5°＝`51N`／**南緯5.1°＝`50M`**／東京＝`54S`／ブエノスアイレス＝`21H`。
  ★間違えても**404にならず 200 OK で別大陸のタイルが落ちてくる**（実測2026-08：南緯5°の地点に
  `50S` を指定 → 北緯32-40度のタイル 203MB×7 を取得してしまった）。
  赤道付近で `51N` が正しく見えるのは、半球Nと帯Nがたまたま一致するため。
  **取得後は必ず `ds.bounds` を経緯度に変換してAOIを含むか確認する。**
- **★逐次ダウンロードは1ファイル約13分（接続あたりで律速）。並列にすると全体で数分**
  （`scripts/download_esri.sh` 相当を `&` ＋ `wait` で）。
- クラス：1水域 2樹木 4湛水植生 5作物 7市街地 8裸地 9雪氷 10雲 11草原・低木。
- 引用：`Karra, K. et al. (2021) Global land use/land cover with Sentinel-2 and deep learning. IGARSS 2021. Esri / Impact Observatory / Microsoft`
- 投影はUTM。**AOIポリゴンをUTMへ投影してからラスタライズ**する（`rasterio.warp.transform`）。
- **落とし穴**：**樹木⇄草原の年次分類揺れが大きい**（実測で±4万ha/年）。森林増減には使わない。
  信頼できるのは作物・市街地・水域の**方向性**。

## 6. geoBoundaries（行政界）

- メタデータAPI：`https://www.geoboundaries.org/api/current/gbOpen/{ISO3}/{ADM1|ADM2}/`
  → `gjDownloadURL` にGeoJSONの実体URL、`boundarySource` / `boundaryLicense` に**そのレベルの**出所。
- **★レベルごとに出所もライセンスも違う**。実測（IDN, 2026-08）：
  - ADM1：OpenStreetMap / Wambacher、**ODbL 1.0**
  - ADM2：BPS Statistics Indonesia / WFP / OCHA ROAP、**CC BY 3.0 IGO**（HDX経由）
- 製品自体の引用：`geoBoundaries gbOpen (Runfola, D. et al. 2020), CC BY 4.0` ＋ 上の原典表記。
- **落とし穴**：ADM1とADM2が別ソースだと**州の面積 ≠ 県の合計**になる。差を脚注で明示する。

## 7. OSM 保護区（Overpass）

- `POST https://overpass-api.de/api/interpreter`、
  `[out:json];(relation["boundary"="protected_area"](S,W,N,E);relation["boundary"="national_park"](...);way["boundary"="protected_area"](...););out geom;`
- way＝単一リング、relation＝outer/inner のマルチポリゴンとして組み立てる。
- ライセンス：ODbL 1.0。**公式の保護区界ではない**。区分（保護林/生産林等）は持たない。

## 8. HydroBASINS / HydroRIVERS（集水域・河道）

- `https://data.hydrosheds.org/file/hydrobasins/standard/hybas_{region}_lev{NN}_v1c.zip`
  （region＝af/ar/as/au/eu/gr/na/sa/si。地域の境界は直感と違うことがあるので、
  取得後にAOIが含まれるか確認する。lev12で1地域約37MB）
- 属性：`HYBAS_ID` / `NEXT_DOWN`（下流をたどる）/ `MAIN_BAS` / `SUB_AREA` / `UP_AREA` / `COAST`。
- 読むのは `pyshp`（`import shapefile`）で十分。geopandas不要。
- 引用：`Lehner, B., Grill G. (2013) Hydrological Processes 27(15): 2171-2186. HydroSHEDS/WWF`
- **落とし穴**：lev12でも**沿岸は小河川がまとめられ数百km²の1集水域**になる。
  「下流」の粒度が場所によって全く違うので、面積を比較する時は集水域数と面積を併記する。

## 9. 各国の林地区分レイヤ

- 省庁の公式ポータルは国外から到達できないことが多い（実測2026-08：5系統を試行、いずれもDNS失敗か404）。
  諦める前に**公開ミラー（例：Global Forest Watch Open Data）がないかを先に確認する**。
  ミラーは国全体を**1行1フィーチャ**のGeoJSONで配ることが多く、ストリーミングでbbox抽出できる。
  同じレイヤのArcGIS REST は、メタデータ（`?f=json`）は取れても `/query` がタイムアウトすることがある。
- **落とし穴**：ミラー側に版・更新年が明示されないことが多い。区分は行政決定で改定されるため、
  対外資料では現地で確認できない限り「版未確認」と書く。

## 10. その他の統計

- 統計局サイトは自動取得を403で拒否することが多い。**原文・公式PDF・正式統計表で確認できた値だけ**を使い、
  検索結果の抜粋（期間・単位・改訂・注記が落ちる）から数値を取らない。
