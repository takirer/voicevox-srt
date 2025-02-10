# VOICEVOXから発話と完全同期するSRTファイルを出力するツールを作ったよ

## はじめに
VOICEVOXで生成したvvprojファイルから、**発話と完全同期するSRTファイルを出力するツール**を作成しました。

このツールは、入力のJSON形式のvvprojファイルから、テキストの自然な分割と音声時間の詳細な計算を行い、スライディングウィンドウ方式、ウィンドウ内句読点探索、およびトークンベース再分割などの技法を用いて各字幕行のレイアウトを最適化することで、字幕の自動配置を実現しています。

![](https://raw.githubusercontent.com/yKesamaru/voicevox-srt/refs/heads/main/assets/eye-catch.png)

## 例
[YouTubeで見る](https://www.youtube.com/watch?v=GlfdhSk6bEM)

![](https://raw.githubusercontent.com/yKesamaru/voicevox-srt/refs/heads/main/assets/output.gif)

![](https://raw.githubusercontent.com/yKesamaru/voicevox-srt/refs/heads/main/assets/2025-02-09-17-32-19.png)

## リポジトリ
yKesamaru / voicevox-srt

https://github.com/yKesamaru/voicevox-srt/tree/main

## 使い方
1. VOICEVOXで音声を生成します。
2. プロジェクトを`vvproj`として保存します。
3. `voicevox-srt.py`を実行します。
   ```python
   python voicevox-srt.py
   ```
4. SRTファイルをkdenliveなどの動画編集ソフトに読み込ませます。
5. 字幕の自動配置が完了しました。

字幕を、**タイムラインに合わせながらチマチマ調整する必要がなくなります！**

:::details 環境構築など
## ホスト環境
開発にあたり使用したホスト環境を以下に示します。
```bash
$ python -V
Python 3.10.12
$ inxi -S --filter
System:
  Kernel: 6.8.0-52-generic x86_64 bits: 64 Desktop: Unity
    Distro: Ubuntu 22.04.5 LTS (Jammy Jellyfish)
```

## MeCabのインストール
スクリプト内で使用している`fugashi`は、MeCabのPythonラッパーライブラリです。MeCabをインストールすることで、`fugashi`を使用することができます。
```bash
sudo apt-get update
sudo apt-get install mecab libmecab-dev mecab-ipadic-utf8
```
スクリプト内ではGenericTaggerを使用してMeCabの設定ファイルとUTF-8版辞書を明示的に指定して初期化することが必要です。
```python
tagger = GenericTagger("-r /etc/mecabrc -d /var/lib/mecab/dic/ipadic-utf8")
```
MeCabの設定ファイルとUTF-8版辞書のパスは、環境によって異なる場合がありますので、適宜変更してください。
:::

## VOICEVOX ISSUE
:::details #1669
[[機能向上]SRTファイルを利用した音声合成 #1669](https://github.com/VOICEVOX/voicevox/issues/1669)
> SRTという字幕のためのファイル形式を利用した音声合成の機能を実装してほしいです。
> SRTファイルによって音声合成するときそのSRTファイルの時間と一致するように合成・変換してほしいです。
> 例えば、
> ```srt
> 1
> 00:00:00,000 --> 00:00:04,500
> こんにちは、お元気ですか。
> 
> 2
> 00:00:04,500 --> 00:00:09,120
> はい、調子が良いです
> 
> 3
> 00:00:09,120 --> 00:00:12,160
> 
> 
> 4
> 00:00:12,160 --> 00:00:15,840
> そして、ここで大いなる発表です。
> ```
> というSRTファイルがあるとしたら最初の「こんにちは、お元気ですか」が4.5秒ちょうどか収まるように速度を調節して合成して、他の部分も同様に時間内に収まるように合成して、空白の部分も考量して一つの音声ファイルになるようにしてほしいです。動画編集ソフトにその一つの音声ファイルとSRTファイルを読み込ませるとそのまま音声と字幕がずれることがなく使えるようにしてほしいです。
> （中略）
> 主な新しい処理は時間を考慮して速度を調節するくらいなので、APIの速度調節のパラメータを利用して外部アプリとして実装すればよいと正直思いました。ふと思ったのですが、そのような場合に既に作られているかどうか確認できるVOICEVOXを活用したオープンソースのアプリや拡張機能一覧のようなものは公式ではないのですか？
:::

ということでしたので作りました。
各発話タイミングを計算するアルゴリズムは、VOICEVOXの音声合成エンジンによって生成される`vvproj`ファイルを解析しています。

## アルゴリズムの概要
このツールには「文節の分割機能」と「各字幕の時間の長さを得る機能」がありますが、ここでは「各字幕の時間の長さを得る機能」に絞って説明します。
### vvprojファイル構造
vvprojファイルはJSON形式で記述されており、以下のような構造をしています。
:::details JSON構造
```json
    "audioItems": {
      "0d0f8b31-4626-40f1-8255-f24f377defc7": {
        "text": "Huaweiの最新AIプロセッサ「Ascend910」とRISCVへの展望",
        "voice": {
          "engineId": "074fc39e-678b-4c13-8916-ffca8d505d1d",
          "speakerId": "9f3ee141-26ad-437e-97bd-d22298d02ad2",
          "styleId": 20
        },
        "query": {
          "accentPhrases": [
            {
              "moras": [
                {
                  "text": "ファ",
                  "consonant": "f",
                  "consonantLength": 0.0747395008802414,
                  "vowel": "a",
                  "vowelLength": 0.13301876187324524,
                  "pitch": 5.738225936889648
                },
                {
                  "text": "ア",
                  "vowel": "a",
                  "vowelLength": 0.10208874940872192,
                  "pitch": 5.882820129394531
                },
                {
                  "text": "ウェ",
                  "consonant": "w",
                  "consonantLength": 0.029048621654510498,
                  "vowel": "e",
                  "vowelLength": 0.12287335097789764,
                  "pitch": 5.772856712341309
                },
                {
                  "text": "イ",
                  "vowel": "i",
                  "vowelLength": 0.05447140708565712,
                  "pitch": 5.546143531799316
                },
```
:::

- `"audioItems"`キー
  `"talk"`内にあり、各音声項目（字幕に対応する）の辞書の集合です。
  - 各音声項目の`"text"`キーには、字幕として表示するテキストが格納されています。
  - 同じ音声項目の`"query"`キーには、発話データが含まれており、そこから以下の情報を取得します:
    - `"accentPhrases"`:各アクセントフレーズに関する情報。
    - `"moras"`:各アクセントフレーズ内で、各モーラの`"vowelLength"`（母音の長さ）と`"consonantLength"`（子音の長さ）。
    - `"pauseMora"`:アクセントフレーズ間のポーズを示す情報（主に`"vowelLength"`）。
    - `"prePhonemeLength"`と`"postPhonemeLength"`:発話前後の無音時間。

### 各字幕の時間の長さを得るアルゴリズム
#### 音声時間計算の流れ
関数`calculate_audio_duration(query)`において、各音声項目の`"query"`辞書から以下の情報を取得し、音声の再生時間を算出しています。
1. アクセントフレーズ内のモーラ計算
   - 各`"accentPhrases"`内の`"moras"`リストを走査し、各モーラの`"vowelLength"`と`"consonantLength"`を合計します。

2. ポーズの考慮
   - 各アクセントフレーズ内に存在する`"pauseMora"`の`"vowelLength"`を加算し、アクセントフレーズ間の間隔（ポーズ）を反映させます。

3. 前後の無音時間の付加
   - `"prePhonemeLength"`と`"postPhonemeLength"`の値を加算することで、発話開始前および終了後の無音部分も考慮しています。

この総和をもとに、各字幕ブロックの開始時刻は累積時間、終了時刻は開始時刻に発話時間を加えたものとなり、SRTフォーマット（hh:mm:ss,ms）に整形して出力されます。

https://github.com/yKesamaru/voicevox-srt/blob/a6e87db07d1bb95d6811c9ac201aa090b0483ce6/voicevox-srt.py#L63-L84

https://github.com/yKesamaru/voicevox-srt/blob/a6e87db07d1bb95d6811c9ac201aa090b0483ce6/voicevox-srt.py#L253-L292

現実的な長さの動画を作成する限り、このアルゴリズムによって生成されるSRTファイルは、VOICEVOXの音声合成エンジンによって生成される音声とほぼ同期するようになります。

## 最後に
字幕のスマートな自動改行を実現するためにMeCabを使用していますが、それが必要ないのであればかなりスマートなコードになるはずです。

ツールとして公開しましたが、おそらくこれが使える人はプログラムを理解している人です。それに対してこれを必要とする人はプログラムとは無縁の方だと思います。

ツールとしてどういう形が良いのか？と悩みましたが、良いアイデアがありましたら教えてくださると嬉しいです。