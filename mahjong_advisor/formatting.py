"""Shared plain-text formatting for the CLI and the overlay popup."""

from __future__ import annotations

from mahjong_advisor.engine.advisor import STANCE_FOLD, STANCE_PUSH, HandAnalysis


def _stance_tag(result: HandAnalysis) -> str:
    """What the ranking is actually optimizing - an explicit stance overrides
    the engine's own push/fold call, so say which one is in effect."""
    if result.stance == STANCE_FOLD:
        return "ベタオリ指定"
    if result.stance == STANCE_PUSH:
        return "押し指定"
    return result.push_fold.verdict


def format_analysis(result: HandAnalysis, top_n: int = 5) -> str:
    if result.is_agari:
        return "あがり！ツモ可能です。(agari - you can win now)"

    if result.hand_size == 13:
        if result.is_tenpai:
            waits = "/".join(result.wait_names())
            return f"テンパイ中（待ち: {waits}） shanten=0"
        return f"shanten={result.shanten}（まだ自分の番ではありません）"

    best = result.best
    if best is None:
        return "手札を解析できませんでした。"

    lines = []
    header = "→ 切るなら: " + best.display_name
    if result.under_threat:
        header += f"  [{_stance_tag(result)}]  危険度 {best.danger_percent:.1f}% ({best.danger_reason})"
    if best.tenpai:
        header += f"  テンパイ！待ち: {'/'.join(best.ukeire_names())}"
    else:
        header += (
            f"  shanten={best.shanten_after} 受入={best.ukeire_kinds}種/{best.ukeire_live}枚"
        )
    lines.append(header)

    if result.under_threat:
        verdict = result.push_fold
        note = "・現物で回せます" if verdict.safe_tile_available else ""
        lines.append(
            f"押し引き: {verdict.verdict}"
            f"（押しEV {verdict.ev_push:+.0f}点 / ベタオリ {verdict.ev_fold:+.0f}点{note}）"
        )
        for label, tiles in result.safe_tiles.items():
            safe = "/".join(tiles) if tiles else "なし"
            lines.append(f"  {label}への安全牌: {safe}")

    if len(result.discard_options) > 1:
        lines.append("")
        if result.under_threat:
            lines.append(f"{'tile':<6}{'shanten':>8}{'受入':>7}{'危険度':>8}{'EV':>8}  根拠")
            for opt in result.discard_options[:top_n]:
                lines.append(
                    f"{opt.display_name:<6}{opt.shanten_after:>8}{opt.ukeire_live:>7}"
                    f"{opt.danger_percent:>7.1f}%{opt.ev or 0:>8.0f}  {opt.danger_reason}"
                )
        else:
            lines.append(f"{'tile':<6}{'shanten':>8}{'kinds':>7}{'live':>6}  ukeire")
            for opt in result.discard_options[:top_n]:
                lines.append(
                    f"{opt.display_name:<6}{opt.shanten_after:>8}{opt.ukeire_kinds:>7}"
                    f"{opt.ukeire_live:>6}  {'/'.join(opt.ukeire_names())}"
                )
    return "\n".join(lines)
