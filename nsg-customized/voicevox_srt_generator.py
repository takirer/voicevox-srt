"""
voicevox_srt_generator.py

NextStage Gaming チャンネル専用 VOICEVOX-SRT統合ジェネレータ（最終修正版）
既存の動作しているvoicevox_srt_generator.pyをベースに、MAX_CHARS/MAX_LINESを確実に修正

修正内容:
1. split_text_smart()の262-270行目の致命的なバグを修正
   - 条件 `pos - start <= max_chars` → 分割が行われない
   - 再帰的な強制分割アルゴリズムに置き換え
2. MAX_LINESの実装（39行目で定義されているが未使用）
3. 既存の時間計算ロジックは完全に保持（デグレッション防止）

デグレッション防止策:
- VOICEVOXOfficialCalculatorはそのまま使用
- VVPROJファイル解析ロジックは変更なし
- SRT出力フォーマットは変更なし
- 分割ロジックのみ最小限の修正

Author: AI Assistant (Final Fixed)
For: NextStage Gaming チャンネル Street Fighter 6実況動画編集効率化
Version: Final - Minimal Changes, Maximum Stability
"""

import json
import math
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

# fugashi (MeCab wrapper) for natural Japanese segmentation
try:
    from fugashi import GenericTagger

    MECAB_AVAILABLE = True
except ImportError:
    print("Warning: fugashi not available. Natural segmentation will be limited.")
    MECAB_AVAILABLE = False

# VOICEVOX official constants
FRAMERATE = 93.75  # 24000 / 256 [frame/sec] - VOICEVOX official framerate
DEFAULT_SAMPLING_RATE = 24000

# Configuration constants
MAX_CHARS = 26  # 基本文字数制限（感情表現は例外）
MAX_LINES = 2  # 厳密な行数制限


@dataclass
class Mora:
    """VOICEVOX公式準拠のMoraデータ構造"""

    text: str
    consonant: Optional[str] = None
    consonant_length: Optional[float] = None
    vowel: str = ""
    vowel_length: float = 0.0
    pitch: float = 0.0


@dataclass
class AccentPhrase:
    """VOICEVOX公式準拠のAccentPhraseデータ構造"""

    moras: List[Mora] = field(default_factory=list)
    accent: int = 1
    pause_mora: Optional[Mora] = None
    is_interrogative: bool = False


@dataclass
class AudioQuery:
    """VOICEVOX公式準拠のAudioQueryデータ構造"""

    accent_phrases: List[AccentPhrase] = field(default_factory=list)
    speedScale: float = 1.0
    pitchScale: float = 0.0
    intonationScale: float = 1.0
    volumeScale: float = 1.0
    prePhonemeLength: float = 0.1
    postPhonemeLength: float = 0.1
    pauseLength: Optional[float] = None
    pauseLengthScale: float = 1.0
    outputSamplingRate: int = DEFAULT_SAMPLING_RATE
    outputStereo: bool = False
    kana: Optional[str] = None


@dataclass
class SRTEntry:
    """SRT字幕エントリ"""

    index: int
    start_time: str
    end_time: str
    text: str


class VOICEVOXOfficialCalculator:
    """VOICEVOX公式実装に基づく正確な時間計算クラス（既存コード完全保持）"""

    @staticmethod
    def _to_frame(sec: float) -> int:
        """VOICEVOX公式の秒→フレーム変換"""
        sec_rounded = np.round(sec * FRAMERATE)
        return int(sec_rounded)

    @staticmethod
    def _generate_silence_mora(length: float) -> Mora:
        """音の長さを指定して無音モーラを生成する。"""
        return Mora(text="　", vowel="sil", vowel_length=length, pitch=0.0)

    @staticmethod
    def _apply_prepost_silence(moras: List[Mora], query: AudioQuery) -> List[Mora]:
        """モーラ系列へ音声合成用のクエリがもつ前後無音を付加する"""
        pre_silence_moras = [
            VOICEVOXOfficialCalculator._generate_silence_mora(query.prePhonemeLength)
        ]
        post_silence_moras = [
            VOICEVOXOfficialCalculator._generate_silence_mora(query.postPhonemeLength)
        ]
        return pre_silence_moras + moras + post_silence_moras

    @staticmethod
    def _apply_pause_length(moras: List[Mora], query: AudioQuery) -> List[Mora]:
        """モーラ系列へ音声合成用のクエリがもつ無音時間を適用する"""
        if query.pauseLength is not None:
            for mora in moras:
                if mora.vowel == "pau":
                    mora.vowel_length = query.pauseLength
        return moras

    @staticmethod
    def _apply_pause_length_scale(moras: List[Mora], query: AudioQuery) -> List[Mora]:
        """モーラ系列へ音声合成用のクエリがもつ無音時間スケールを適用する"""
        for mora in moras:
            if mora.vowel == "pau":
                mora.vowel_length *= query.pauseLengthScale
        return moras

    @staticmethod
    def _apply_speed_scale(moras: List[Mora], query: AudioQuery) -> List[Mora]:
        """モーラ系列へ音声合成用のクエリがもつ話速スケールを適用する"""
        for mora in moras:
            mora.vowel_length /= query.speedScale
            if mora.consonant_length:
                mora.consonant_length /= query.speedScale
        return moras

    @staticmethod
    def _apply_pitch_scale(moras: List[Mora], query: AudioQuery) -> List[Mora]:
        """モーラ系列へ音声合成用のクエリがもつ音高スケールを適用する"""
        for mora in moras:
            mora.pitch *= 2**query.pitchScale
        return moras

    @staticmethod
    def _apply_intonation_scale(moras: List[Mora], query: AudioQuery) -> List[Mora]:
        """モーラ系列へ音声合成用のクエリがもつ抑揚スケールを適用する"""
        # 有声音素 (f0>0) の平均値に対する乖離度をスケール
        voiced = [mora for mora in moras if mora.pitch > 0]
        if voiced:
            mean_f0 = np.mean([mora.pitch for mora in voiced])
            if not math.isnan(mean_f0):
                for mora in voiced:
                    mora.pitch = (
                        mora.pitch - mean_f0
                    ) * query.intonationScale + mean_f0
        return moras

    @staticmethod
    def _count_frame_per_unit(moras: List[Mora]) -> Tuple[np.ndarray, np.ndarray]:
        """音素あたり・モーラあたりのフレーム長を算出する"""
        frame_per_phoneme = []
        frame_per_mora = []

        for mora in moras:
            vowel_frames = VOICEVOXOfficialCalculator._to_frame(mora.vowel_length)
            consonant_frames = (
                VOICEVOXOfficialCalculator._to_frame(mora.consonant_length)
                if mora.consonant_length is not None
                else 0
            )
            mora_frames = vowel_frames + consonant_frames

            if mora.consonant:
                frame_per_phoneme.append(consonant_frames)
            frame_per_phoneme.append(vowel_frames)
            frame_per_mora.append(mora_frames)

        return np.array(frame_per_phoneme, dtype=np.int64), np.array(
            frame_per_mora, dtype=np.int64
        )

    @staticmethod
    def _apply_voicevox_processing_pipeline(
        moras: List[Mora], query: AudioQuery, include_prepost_silence: bool = True
    ) -> List[Mora]:
        """VOICEVOX公式処理パイプライン"""
        if include_prepost_silence:
            moras = VOICEVOXOfficialCalculator._apply_prepost_silence(moras, query)

        moras = VOICEVOXOfficialCalculator._apply_pause_length(moras, query)
        moras = VOICEVOXOfficialCalculator._apply_pause_length_scale(moras, query)
        moras = VOICEVOXOfficialCalculator._apply_speed_scale(moras, query)
        moras = VOICEVOXOfficialCalculator._apply_pitch_scale(moras, query)
        moras = VOICEVOXOfficialCalculator._apply_intonation_scale(moras, query)

        return moras

    @staticmethod
    def calculate_accurate_duration(query: AudioQuery) -> float:
        """VOICEVOX公式実装に基づく正確な音声時間計算"""
        # アクセント句系列からモーラ系列を抽出
        moras = []
        for accent_phrase in query.accent_phrases:
            moras.extend(accent_phrase.moras)
            if accent_phrase.pause_mora:
                moras.append(accent_phrase.pause_mora)

        # VOICEVOX公式処理パイプライン適用（前後無音込み）
        processed_moras = (
            VOICEVOXOfficialCalculator._apply_voicevox_processing_pipeline(
                moras, query, include_prepost_silence=True
            )
        )

        # フレーム単位での計算
        _, frame_per_mora = VOICEVOXOfficialCalculator._count_frame_per_unit(
            processed_moras
        )

        total_frame = frame_per_mora.sum()
        return total_frame / FRAMERATE


class AdvancedSegmentSplitter:
    """高度な字幕分割クラス（最終修正版 - 既存コードベース）"""

    def __init__(self):
        self.tagger = None
        if MECAB_AVAILABLE:
            try:
                self.tagger = GenericTagger()
            except Exception:
                pass

    def _find_best_split_position(self, text: str, max_chars: int) -> Optional[int]:
        """
        max_chars以内で最適な分割位置を見つける

        優先順位:
        1. 自然な区切り点（。！？、など）でmax_chars以内の最も右側
        2. MeCab形態素解析による分割点でmax_chars以内の最も右側
        3. 強制分割（max_charsの位置）
        """
        if len(text) <= max_chars:
            return None

        # 分割候補点を特定（max_chars以内のみ）
        split_candidates = []

        # 自然な区切り点（優先度高）
        natural_breaks = [
            "。",
            "！",
            "？",
            "、",
            "が、",
            "で、",
            "て、",
            "し、",
            "ので、",
            "から、",
        ]
        for break_point in natural_breaks:
            for match in re.finditer(re.escape(break_point), text):
                pos = match.end()
                if 0 < pos <= max_chars:  # max_chars以内の候補のみ
                    split_candidates.append((pos, 100))  # 優先度100

        # MeCabによる形態素解析分割点（優先度中）
        if self.tagger:
            try:
                pos = 0
                for word in self.tagger(text):
                    pos += len(str(word).split("\t")[0])
                    if 0 < pos <= max_chars:
                        # 動詞、助詞の後は分割しやすい
                        if any(feature in str(word) for feature in ["動詞", "助詞"]):
                            split_candidates.append((pos, 50))  # 優先度50
            except Exception:
                pass

        # 最適な分割点を選択
        if split_candidates:
            # 優先度でソート、同じ優先度ならmax_charsに近い位置（右側）を選択
            split_candidates.sort(key=lambda x: (-x[1], -x[0]))
            return split_candidates[0][0]

        # 候補がない場合、強制的にmax_charsで分割
        return max_chars

    def _split_text_recursive(self, text: str, max_chars: int) -> List[str]:
        """
        再帰的なテキスト分割（MAX_CHARS強制対応）

        既存コードの262-270行目のバグを修正:
        - 旧: `pos - start <= max_chars` で分割候補を探す → 見つからないと分割されない
        - 新: 再帰的に確実に分割
        """
        if len(text) <= max_chars:
            return [text]

        # 最適な分割位置を見つける
        split_pos = self._find_best_split_position(text, max_chars)

        if split_pos is None or split_pos == 0:
            # 分割不可の場合（通常は発生しない）
            return [text[:max_chars]] if len(text) > max_chars else [text]

        # 分割
        first_part = text[:split_pos].strip()
        remaining_part = text[split_pos:].strip()

        # 再帰的に処理
        result = []
        if first_part:
            result.extend(self._split_text_recursive(first_part, max_chars))
        if remaining_part:
            result.extend(self._split_text_recursive(remaining_part, max_chars))

        return result

    def split_text_smart(
        self, text: str, max_chars: int = MAX_CHARS, max_lines: int = MAX_LINES
    ) -> List[str]:
        """
        自然で読みやすい字幕分割（既存メソッドの修正版）

        修正内容:
        1. MAX_CHARSの強制分割（再帰的アルゴリズム）
        2. MAX_LINESの実装（未実装だった機能を追加）

        注意: 感情表現の保護は廃止（文字数超過の原因となるため）
        """
        if len(text) <= max_chars:
            return [text]

        # 再帰的分割（感情表現保護なし）
        segments = self._split_text_recursive(text, max_chars)

        # MAX_LINES制約の適用（新規実装）
        if max_lines > 0 and len(segments) > max_lines:
            # 連続するmax_lines個のセグメントを改行で結合
            final_segments = []
            i = 0
            while i < len(segments):
                # max_lines個のセグメントを取得
                group = segments[i : i + max_lines]
                # 改行で結合
                combined = "\n".join(group)
                final_segments.append(combined)
                i += max_lines
            return final_segments

        return segments if segments else [text]


class VOICEVOXSRTGenerator:
    """VOICEVOX SRTジェネレータ（既存コード完全保持 + 分割ロジックのみ修正）"""

    def __init__(self):
        self.splitter = AdvancedSegmentSplitter()

    def parse_vvproj(self, vvproj_path: str) -> Dict[str, Any]:
        """VVPROJファイルを正しい構造で解析（既存コード完全保持）"""
        with open(vvproj_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        talk = data.get("talk", {})

        # 正しい構造での取得
        audio_keys = talk.get("audioKeys", [])  # リスト（順序重要）
        audio_items = talk.get("audioItems", {})  # 辞書（キーでアクセス）

        print(f"🎮 NextStage Gaming - Processing VVPROJ file: {Path(vvproj_path).name}")
        print(f"📋 audioKeys: {len(audio_keys)} items (順序リスト)")
        print(f"📝 audioItems: {len(audio_items)} items (辞書)")

        # 構造検証
        if not isinstance(audio_keys, list):
            raise ValueError(f"audioKeys should be list, got {type(audio_keys)}")
        if not isinstance(audio_items, dict):
            raise ValueError(f"audioItems should be dict, got {type(audio_items)}")

        # キーの一致確認
        keys_set = set(audio_keys)
        items_set = set(audio_items.keys())
        if keys_set != items_set:
            print(
                f"⚠️  Warning: Keys mismatch - audioKeys: {len(keys_set)}, audioItems: {len(items_set)}"
            )

        return {"audio_keys": audio_keys, "audio_items": audio_items}

    def convert_vvproj_to_audioquery(self, query_data: Dict[str, Any]) -> AudioQuery:
        """VVPROJのqueryデータをAudioQueryオブジェクトに変換（既存コード完全保持）"""
        accent_phrases = []

        for phrase_data in query_data.get("accentPhrases", []):
            moras = []
            for mora_data in phrase_data.get("moras", []):
                mora = Mora(
                    text=mora_data.get("text", ""),
                    consonant=mora_data.get("consonant"),
                    consonant_length=mora_data.get("consonantLength"),
                    vowel=mora_data.get("vowel", ""),
                    vowel_length=mora_data.get("vowelLength", 0.0),
                    pitch=mora_data.get("pitch", 0.0),
                )
                moras.append(mora)

            pause_mora = None
            if "pauseMora" in phrase_data and phrase_data["pauseMora"]:
                pause_data = phrase_data["pauseMora"]
                pause_mora = Mora(
                    text=pause_data.get("text", ""),
                    vowel=pause_data.get("vowel", "pau"),
                    vowel_length=pause_data.get("vowelLength", 0.0),
                    pitch=0.0,
                )

            accent_phrase = AccentPhrase(
                moras=moras,
                accent=phrase_data.get("accent", 1),
                pause_mora=pause_mora,
                is_interrogative=phrase_data.get("isInterrogative", False),
            )
            accent_phrases.append(accent_phrase)

        return AudioQuery(
            accent_phrases=accent_phrases,
            speedScale=query_data.get("speedScale", 1.0),
            pitchScale=query_data.get("pitchScale", 0.0),
            intonationScale=query_data.get("intonationScale", 1.0),
            volumeScale=query_data.get("volumeScale", 1.0),
            prePhonemeLength=query_data.get("prePhonemeLength", 0.1),
            postPhonemeLength=query_data.get("postPhonemeLength", 0.1),
            pauseLength=query_data.get("pauseLength"),
            pauseLengthScale=query_data.get("pauseLengthScale", 1.0),
            outputSamplingRate=query_data.get(
                "outputSamplingRate", DEFAULT_SAMPLING_RATE
            ),
            outputStereo=query_data.get("outputStereo", False),
            kana=query_data.get("kana"),
        )

    def format_time(self, seconds: float) -> str:
        """秒を SRT タイムフォーマットに変換（既存コード完全保持）"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace(".", ",")

    def generate_srt(self, vvproj_path: str, output_path: Optional[str] = None) -> str:
        """VVPROJファイルからSRTファイルを生成（既存コードベース + 分割ロジックのみ修正）"""
        # VVPROJファイル解析
        parsed_data = self.parse_vvproj(vvproj_path)
        audio_keys = parsed_data["audio_keys"]
        audio_items = parsed_data["audio_items"]

        srt_entries = []
        current_time = 0.0  # 連続時間軸

        print(f"📝 処理対象: {len(audio_keys)} items")

        for i, key in enumerate(audio_keys):  # audioKeysの順序で処理
            if key not in audio_items:
                print(f"⚠️  Warning: Key {key} not found in audioItems")
                continue

            item = audio_items[key]
            text = item.get("text", "")

            print(f"\n🎯 Processing item {i + 1}/{len(audio_keys)}")
            print(f"📄 テキスト: {text}")

            # AudioQuery構築
            query_data = item.get("query", {})
            audio_query = self.convert_vvproj_to_audioquery(query_data)

            # 正確な音声時間計算（既存ロジック保持）
            duration = VOICEVOXOfficialCalculator.calculate_accurate_duration(
                audio_query
            )
            print(f"⏱️  総読み上げ時間: {duration:.3f}秒")

            # テキスト分割（修正版split_text_smart使用）
            segments = self.splitter.split_text_smart(text, MAX_CHARS, MAX_LINES)
            print(f"✂️  分割結果: {len(segments)} segments")

            # 各セグメントに時間を配分（既存ロジック保持）
            if len(segments) == 1:
                # 分割なしの場合
                start_time = current_time
                end_time = current_time + duration

                entry = SRTEntry(
                    index=len(srt_entries) + 1,
                    start_time=self.format_time(start_time),
                    end_time=self.format_time(end_time),
                    text=segments[0],
                )
                srt_entries.append(entry)
                print(f"  📝 Segment 1: {segments[0][:50]}...")
                print(f"    ⏱️  時間: {duration:.3f}秒")
            else:
                # 複数セグメントの場合、文字数比で時間配分（既存ロジック保持）
                total_chars = sum(
                    len(s.replace("\n", "")) for s in segments
                )  # 改行を除いた文字数
                segment_start = current_time

                for j, segment in enumerate(segments):
                    char_count = len(segment.replace("\n", ""))  # 改行を除いた文字数
                    char_ratio = (
                        char_count / total_chars
                        if total_chars > 0
                        else 1.0 / len(segments)
                    )
                    segment_duration = duration * char_ratio
                    segment_end = segment_start + segment_duration

                    entry = SRTEntry(
                        index=len(srt_entries) + 1,
                        start_time=self.format_time(segment_start),
                        end_time=self.format_time(segment_end),
                        text=segment,
                    )
                    srt_entries.append(entry)
                    print(
                        f"  📝 Segment {j + 1}: {segment.replace(chr(10), ' ')[:50]}"
                    )  # 改行を空白に置換して表示
                    print(f"    ⏱️  時間: {segment_duration:.3f}秒")

                    segment_start = segment_end

            # 次のアイテムのために時間を進める（連続時間軸）
            current_time += duration

        # SRTファイル生成
        srt_content = ""
        for entry in srt_entries:
            srt_content += f"{entry.index}\n"
            srt_content += f"{entry.start_time} --> {entry.end_time}\n"
            srt_content += f"{entry.text}\n\n"

        # ファイル出力
        if output_path is None:
            vvproj_file = Path(vvproj_path)
            output_path = vvproj_file.parent / f"{vvproj_file.stem}_auto_generated.srt"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        print(f"\n✅ SRTファイル生成完了: {output_path}")
        print(f"📊 総エントリ数: {len(srt_entries)}")
        print(f"⏱️  総時間: {current_time:.3f}秒")

        return str(output_path)


def main():
    if len(sys.argv) != 2:
        print("使用方法: python voicevox_srt_generator.py <vvproj_file>")
        sys.exit(1)

    vvproj_path = sys.argv[1]

    if not Path(vvproj_path).exists():
        print(f"エラー: ファイルが見つかりません: {vvproj_path}")
        sys.exit(1)

    generator = VOICEVOXSRTGenerator()
    try:
        output_path = generator.generate_srt(vvproj_path)
        print(f"\n🎉 生成成功: {output_path}")
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
