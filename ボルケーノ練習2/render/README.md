# 動画の書き出し（手元のPCで実行する）

元動画は大きくてやり取りできないので、**書き出しは動画のあるPCで行う。**

## 1. 準備（初回だけ）

```
pip install imageio-ffmpeg pillow
```

システムに `ffmpeg` が入っていればそれを使う。なければ `imageio-ffmpeg` が同梱のものを使う。
日本語フォントは `車関係_動画生成.py` の `FONT` で指定している。
Windows/Mac で動かす場合はここを手元のフォントに書き換えること。

| OS | 例 |
|---|---|
| Windows | `C:/Windows/Fonts/meiryob.ttc` または `msgothic.ttc` |
| macOS | `/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc` |
| Linux | `/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf` |

## 2. 元動画のパスを書く

`車関係_編集指示_01.json` の `"source"` を、ダウンロードした動画のパスに書き換える。

```json
"source": "/Users/you/Downloads/carwow_lfa_vs_viper.mp4",
```

## 3. 実行

```
python3 車関係_動画生成.py 車関係_編集指示_01.json
```

`out/車関係_01_バイパーvsLFA.mp4` が出る（720×1280 / 30fps / H.264+AAC / 70秒）。

## 4. 確認するところ

出来上がったら、まずここを見る。

- **各区間の切り替わりが狙いどおりか**（タイムコードは Gemini の出力に基づいており、未検証）
- 11.5秒あたりに `3 2 1` が出るか
- 54秒あたりでハーフマイルのゴール通過（LFAが先）が映るか
- **62秒でパネルの VIPER 側が光るか**
- 63秒あたりでタイム表示（12.1 / 12.2）が映るか

ズレていたら `車関係_編集指示_01.json` の `segments` と `subtitles` の数字を直して再実行する。
**JSONを直すだけでよく、スクリプトは触らなくてよい。**

---

# Claude にタイムコードを検証させたい場合

元動画そのものは大きすぎて送れないが、**低解像度のプロキシなら送れる。**
以下で必要な範囲だけを切り出して縮小すると、数MBに収まる。

```
ffmpeg -ss 2:00 -to 11:30 -i 元動画.mp4 \
       -vf "scale=480:-2,fps=15" -c:v libx264 -crf 34 -preset veryfast \
       -c:a aac -b:a 48k proxy.mp4
```

画質は落ちるが、**何が何秒に映っているかの確認には十分**。
これを渡してもらえれば、Claude 側でフレーム実測して9箇所のイン点・アウト点を確定させる。

さらに小さくしたい場合は、必要な3箇所だけに分ける。

```
ffmpeg -ss 2:05 -to 2:30  -i 元動画.mp4 -vf "scale=480:-2,fps=15" -c:v libx264 -crf 34 -c:a aac p1.mp4
ffmpeg -ss 4:00 -to 4:10  -i 元動画.mp4 -vf "scale=480:-2,fps=15" -c:v libx264 -crf 34 -c:a aac p2.mp4
ffmpeg -ss 9:45 -to 11:20 -i 元動画.mp4 -vf "scale=480:-2,fps=15" -c:v libx264 -crf 34 -c:a aac p3.mp4
```

## それも面倒な場合

以下の時刻のスクリーンショットを撮って送るだけでもよい（画像なので軽い）。

`9:48` / `10:19` / `10:23` / `10:34` / `10:40` / `11:07` / `11:11` / `11:18`

それぞれで「何が映っているか」が分かれば、区間のイン点・アウト点は検証できる。
