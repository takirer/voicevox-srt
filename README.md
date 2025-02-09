# VOICEVOX-SRT: VOICEVOXからSRTファイルを生成するツール

## 特長
- 完璧なタイミングの字幕を生成。出力されるSRTファイルは、音声の再生時間に合わせて字幕が表示されるようになっています。kdenliveなどの動画編集ソフトに読み込ませることで、字幕の自動配置が可能です。
- 

![](assets/2025-02-09-17-32-19.png)

[YouTubeで見る](https://youtu.be/a7P8STjVrlA)


## 使い方
1. VOICEVOXで音声を生成します。
2. プロジェクトを`vvproj`として保存します。
3. `voicevox-srt.py`を実行します。
   ```python
   python voicevox-srt.py
   ```
4. SRTファイルをkdenliveなどの動画編集ソフトに読み込ませます。
5. 字幕の自動配置が完了しました。

## 利用規約
個人がVOICEVOX-SRTを用いて生成したSRTファイルを用いて作成した動画は、「VOICEVOX-SRT: 」