#!/usr/bin/env python3
"""車関係ショート動画のオーバーレイをPNGに書き出す。

使い方:
    python3 車関係_書き出し.py                      # 車関係_データ.json を読んで2枚出力
    python3 車関係_書き出し.py 別のデータ.json

出力:
    out/overlay_preview.png   背景あり。全体の確認用
    out/overlay_alpha.png     クリップ窓が透過。編集ソフトでクリップの上に重ねる用

必要なもの:
    pip install playwright pillow
    Chromium は /opt/pw-browsers/ のものを使う（このリポジトリの動作環境）。
    別環境なら CHROME 環境変数で実行ファイルを指定する。
"""
import json, os, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
HTML = HERE / "車関係_オーバーレイ.html"
DATA = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "車関係_データ.json"
OUT = HERE / "out"

CHROME = os.environ.get("CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def headline_html(lines):
    out = []
    for line in lines:
        out.append("".join(
            f'<span class="g">{t}</span>' if cls == "g" else t for t, cls in line))
    return "<br>".join(out)


def carname_html(name):
    """TOYOTA {GR} YARIS -> 中括弧の部分にゴールドの下線"""
    return name.replace("{", "<u>").replace("}", "</u>")


def main():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    from playwright.sync_api import sync_playwright

    payload = {
        "accountName": d["accountName"],
        "accountId": d["accountId"],
        "headline": headline_html(d["headline"]),
        "sides": {},
    }
    for side in ("left", "right"):
        s = d[side]
        payload["sides"][side] = {
            "name": carname_html(s["name"]),
            "power": s["power"],
            "specs": s["specs"],
            "priceName": s["priceName"],
            "price": s["price"],
            "note": s.get("note", ""),
        }

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 720, "height": 1280}, device_scale_factor=1)
        pg.goto(HTML.as_uri())
        pg.wait_for_timeout(2500)
        pg.evaluate(APPLY_JS, payload)
        pg.wait_for_timeout(300)

        clip = {"x": 0, "y": 0, "width": 720, "height": 1280}
        pg.screenshot(path=str(OUT / "overlay_preview.png"), clip=clip)
        b.close()

    # 背景の黒は残したまま、クリップ窓だけをくり抜いて透過PNGにする。
    # （編集ソフトでは、下のレイヤーに素材クリップ、上にこのPNGを重ねる）
    punch_clip_window(OUT / "overlay_preview.png", OUT / "overlay_alpha.png")

    print(f"書き出しました:\n  {OUT/'overlay_preview.png'}\n  {OUT/'overlay_alpha.png'}")



# クリップ窓の実測値（車関係_参考動画分析_01_Paradoxia.md より）
CLIP_X, CLIP_Y, CLIP_W, CLIP_H, CLIP_R = 41, 284, 638, 361, 8


def punch_clip_window(src, dst):
    """PNGのクリップ窓部分（角丸8px）だけをアルファ0にする。

    背景の黒は残す。編集ソフトでは下のレイヤーに素材クリップ、上にこのPNGを重ねる。
    """
    from PIL import Image, ImageDraw

    im = Image.open(src).convert("RGBA")
    hole = Image.new("L", im.size, 255)
    ImageDraw.Draw(hole).rounded_rectangle(
        [CLIP_X, CLIP_Y, CLIP_X + CLIP_W - 1, CLIP_Y + CLIP_H - 1],
        radius=CLIP_R, fill=0)
    im.putalpha(hole)
    im.save(dst)


APPLY_JS = """(d) => {
  document.querySelector('[data-f=accountName]').textContent = d.accountName;
  document.querySelector('[data-f=accountId]').textContent = d.accountId;
  document.querySelector('#avatar').textContent = d.accountName;
  document.querySelector('[data-f=headline]').innerHTML = d.headline;
  for (const side of ['left','right']) {
    const s = d.sides[side];
    const col = document.querySelector('.col.' + side);
    col.querySelector('.carname').innerHTML = s.name;
    col.querySelector('.power .n').textContent = s.power;
    const rows = col.querySelectorAll('.row');
    s.specs.forEach((sp, i) => {
      if (!rows[i]) return;
      rows[i].querySelector('.l').textContent = sp[0];
      rows[i].querySelector('.v').textContent = sp[1];
    });
    const pc = document.querySelector('#price .pcol.' + (side === 'left' ? 'l' : 'r'));
    pc.querySelector('.pname').textContent = s.priceName;
    pc.querySelector('.pval').textContent = s.price;
    let note = pc.querySelector('.pnote');
    if (s.note) {
      if (!note) { note = document.createElement('div'); note.className = 'pnote'; pc.appendChild(note); }
      note.textContent = s.note;
    } else if (note) { note.remove(); }
  }
}"""


if __name__ == "__main__":
    main()
