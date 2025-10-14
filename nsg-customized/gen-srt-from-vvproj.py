#!/usr/bin/env python3
"""
gen-srt-from-vvproj.py

VOICEVOX-SRT 公式仕様準拠版
VOICEVOXで生成したvvprojファイルから完全同期するSRTファイルを出力

主要機能:
- VOICEVOX公式実装に基づく正確な時間計算
- 感情表現（句読点・感嘆詞繰り返し）の自然な保持
- fugashi（MeCab）による自然な日本語行分割
- MAX_CHARS/MAX_LINES要件への準拠

Author: AI Assistant (based on yKesamaru/voicevox-srt + VOICEVOX official implementation)
For: NextStage Gaming チャンネル Street Fighter 6実況動画編集効率化
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
MAX_LINES = 2   # 厳密な行数制限
UPSPEAK_LENGTH = 0.15
UPSPEAK_PITCH_ADD = 0.3
UPSPEAK_PITCH_MAX = 6.5

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
    """VOICEVOX公式実装に基づく正確な時間計算クラス"""
    
    @staticmethod
    def _to_frame(sec: float) -> int:
        """
        VOICEVOX公式の秒→フレーム変換
        NOTE: roundは偶数丸め。移植時に取扱い注意。
        """
        sec_rounded = np.round(sec * FRAMERATE)
        return int(sec_rounded)
    
    @staticmethod
    def _generate_silence_mora(length: float) -> Mora:
        """音の長さを指定して無音モーラを生成する。"""
        return Mora(text="　", vowel="sil", vowel_length=length, pitch=0.0)
    
    @staticmethod
    def _apply_prepost_silence(moras: List[Mora], query: AudioQuery) -> List[Mora]:
        """モーラ系列へ音声合成用のクエリがもつ前後無音を付加する"""
        pre_silence_moras = [VOICEVOXOfficialCalculator._generate_silence_mora(query.prePhonemeLength)]
        post_silence_moras = [VOICEVOXOfficialCalculator._generate_silence_mora(query.postPhonemeLength)]
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
                    mora.pitch = (mora.pitch - mean_f0) * query.intonationScale + mean_f0
        return moras
    
    @staticmethod
    def _count_frame_per_unit(moras: List[Mora]) -> Tuple[np.ndarray, np.ndarray]:
        """
        音素あたり・モーラあたりのフレーム長を算出する
        
        Returns:
            frame_per_phoneme: 音素あたりのフレーム長
            frame_per_mora: モーラあたりのフレーム長
        """
        frame_per_phoneme = []
        frame_per_mora = []
        
        for mora in moras:
            vowel_frames = VOICEVOXOfficialCalculator._to_frame(mora.vowel_length)
            consonant_frames = (
                VOICEVOXOfficialCalculator._to_frame(mora.consonant_length) 
                if mora.consonant_length is not None else 0
            )
            mora_frames = vowel_frames + consonant_frames
            
            if mora.consonant:
                frame_per_phoneme.append(consonant_frames)
            frame_per_phoneme.append(vowel_frames)
            frame_per_mora.append(mora_frames)
        
        return np.array(frame_per_phoneme, dtype=np.int64), np.array(frame_per_mora, dtype=np.int64)
    
    @staticmethod
    def calculate_accurate_duration(query: AudioQuery) -> float:
        """
        VOICEVOX公式実装に基づく正確な音声時間計算
        _query_to_decoder_featureの処理フローを再現
        """
        # アクセント句系列からモーラ系列を抽出
        moras = []
        for accent_phrase in query.accent_phrases:
            moras.extend(accent_phrase.moras)
            if accent_phrase.pause_mora:
                moras.append(accent_phrase.pause_mora)
        
        # 設定を適用する順序が重要（公式実装と同順序）
        moras = VOICEVOXOfficialCalculator._apply_prepost_silence(moras, query)
        moras = VOICEVOXOfficialCalculator._apply_pause_length(moras, query)
        moras = VOICEVOXOfficialCalculator._apply_pause_length_scale(moras, query)
        moras = VOICEVOXOfficialCalculator._apply_speed_scale(moras, query)
        moras = VOICEVOXOfficialCalculator._apply_pitch_scale(moras, query)
        moras = VOICEVOXOfficialCalculator._apply_intonation_scale(moras, query)
        
        # フレーム単位での計算
        _, frame_per_mora = VOICEVOXOfficialCalculator._count_frame_per_unit(moras)
        
        # 総フレーム数を計算
        total_frames = np.sum(frame_per_mora)
        
        # フレームから秒に変換
        total_seconds = total_frames / FRAMERATE
        
        return total_seconds

class EmotionalExpressionHandler:
    """感情表現（句読点・感嘆詞繰り返し）処理クラス"""
    
    # 感情表現として認識するパターン
    EMOTION_PATTERN = r'([。！？、…・ー～]{2,})$'
    SINGLE_PUNCT_PATTERN = r'[。！？、…・ー～]+$'
    
    @classmethod
    def analyze_emotional_expression(cls, text: str) -> Dict[str, Any]:
        """感情表現を詳細分析"""
        match = re.search(cls.EMOTION_PATTERN, text)
        
        if match:
            base_text = text[:match.start()]
            emotion_part = match.group(1)
            
            return {
                'has_emotion': True,
                'base_text': base_text,
                'emotion_part': emotion_part,
                'base_length': len(base_text),
                'emotion_length': len(emotion_part),
                'total_length': len(text)
            }
        
        return {
            'has_emotion': False,
            'base_text': text,
            'emotion_part': '',
            'base_length': len(text),
            'emotion_length': 0,
            'total_length': len(text)
        }
    
    @classmethod
    def is_chars_allowed_with_emotion(cls, text: str, max_chars: int = MAX_CHARS) -> bool:
        """感情表現を考慮した文字数制限チェック"""
        if len(text) <= max_chars:
            return True
        
        analysis = cls.analyze_emotional_expression(text)
        
        # 感情表現がある場合、基本文字部分のみを制限対象とする
        if analysis['has_emotion']:
            return analysis['base_length'] <= max_chars
        
        return False
    
    @classmethod
    def is_meaningless_punctuation(cls, text: str) -> bool:
        """意味のない句読点のみのテキストかチェック"""
        stripped = text.strip()
        if not stripped:
            return True
        
        # 1文字以下の句読点のみは意味がない
        if len(stripped) <= 1 and re.match(cls.SINGLE_PUNCT_PATTERN, stripped):
            return True
        
        return False

class NaturalSegmentator:
    """fugashiによる自然な日本語行分割クラス（感情表現対応版）"""
    
    def __init__(self):
        if MECAB_AVAILABLE:
            try:
                self.tagger = GenericTagger("-r /opt/homebrew/etc/mecabrc -d /opt/homebrew/lib/mecab/dic/ipadic")
            except Exception as e:
                print(f"Warning: Failed to initialize MeCab: {e}")
                self.tagger = None
        else:
            self.tagger = None
        
        self.emotion_handler = EmotionalExpressionHandler()
    
    def segment_text(self, text: str, max_chars: int = MAX_CHARS, max_lines: int = MAX_LINES) -> List[str]:
        """
        感情表現を考慮した自然な日本語分割
        """
        if not text.strip():
            return []
        
        # 基本的な分割候補を取得
        segments = self._get_natural_break_points(text)
        
        # 意味のない句読点エントリを除外
        meaningful_segments = []
        for segment in segments:
            if not self.emotion_handler.is_meaningless_punctuation(segment):
                meaningful_segments.append(segment)
        
        if not meaningful_segments:
            return []
        
        # MAX_CHARS/MAX_LINES制限に準拠した分割（感情表現考慮）
        result = self._enforce_limits_with_emotion(meaningful_segments, max_chars, max_lines)
        
        return result
    
    def _get_natural_break_points(self, text: str) -> List[str]:
        """自然な分割候補を取得（改良版）"""
        if not self.tagger:
            return self._simple_segmentation(text)
        
        # より自然な分割のため、句読点での分割を改良
        # 句読点は前の文章と統合することを基本とする
        sentences = []
        current = ""
        
        i = 0
        while i < len(text):
            char = text[i]
            current += char
            
            # 句読点に遭遇した場合
            if char in "。！？":
                # 連続する句読点も含める
                while i + 1 < len(text) and text[i + 1] in "。！？、…・ー～":
                    i += 1
                    current += text[i]
                
                # 現在の文を確定
                if current.strip():
                    sentences.append(current.strip())
                    current = ""
            
            i += 1
        
        # 残りの部分があれば追加
        if current.strip():
            sentences.append(current.strip())
        
        # 長すぎるセンテンスをMeCabで細分割
        refined_sentences = []
        for sentence in sentences:
            if self.emotion_handler.is_chars_allowed_with_emotion(sentence, MAX_CHARS):
                refined_sentences.append(sentence)
            else:
                refined_sentences.extend(self._mecab_segmentation(sentence))
        
        return refined_sentences
    
    def _mecab_segmentation(self, text: str) -> List[str]:
        """MeCabによる形態素解析分割（感情表現考慮）"""
        try:
            # 感情表現部分を保護
            emotion_analysis = self.emotion_handler.analyze_emotional_expression(text)
            
            if emotion_analysis['has_emotion']:
                base_text = emotion_analysis['base_text']
                emotion_part = emotion_analysis['emotion_part']
                
                # 基本部分のみを分割
                words = []
                for word in self.tagger(base_text):
                    words.append(str(word.surface))
                
                # 単語を適切にグループ化
                segments = []
                current = ""
                
                for word in words:
                    if len(current + word) <= MAX_CHARS:
                        current += word
                    else:
                        if current:
                            segments.append(current)
                        current = word
                
                # 最後のセグメントに感情表現を追加
                if current:
                    current += emotion_part
                    segments.append(current)
                elif segments:
                    segments[-1] += emotion_part
                
                return segments
            else:
                # 通常の分割処理
                words = []
                for word in self.tagger(text):
                    words.append(str(word.surface))
                
                segments = []
                current = ""
                
                for word in words:
                    if len(current + word) <= MAX_CHARS:
                        current += word
                    else:
                        if current:
                            segments.append(current)
                        current = word
                
                if current:
                    segments.append(current)
                
                return segments
                
        except Exception:
            return self._simple_segmentation(text)
    
    def _simple_segmentation(self, text: str) -> List[str]:
        """MeCab利用不可時の簡易分割（感情表現考慮）"""
        segments = []
        current = ""
        
        for char in text:
            test_text = current + char
            if self.emotion_handler.is_chars_allowed_with_emotion(test_text, MAX_CHARS):
                current = test_text
            else:
                if current:
                    segments.append(current)
                current = char
        
        if current:
            segments.append(current)
        
        return segments
    
    def _enforce_limits_with_emotion(self, segments: List[str], max_chars: int, max_lines: int) -> List[str]:
        """MAX_CHARS/MAX_LINES制限の厳密な実装（感情表現考慮）"""
        if not segments:
            return []
        
        result = []
        current_lines = []
        
        for segment in segments:
            # セグメントが長すぎる場合は強制分割
            if not self.emotion_handler.is_chars_allowed_with_emotion(segment, max_chars):
                segment_parts = self._force_split_with_emotion(segment, max_chars)
            else:
                segment_parts = [segment]
            
            for part in segment_parts:
                # 現在の行に追加可能かチェック
                if len(current_lines) < max_lines:
                    if not current_lines:
                        current_lines.append(part)
                    else:
                        # 最後の行に追加可能かチェック
                        last_line = current_lines[-1]
                        combined = last_line + part
                        if self.emotion_handler.is_chars_allowed_with_emotion(combined, max_chars):
                            current_lines[-1] = combined
                        else:
                            # 新しい行として追加
                            if len(current_lines) < max_lines:
                                current_lines.append(part)
                            else:
                                # 行数制限に達した場合、現在のエントリを確定
                                result.append('\n'.join(current_lines))
                                current_lines = [part]
                else:
                    # 行数制限に達した場合、現在のエントリを確定
                    result.append('\n'.join(current_lines))
                    current_lines = [part]
        
        # 残りの行を追加
        if current_lines:
            result.append('\n'.join(current_lines))
        
        return result
    
    def _force_split_with_emotion(self, text: str, max_chars: int) -> List[str]:
        """文字数制限を超える場合の強制分割（感情表現考慮）"""
        emotion_analysis = self.emotion_handler.analyze_emotional_expression(text)
        
        if emotion_analysis['has_emotion']:
            # 感情表現がある場合、基本部分を分割し最後に感情表現を付加
            base_text = emotion_analysis['base_text']
            emotion_part = emotion_analysis['emotion_part']
            
            base_parts = []
            current = ""
            
            for char in base_text:
                if len(current + char) <= max_chars:
                    current += char
                else:
                    if current:
                        base_parts.append(current)
                    current = char
            
            if current:
                current += emotion_part
                base_parts.append(current)
            elif base_parts:
                base_parts[-1] += emotion_part
            
            return base_parts
        else:
            # 通常の強制分割
            parts = []
            current = ""
            
            for char in text:
                if len(current + char) <= max_chars:
                    current += char
                else:
                    if current:
                        parts.append(current)
                    current = char
            
            if current:
                parts.append(current)
            
            return parts

class VOICEVOXSRTGenerator:
    """VOICEVOX公式仕様準拠のSRTジェネレータ（感情表現対応版）"""
    
    def __init__(self):
        self.calculator = VOICEVOXOfficialCalculator()
        self.segmentator = NaturalSegmentator()
    
    def process_vvproj(self, vvproj_path: str, output_path: Optional[str] = None) -> str:
        """VVPROJファイルを処理してSRTファイルを生成"""
        print(f"Processing VVPROJ file: {vvproj_path}")
        
        # VVPROJファイルを読み込み
        with open(vvproj_path, 'r', encoding='utf-8') as f:
            vvproj_data = json.load(f)
        
        # audioItemsを取得
        audio_items = vvproj_data.get('talk', {}).get('audioItems', {})
        if not audio_items:
            raise ValueError("No audioItems found in VVPROJ file")
        
        # audioKeysの順序を取得
        audio_keys = vvproj_data.get('talk', {}).get('audioKeys', [])
        if not audio_keys:
            audio_keys = list(audio_items.keys())
        
        print(f"Found {len(audio_items)} audio items, {len(audio_keys)} audio keys")
        
        # SRTエントリを生成
        srt_entries = self._generate_srt_entries(audio_items, audio_keys)
        
        # SRTファイルに出力
        if output_path is None:
            vvproj_path_obj = Path(vvproj_path)
            output_path = vvproj_path_obj.with_suffix('.srt')
        
        srt_content = self._write_srt_file(srt_entries, output_path)
        
        print(f"SRT file generated: {output_path}")
        print(f"Total entries: {len(srt_entries)}")
        
        return srt_content
    
    def _vvproj_to_audio_query(self, audio_item: Dict[str, Any]) -> AudioQuery:
        """VVPROJのaudioItemをAudioQueryに変換"""
        query_data = audio_item.get('query', {})
        
        # AccentPhraseを変換
        accent_phrases = []
        for phrase_data in query_data.get('accentPhrases', []):
            # Moraを変換
            moras = []
            for mora_data in phrase_data.get('moras', []):
                mora = Mora(
                    text=mora_data.get('text', ''),
                    consonant=mora_data.get('consonant'),
                    consonant_length=mora_data.get('consonantLength'),
                    vowel=mora_data.get('vowel', ''),
                    vowel_length=mora_data.get('vowelLength', 0.0),
                    pitch=mora_data.get('pitch', 0.0)
                )
                moras.append(mora)
            
            # PauseMoraを変換
            pause_mora = None
            if phrase_data.get('pauseMora'):
                pause_data = phrase_data['pauseMora']
                pause_mora = Mora(
                    text=pause_data.get('text', ''),
                    consonant=pause_data.get('consonant'),
                    consonant_length=pause_data.get('consonantLength'),
                    vowel=pause_data.get('vowel', ''),
                    vowel_length=pause_data.get('vowelLength', 0.0),
                    pitch=pause_data.get('pitch', 0.0)
                )
            
            accent_phrase = AccentPhrase(
                moras=moras,
                accent=phrase_data.get('accent', 1),
                pause_mora=pause_mora,
                is_interrogative=phrase_data.get('isInterrogative', False)
            )
            accent_phrases.append(accent_phrase)
        
        # AudioQueryを構築
        audio_query = AudioQuery(
            accent_phrases=accent_phrases,
            speedScale=query_data.get('speedScale', 1.0),
            pitchScale=query_data.get('pitchScale', 0.0),
            intonationScale=query_data.get('intonationScale', 1.0),
            volumeScale=query_data.get('volumeScale', 1.0),
            prePhonemeLength=query_data.get('prePhonemeLength', 0.1),
            postPhonemeLength=query_data.get('postPhonemeLength', 0.1),
            pauseLength=query_data.get('pauseLength'),
            pauseLengthScale=query_data.get('pauseLengthScale', 1.0),
            outputSamplingRate=query_data.get('outputSamplingRate', DEFAULT_SAMPLING_RATE),
            outputStereo=query_data.get('outputStereo', False),
            kana=query_data.get('kana')
        )
        
        return audio_query
    
    def _generate_srt_entries(self, audio_items: Dict[str, Any], audio_keys: List[str]) -> List[SRTEntry]:
        """SRTエントリを生成（感情表現対応）"""
        srt_entries = []
        current_time = 0.0
        
        for i, audio_key in enumerate(audio_keys):
            if audio_key not in audio_items:
                print(f"Warning: Audio key {audio_key} not found in audioItems")
                continue
            
            audio_item = audio_items[audio_key]
            text = audio_item.get('text', '')
            
            if not text.strip():
                continue
            
            # AudioQueryに変換
            audio_query = self._vvproj_to_audio_query(audio_item)
            
            # VOICEVOX公式実装に基づく正確な時間計算
            duration = self.calculator.calculate_accurate_duration(audio_query)
            
            # 感情表現を考慮した自然な分割を適用
            text_segments = self.segmentator.segment_text(text, MAX_CHARS, MAX_LINES)
            
            if not text_segments:
                current_time += duration
                continue
            
            # 各セグメントの時間を均等分割
            segment_duration = duration / len(text_segments) if text_segments else duration
            
            for j, segment_text in enumerate(text_segments):
                if not segment_text.strip():
                    continue
                
                start_time = current_time + (j * segment_duration)
                end_time = start_time + segment_duration
                
                srt_entry = SRTEntry(
                    index=len(srt_entries) + 1,
                    start_time=self._seconds_to_srt_time(start_time),
                    end_time=self._seconds_to_srt_time(end_time),
                    text=segment_text.strip()
                )
                srt_entries.append(srt_entry)
            
            current_time += duration
        
        return srt_entries
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """秒をSRT時間形式に変換"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def _write_srt_file(self, srt_entries: List[SRTEntry], output_path: str) -> str:
        """SRTファイルを出力"""
        srt_content = []
        
        for entry in srt_entries:
            srt_content.append(str(entry.index))
            srt_content.append(f"{entry.start_time} --> {entry.end_time}")
            srt_content.append(entry.text)
            srt_content.append("")  # 空行
        
        content = '\n'.join(srt_content)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return content

def main():
    """メイン処理"""
    if len(sys.argv) < 2:
        print("Usage: python gen-srt-from-vvproj.py <vvproj_file> [output_srt_file]")
        sys.exit(1)
    
    vvproj_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(vvproj_path).exists():
        print(f"Error: VVPROJ file not found: {vvproj_path}")
        sys.exit(1)
    
    try:
        generator = VOICEVOXSRTGenerator()
        generator.process_vvproj(vvproj_path, output_path)
        print("✅ NextStage Gaming チャンネル用SRT生成完了！")
        print("🎮 Street Fighter 6実況動画編集の効率化を実現しました")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()