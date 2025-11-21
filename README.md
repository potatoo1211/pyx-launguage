# Pyx Language Extension

**Pyx** は、Pythonのコーディング速度を爆速にするために設計された、強力なプリプロセッサ兼言語拡張機能です。特に**競技プログラミング（競プロ）**に最適化されています。

C言語スタイルのマクロ、名前空間による管理、ループの自動展開、ファイル結合機能をPythonに追加し、VS Code上でのシンタックスハイライトも完備しています。

## ✨ 主な機能

- **マクロ & Define**: 再利用可能なコードブロックや、インラインマクロを定義できます。
- **名前空間 (Namespace)**: マクロ定義や `import` 文を分離して管理。カンマ区切りで複数読み込みも可能です。
- **ループの自動生成**: `$cases` で定型ループを自動生成。`1` の場合はループしない賢い挙動。
- **ファイル展開**: 外部ファイルを相対パスで読み込み、1つに結合します（ライブラリ管理に最適）。
- **スマート実行**: トランスパイル→実行→**終了後にクリップボードへコピー**をワンアクションで。
- **フルカスタマイズ**: 免責事項の文章やコメントスタイル、表示有無を自由に設定可能。

---

## 🚀 クイックスタート

1. 拡張子が `.pyx` のファイルを作成します（例: `main.pyx`）。
2. Pyx記法を使ってコードを書きます。
3. **`F5`** で実行のみ、**`Ctrl+Shift+B`** で「実行して終了後にコピー」を行います。

---

## 📖 構文ガイド

### 1. マクロ定義 (`!macro`)
関数のように引数を取るマクロを定義します。デフォルト引数も使用可能です。

```python
!macro pr(x):
    print("Value:", x)

!macro add(a, b=10):
    print(a + b)

pr(100)      # -> print("Value:", 100)
add(5)       # -> print(5 + 10)
```

### 2. 単純置換 (`!define`)
単純な文字列の置き換えや、引数を取らないコードブロックを定義します。

```python
!define INF: 10**18
!define _I: int(input())

x = _I       # -> x = int(input())
```

### 3. 名前空間 (`$namespace` & `$using`)
ライブラリごとに `import` やマクロを隔離できます。`$using` で読み込みます。カンマ区切りで複数指定も可能です。

```python
$namespace MathLib
import math
!macro gcd(a, b):
    math.gcd(a, b)
$

$namespace IOLib
!macro pr(x): print(x)
$

# カンマ区切りで複数の名前空間を展開
$using MathLib, IOLib

pr(gcd(12, 18))
```

### 4. テストケースループ (`$cases`)
直下のコードブロックを指定された回数（または変数の値）分、`for` ループで囲みます。

```python
!define _I: int(input())

# T回ループするコードに展開されます
$cases _I
    n = int(input())
    print(n * 2)
```
*Note: 引数が `1` の場合（例: `$cases 1`）、ループは生成されずそのまま展開されます（単一テストケース用）。*

### 5. 外部ファイル展開 (`$expand`)
相対パスで指定したファイルを読み込んで結合します。

```python
$expand ./library/graph.pyx
```

---

## ⚙️ 設定 (Configuration)

VS Codeの設定画面 (`Ctrl + ,`) で `Pyx` と検索すると、以下の項目を変更できます。

| 設定項目 | 説明 | デフォルト値 |
| :--- | :--- | :--- |
| `pyx.showDisclaimer` | 生成コードの先頭に免責事項ヘッダーを表示するか | `true` |
| `pyx.showOriginalCode` | 生成コード内に変換前のPyxコードをコメントとして残すか | `true` |
| `pyx.disclaimerText` | **免責事項の文章そのもの**を自由に編集できます | (デフォルトの文章) |
| `pyx.commentStyle` | ヘッダーやオリジナルコードを囲むコメント記号 | `'''` |

---

## ⌨️ ショートカットキー

| キー | コマンド | 動作 |
| :--- | :--- | :--- |
| **`F5`** | `Pyx: Run Only` | トランスパイルしてターミナルで実行します（コピーはしません）。 |
| **`Ctrl+Shift+B`** | `Pyx: Run and Copy` | トランスパイルして実行し、**プログラムが終了（または中断）した直後に**コードをクリップボードにコピーします。 |

---

## 🔧 自動処理・仕様

この拡張機能は、快適なコーディングのために裏側で以下を行っています：

- **スマートコピー**: プログラム実行中はコピーせず、正常終了または `Ctrl+C` で中断したタイミングでコピーを行います。
- **WSLサポート**: WSL環境で発生するクリップボードの文字化け（日本語）を自動的に回避します。
- **パス自動解決**: 実行ファイルのディレクトリを `sys.path` に自動追加するため、同階層の `.py` ファイル読み込みもエラーになりません。

---

## 📝 サンプルコード

**main.pyx**
```python
$namespace IO
!define _I: int(input())
!define _S: input()
!macro pr(x):
    print(x)
$

$using IO

# テストケース数 T だけループ
$cases _I
    s = _S
    pr(f"Hello, {s}!")
```

**出力結果 (生成されるPythonコード)**
```python
'''
このプログラムは特定のアルゴリズムにより変換されたもので、AIは一切関与していません。
This program was transformed by a specific algorithm, and no AI was involved in the process.

github:
https://github.com/potatoo1211/pyx-launguage
'''
'''
[Original Code]
$namespace IO
!define _I: int(input())
!define _S: input()
!macro pr(x):
    print(x)
$

$using IO

# テストケース数 T だけループ
$cases _I
    s = _S
    pr(f"Hello, {s}!")
'''


# テストケース数 T だけループ
for _ in range(int(input())):
        s = input()
        print(f"Hello, {s}!")
```

---

## 📦 インストール方法

1. パッケージ化された `.vsix` ファイルをインストールしてください。
2. システムに `python` (または `python3`) がインストールされている必要があります。
3. 必要なPythonパッケージ（`atcoder` ライブラリなど）は適宜インストールしてください。

---

**Happy Coding!**