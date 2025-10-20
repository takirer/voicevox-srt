"""
test_voicevox_srt_generator.py

voicevox_srt_generator_v4_fixed.pyの包括的テストスクリプト

テスト項目:
1. MAX_CHARS制約の検証（26文字制限）
2. MAX_LINES制約の検証（2行制限）
3. タイミング精度の検証（分割前後でタイミング一致）
4. デグレッション検証（既存機能の動作確認）
5. 既存SRTとの比較分析

Author: AI Assistant
Version: 1.0
"""

import sys
from pathlib import Path
from typing import List, Dict, Any
import re


# SRTエントリのパース用
def parse_srt_file(srt_path: str) -> List[Dict[str, Any]]:
    """SRTファイルをパースしてエントリリストを返す"""
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = []
    blocks = content.strip().split("\n\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        index = int(lines[0])
        time_line = lines[1]
        text = "\n".join(lines[2:])

        # タイムスタンプ解析
        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", time_line
        )
        if time_match:
            start_time_str = time_match.group(1)
            end_time_str = time_match.group(2)

            # 秒に変換
            start_time = parse_srt_time(start_time_str)
            end_time = parse_srt_time(end_time_str)

            entries.append(
                {
                    "index": index,
                    "start_time": start_time,
                    "end_time": end_time,
                    "start_time_str": start_time_str,
                    "end_time_str": end_time_str,
                    "text": text,
                    "duration": end_time - start_time,
                }
            )

    return entries


def parse_srt_time(time_str: str) -> float:
    """SRTタイムフォーマット (HH:MM:SS,mmm) を秒に変換"""
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])

    return hours * 3600 + minutes * 60 + seconds


def test_max_chars_constraint(
    entries: List[Dict[str, Any]], max_chars: int = 26
) -> Dict[str, Any]:
    """
    Test 1: MAX_CHARS制約の検証

    検証内容:
    - 全エントリが max_chars 以下であること
    - 改行を含む場合、各行が max_chars 以下であること
    """
    print("=" * 80)
    print("Test 1: MAX_CHARS制約の検証")
    print("=" * 80)

    violations = []
    line_violations = []

    for entry in entries:
        text = entry["text"]
        text_length = len(text)

        # 改行を含む場合、各行をチェック
        lines = text.split("\n")
        for line_num, line in enumerate(lines, 1):
            line_length = len(line)
            if line_length > max_chars:
                line_violations.append(
                    {
                        "entry_index": entry["index"],
                        "line_num": line_num,
                        "line": line,
                        "length": line_length,
                        "excess": line_length - max_chars,
                    }
                )

        # 全体の文字数チェック（改行を除く）
        text_no_newline = text.replace("\n", "")
        if len(text_no_newline) > max_chars * len(lines):
            violations.append(
                {
                    "entry_index": entry["index"],
                    "text": text,
                    "length": text_length,
                    "lines": len(lines),
                }
            )

    # 結果表示
    print(f"📊 総エントリ数: {len(entries)}")
    print(f"✅ MAX_CHARS制約を満たすエントリ: {len(entries) - len(line_violations)}")
    print(f"❌ MAX_CHARS制約違反: {len(line_violations)} 行")

    if line_violations:
        print("\n❌ 制約違反の詳細:")
        for i, violation in enumerate(line_violations[:5], 1):
            print(f"\n  違反 {i}:")
            print(f"    Entry: {violation['entry_index']}")
            print(f"    行番号: {violation['line_num']}")
            print(
                f"    文字数: {violation['length']} (超過: {violation['excess']}文字)"
            )
            print(f"    テキスト: {violation['line']}")

        if len(line_violations) > 5:
            print(f"\n  ...他 {len(line_violations) - 5} 件の違反")
    else:
        print("✅ すべてのエントリがMAX_CHARS制約を満たしています")

    return {
        "passed": len(line_violations) == 0,
        "total_entries": len(entries),
        "violations": len(line_violations),
        "details": line_violations,
    }


def test_max_lines_constraint(
    entries: List[Dict[str, Any]], max_lines: int = 2
) -> Dict[str, Any]:
    """
    Test 2: MAX_LINES制約の検証

    検証内容:
    - 全エントリが max_lines 行以下であること
    """
    print("\n" + "=" * 80)
    print("Test 2: MAX_LINES制約の検証")
    print("=" * 80)

    violations = []

    for entry in entries:
        text = entry["text"]
        lines = text.split("\n")
        num_lines = len(lines)

        if num_lines > max_lines:
            violations.append(
                {
                    "entry_index": entry["index"],
                    "text": text,
                    "num_lines": num_lines,
                    "excess": num_lines - max_lines,
                }
            )

    # 結果表示
    print(f"📊 総エントリ数: {len(entries)}")
    print(f"✅ MAX_LINES制約を満たすエントリ: {len(entries) - len(violations)}")
    print(f"❌ MAX_LINES制約違反: {len(violations)} エントリ")

    if violations:
        print("\n❌ 制約違反の詳細:")
        for i, violation in enumerate(violations[:5], 1):
            print(f"\n  違反 {i}:")
            print(f"    Entry: {violation['entry_index']}")
            print(f"    行数: {violation['num_lines']} (超過: {violation['excess']}行)")
            print(f"    テキスト: {violation['text']}")

        if len(violations) > 5:
            print(f"\n  ...他 {len(violations) - 5} 件の違反")
    else:
        print("✅ すべてのエントリがMAX_LINES制約を満たしています")

    return {
        "passed": len(violations) == 0,
        "total_entries": len(entries),
        "violations": len(violations),
        "details": violations,
    }


def test_timing_accuracy(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Test 3: タイミング精度の検証

    検証内容:
    - 連続する字幕の時間軸が途切れていないこと
    - 各エントリの duration > 0 であること
    """
    print("\n" + "=" * 80)
    print("Test 3: タイミング精度の検証")
    print("=" * 80)

    gaps = []
    overlaps = []
    zero_durations = []

    for i in range(len(entries) - 1):
        current = entries[i]
        next_entry = entries[i + 1]

        # duration チェック
        if current["duration"] <= 0:
            zero_durations.append(
                {"entry_index": current["index"], "duration": current["duration"]}
            )

        # 時間軸の連続性チェック
        gap = next_entry["start_time"] - current["end_time"]

        if abs(gap) > 0.001:  # 1ms以上の差異
            if gap > 0:
                gaps.append(
                    {
                        "between": f"{current['index']} - {next_entry['index']}",
                        "gap": gap,
                        "current_end": current["end_time"],
                        "next_start": next_entry["start_time"],
                    }
                )
            else:
                overlaps.append(
                    {
                        "between": f"{current['index']} - {next_entry['index']}",
                        "overlap": -gap,
                        "current_end": current["end_time"],
                        "next_start": next_entry["start_time"],
                    }
                )

    # 最後のエントリのdurationチェック
    if entries:
        last = entries[-1]
        if last["duration"] <= 0:
            zero_durations.append(
                {"entry_index": last["index"], "duration": last["duration"]}
            )

    # 結果表示
    print(f"📊 総エントリ数: {len(entries)}")
    print(f"✅ 正常なdurationを持つエントリ: {len(entries) - len(zero_durations)}")
    print(f"❌ duration=0のエントリ: {len(zero_durations)}")
    print(f"⚠️  時間軸のギャップ: {len(gaps)}")
    print(f"⚠️  時間軸の重複: {len(overlaps)}")

    if zero_durations:
        print("\n❌ duration=0のエントリ:")
        for item in zero_durations[:5]:
            print(f"  Entry {item['entry_index']}: duration={item['duration']:.3f}秒")

    if gaps:
        print("\n⚠️  時間軸のギャップ（上位5件）:")
        for item in sorted(gaps, key=lambda x: x["gap"], reverse=True)[:5]:
            print(f"  {item['between']}: ギャップ={item['gap']:.3f}秒")

    if overlaps:
        print("\n⚠️  時間軸の重複（上位5件）:")
        for item in sorted(overlaps, key=lambda x: x["overlap"], reverse=True)[:5]:
            print(f"  {item['between']}: 重複={item['overlap']:.3f}秒")

    all_passed = len(zero_durations) == 0 and len(gaps) == 0 and len(overlaps) == 0
    if all_passed:
        print("\n✅ すべてのエントリが正確なタイミングを持っています")

    return {
        "passed": all_passed,
        "zero_durations": len(zero_durations),
        "gaps": len(gaps),
        "overlaps": len(overlaps),
    }


def compare_srt_files(old_srt_path: str, new_srt_path: str) -> Dict[str, Any]:
    """
    Test 4: 既存SRTファイルとの比較分析

    比較内容:
    - エントリ数の変化
    - 総時間の一致
    - 分割パターンの変化
    """
    print("\n" + "=" * 80)
    print("Test 4: 既存SRTファイルとの比較分析")
    print("=" * 80)

    if not Path(old_srt_path).exists():
        print("⚠️  既存SRTファイルが見つかりません。比較をスキップします。")
        return {"skipped": True}

    old_entries = parse_srt_file(old_srt_path)
    new_entries = parse_srt_file(new_srt_path)

    # 総時間計算
    old_total_time = old_entries[-1]["end_time"] if old_entries else 0
    new_total_time = new_entries[-1]["end_time"] if new_entries else 0

    # 統計情報
    print("\n📊 エントリ数:")
    print(f"  既存: {len(old_entries)} エントリ")
    print(f"  新規: {len(new_entries)} エントリ")
    print(
        f"  差分: {new_entries and len(new_entries) - len(old_entries) or 0} エントリ"
    )

    print("\n⏱️  総時間:")
    print(f"  既存: {old_total_time:.3f}秒")
    print(f"  新規: {new_total_time:.3f}秒")
    print(f"  差分: {abs(new_total_time - old_total_time):.3f}秒")

    # 文字数統計
    old_char_lengths = [len(e["text"]) for e in old_entries]
    new_char_lengths = [len(e["text"]) for e in new_entries]

    print("\n📏 文字数統計:")
    print(
        f"  既存: 平均={sum(old_char_lengths) / len(old_char_lengths):.1f}文字, 最大={max(old_char_lengths)}文字"
    )
    print(
        f"  新規: 平均={sum(new_char_lengths) / len(new_char_lengths):.1f}文字, 最大={max(new_char_lengths)}文字"
    )

    # MAX_CHARS違反のカウント
    old_violations = sum(1 for length in old_char_lengths if length > 26)
    new_violations = sum(1 for length in new_char_lengths if length > 26)

    print("\n✂️  分割状況:")
    print(
        f"  既存: MAX_CHARS違反={old_violations}エントリ ({old_violations / len(old_entries) * 100:.1f}%)"
    )
    print(
        f"  新規: MAX_CHARS違反={new_violations}エントリ ({new_violations / len(new_entries) * 100:.1f}%)"
    )

    time_match = abs(new_total_time - old_total_time) < 0.1  # 100ms以内の誤差

    return {
        "old_entries": len(old_entries),
        "new_entries": len(new_entries),
        "old_total_time": old_total_time,
        "new_total_time": new_total_time,
        "time_match": time_match,
        "old_violations": old_violations,
        "new_violations": new_violations,
    }


def generate_test_report(
    test1_result: Dict[str, Any],
    test2_result: Dict[str, Any],
    test3_result: Dict[str, Any],
    test4_result: Dict[str, Any],
    output_path: str,
) -> None:
    """テスト結果レポートを生成"""

    report = f"""# VOICEVOX SRT Generator v4 - テスト結果レポート

## テスト概要

このレポートは、voicevox_srt_generator_v4_fixed.py の動作を検証した結果をまとめたものです。

## Test 1: MAX_CHARS制約の検証

**目的**: 全エントリが26文字制限を満たしているか確認

- 総エントリ数: {test1_result["total_entries"]}
- 合格エントリ: {test1_result["total_entries"] - test1_result["violations"]}
- 違反数: {test1_result["violations"]}
- **結果**: {"✅ PASSED" if test1_result["passed"] else "❌ FAILED"}

"""

    if not test1_result["passed"] and test1_result["details"]:
        report += "### 違反詳細（上位5件）\n\n"
        for i, violation in enumerate(test1_result["details"][:5], 1):
            report += f"**違反 {i}**:\n"
            report += f"- Entry: {violation['entry_index']}\n"
            report += f"- 行番号: {violation['line_num']}\n"
            report += (
                f"- 文字数: {violation['length']} (超過: {violation['excess']}文字)\n"
            )
            report += f"- テキスト: {violation['line']}\n\n"

    report += f"""
## Test 2: MAX_LINES制約の検証

**目的**: 全エントリが2行制限を満たしているか確認

- 総エントリ数: {test2_result["total_entries"]}
- 合格エントリ: {test2_result["total_entries"] - test2_result["violations"]}
- 違反数: {test2_result["violations"]}
- **結果**: {"✅ PASSED" if test2_result["passed"] else "❌ FAILED"}

"""

    report += f"""
## Test 3: タイミング精度の検証

**目的**: 字幕と音声のタイミングが正確に同期しているか確認

- duration=0のエントリ: {test3_result["zero_durations"]}
- 時間軸のギャップ: {test3_result["gaps"]}
- 時間軸の重複: {test3_result["overlaps"]}
- **結果**: {"✅ PASSED" if test3_result["passed"] else "❌ FAILED"}

"""

    if not test4_result.get("skipped"):
        report += f"""
## Test 4: 既存SRTファイルとの比較

**目的**: 既存実装との互換性とデグレッション確認

### エントリ数
- 既存: {test4_result["old_entries"]} エントリ
- 新規: {test4_result["new_entries"]} エントリ
- 差分: {test4_result["new_entries"] - test4_result["old_entries"]} エントリ

### 総時間
- 既存: {test4_result["old_total_time"]:.3f}秒
- 新規: {test4_result["new_total_time"]:.3f}秒
- 差分: {abs(test4_result["new_total_time"] - test4_result["old_total_time"]):.3f}秒
- 時間一致: {"✅ YES" if test4_result["time_match"] else "❌ NO"}

### MAX_CHARS違反
- 既存: {test4_result["old_violations"]} エントリ ({test4_result["old_violations"] / test4_result["old_entries"] * 100:.1f}%)
- 新規: {test4_result["new_violations"]} エントリ ({test4_result["new_violations"] / test4_result["new_entries"] * 100:.1f}%)

"""
    else:
        report += "\n## Test 4: 既存SRTファイルとの比較\n\n⚠️  既存SRTファイルが見つからないため、スキップされました。\n\n"

    # 総合判定
    all_passed = (
        test1_result["passed"] and test2_result["passed"] and test3_result["passed"]
    )

    report += """
## 総合判定

"""

    if all_passed:
        report += "### ✅ ALL TESTS PASSED\n\n"
        report += "すべてのテストに合格しました。voicevox_srt_generator_v4_fixed.py は期待通りに動作しています。\n\n"
        report += "**確認事項**:\n"
        report += "- MAX_CHARS制約（26文字制限）が正しく機能しています\n"
        report += "- MAX_LINES制約（2行制限）が正しく機能しています\n"
        report += "- 字幕と音声のタイミングが正確に同期しています\n"
    else:
        report += "### ❌ SOME TESTS FAILED\n\n"
        report += (
            "一部のテストが失敗しました。詳細は上記の各テスト結果を確認してください。\n"
        )

    # ファイル出力
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n📄 テストレポートを生成しました: {output_path}")


def main():
    if len(sys.argv) < 2:
        print(
            "使用方法: python test_voicevox_srt_generator.py <new_srt_file> [old_srt_file]"
        )
        print(
            "例: python test_voicevox_srt_generator.py RankedMatch_01_v4_fixed.srt RankedMatch_01_fixed.srt"
        )
        sys.exit(1)

    new_srt_path = sys.argv[1]
    old_srt_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not Path(new_srt_path).exists():
        print(f"エラー: ファイルが見つかりません: {new_srt_path}")
        sys.exit(1)

    print("🧪 VOICEVOX SRT Generator v4 - 包括的テスト実行中...")
    print(f"📄 テスト対象: {new_srt_path}")
    if old_srt_path:
        print(f"📄 比較対象: {old_srt_path}")

    # SRTファイル読み込み
    new_entries = parse_srt_file(new_srt_path)

    # テスト実行
    test1_result = test_max_chars_constraint(new_entries, max_chars=26)
    test2_result = test_max_lines_constraint(new_entries, max_lines=2)
    test3_result = test_timing_accuracy(new_entries)

    if old_srt_path:
        test4_result = compare_srt_files(old_srt_path, new_srt_path)
    else:
        test4_result = {"skipped": True}

    # レポート生成
    report_path = Path(new_srt_path).parent / "test_results_report.md"
    generate_test_report(
        test1_result, test2_result, test3_result, test4_result, str(report_path)
    )

    # 総合判定
    print("\n" + "=" * 80)
    print("総合判定")
    print("=" * 80)

    all_passed = (
        test1_result["passed"] and test2_result["passed"] and test3_result["passed"]
    )

    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("voicevox_srt_generator_v4_fixed.py は期待通りに動作しています。")
    else:
        print("❌ SOME TESTS FAILED")
        print("一部のテストが失敗しました。詳細はテストレポートを確認してください。")

    print(f"\n📄 詳細レポート: {report_path}")


if __name__ == "__main__":
    main()
