"""Shared plain-text formatting for the CLI and the overlay popup."""

from __future__ import annotations

from mahjong_advisor.engine.advisor import HandAnalysis


def format_analysis(result: HandAnalysis, top_n: int = 5) -> str:
    if result.is_agari:
        return "あがり！ツモ可能です。(agari - you can win now)"

    if result.hand_size == 13:
        if result.is_tenpai:
            waits = "/".join(result.wait_names())
            return f"テンパイ中（待ち: {waits}） shanten=0"
        return f"shanten={result.shanten}（まだ自分の番ではありません）"

    lines = []
    best = result.best
    if best is None:
        return "手札を解析できませんでした。"

    header = "→ 切るなら: " + best.display_name
    if best.tenpai:
        header += f"  （テンパイ化！待ち: {'/'.join(best.ukeire_names())}）"
    else:
        header += (
            f"  shanten={best.shanten_after}  "
            f"受入枚数={best.ukeire_kinds}種/"
            f"{best.ukeire_live}枚  待ち候補: {'/'.join(best.ukeire_names())}"
        )
    lines.append(header)

    if len(result.discard_options) > 1:
        lines.append("")
        lines.append(f"{'tile':<6}{'shanten':>8}{'kinds':>7}{'live':>6}  ukeire")
        for opt in result.discard_options[:top_n]:
            lines.append(
                f"{opt.display_name:<6}{opt.shanten_after:>8}{opt.ukeire_kinds:>7}"
                f"{opt.ukeire_live:>6}  {'/'.join(opt.ukeire_names())}"
            )
    return "\n".join(lines)
