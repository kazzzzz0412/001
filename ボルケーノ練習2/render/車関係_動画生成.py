#!/usr/bin/env python3
"""編集指示JSONと元動画から、完成した縦型ショート動画を書き出す。

    python3 車関係_動画生成.py 車関係_編集指示_01.json

やること:
  1. 元動画から指定区間を切り出す
  2. 順に連結する
  3. 720x1280 の黒背景の中央 (x41,y284,638x361) に配置する
  4. オーバーレイPNGを重ねる（指定時刻で勝者ハイライト版に差し替え）
  5. 字幕を焼き込む
  6. H.264 / AAC で書き出す

クリップ窓の角丸は、オーバーレイPNG側が角を黒で覆うので自動的に付く。
"""
import json, pathlib, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
FONT = "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf"

# クリップ窓（車関係_参考動画分析_01_Paradoxia.md の実測値）
W, H = 720, 1280
CX, CY, CW, CH = 41, 284, 638, 361
FPS = 30


def ffmpeg_bin():
    for c in (shutil.which("ffmpeg"), shutil.which("ffmpeg7")):
        if c:
            return c
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg が見つかりません。pip install imageio-ffmpeg を実行してください。")


FF = ffmpeg_bin()


def run(args):
    p = subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"ffmpeg 失敗:\n{' '.join(args)}\n{p.stderr[:2000]}")


def hhmmss(t):
    """'9:48' や '10:18.5' や 63.5 を秒に変換する。"""
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(x) for x in str(t).split(":")]
    s = 0.0
    for v in parts:
        s = s * 60 + v
    return s


def render_subtitle(text, size, work, idx):
    """字幕を透過PNGとして描く。

    このffmpegビルドには drawtext（libfreetype）が入っていないため、
    Pillowで描いてoverlayで重ねる。元動画の字幕（白・細い縁取り）に合わせてある。
    """
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, size)
    pad = size  # 縁取りと余白のぶん
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font, stroke_width=2)
    w, h = box[2] - box[0] + pad * 2, box[3] - box[1] + pad * 2
    if w % 2:
        w += 1
    if h % 2:
        h += 1
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text(
        (w // 2, h // 2), text, font=font, anchor="mm",
        fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 200))
    out = work / f"sub{idx:02d}.png"
    im.save(out)
    return out, w, h


def cut_segments(src, segments, work):
    """各区間を切り出し、クリップ窓のサイズに揃えて再エンコードする。"""
    paths = []
    for i, seg in enumerate(segments):
        a, b = hhmmss(seg["in"]), hhmmss(seg["out"])
        if b <= a:
            sys.exit(f"区間 {i+1} の out が in 以下です: {seg}")
        out = work / f"seg{i:02d}.mp4"
        # ここでは元の解像度のまま揃えるだけ。クリップ窓へのスケールは合成時に1回だけ行う
        # （2度スケールすると画質が落ちる。また CH=361 は奇数なので、
        #  yuv420p の偶数制約に引っかかる中間ファイルを作らない）
        run(["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src),
             "-vf", f"setsar=1,fps={FPS}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", str(out)])
        paths.append(out)
        print(f"  区間 {i+1}/{len(segments)}: {seg['in']} → {seg['out']}  ({b-a:.1f}秒)")
    return paths


def concat(paths, work):
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in paths), encoding="utf-8")
    out = work / "joined.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    return out


def compose(joined, cfg, dest, work):
    """黒背景に配置し、オーバーレイと字幕を乗せる。"""
    ov_a = (HERE / cfg["overlay"]).resolve()
    ov_b = cfg.get("overlay_winner")
    ov_b = (HERE / ov_b).resolve() if ov_b else None
    swap = float(cfg.get("overlay_swap_at", 0)) if ov_b else None

    inputs = ["-f", "lavfi", "-i", f"color=c=0x050505:s={W}x{H}:r={FPS}",
              "-i", str(joined), "-loop", "1", "-i", str(ov_a)]
    if ov_b:
        inputs += ["-loop", "1", "-i", str(ov_b)]

    # クリップ窓を埋めるようにスケールしてから切り抜く（CSSの object-fit: cover 相当）。
    # 16:9 素材なら切り落とすのは数ピクセルで、レターボックスの黒帯が出ない。
    steps = [f"[1:v]scale={CW}:{CH}:force_original_aspect_ratio=increase,"
             f"crop={CW}:{CH},setsar=1[clip]",
             f"[0:v][clip]overlay={CX}:{CY}:shortest=1[base]"]
    if ov_b:
        steps.append(f"[base][2:v]overlay=0:0:enable='lt(t,{swap})'[o1]")
        steps.append(f"[o1][3:v]overlay=0:0:enable='gte(t,{swap})'[ov]")
    else:
        steps.append("[base][2:v]overlay=0:0[ov]")

    last = "ov"
    subs = cfg.get("subtitles", [])
    sub_y = cfg.get("subtitle_y", CY + CH - 46)
    size = cfg.get("subtitle_size", 19)
    n_in = 4 if ov_b else 3          # ここまでに使った入力の本数
    for i, sub in enumerate(subs):
        png, sw, sh = render_subtitle(sub["text"], size, work, i)
        inputs += ["-loop", "1", "-i", str(png)]
        tag = f"s{i}"
        x = (W - sw) // 2
        y = sub_y - sh // 2
        steps.append(
            f"[{last}][{n_in + i}:v]overlay={x}:{y}"
            f":enable='between(t,{hhmmss(sub['start'])},{hhmmss(sub['end'])})'[{tag}]")
        last = tag

    run([*inputs, "-filter_complex", ";".join(steps),
         "-map", f"[{last}]", "-map", "1:a?",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-shortest", str(dest)])


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cfg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    src = pathlib.Path(cfg["source"]).expanduser()
    if not src.exists():
        sys.exit(f"元動画が見つかりません: {src}\n"
                 f"編集指示JSONの \"source\" に、ダウンロードした動画のパスを書いてください。")

    dest = HERE / cfg.get("output", "out.mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = sum(hhmmss(s["out"]) - hhmmss(s["in"]) for s in cfg["segments"])
    print(f"元動画: {src}\n区間: {len(cfg['segments'])}本 / 合計 {total:.1f}秒\n")

    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        print("切り出し中...")
        paths = cut_segments(src, cfg["segments"], work)
        print("連結中...")
        joined = concat(paths, work)
        print(f"合成中（オーバーレイ + 字幕{len(cfg.get('subtitles', []))}枚）...")
        compose(joined, cfg, dest, work)

    print(f"\n完成: {dest}")


if __name__ == "__main__":
    main()
