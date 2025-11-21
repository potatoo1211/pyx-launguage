(Geminiに丸投げしました)
# Pyx Language Extension

**Pyx** は、Pythonのコーディング速度を爆速にするために設計された、強力なプリプロセッサ兼言語拡張機能です。特に**競技プログラミング（競プロ）**に最適化されています。

C言語スタイルのマクロ、名前空間による管理、ループの自動展開、ファイルのインクルード機能をPythonに追加し、VS Code上でのシンタックスハイライトも完備しています。

## ✨ 主な機能

- **マクロ & Define**: 再利用可能なコードブロックや、インラインマクロ（関数型マクロ）を定義できます。
- **名前空間 (Namespace)**: マクロ定義や `import` 文を分離されたブロックで管理し、名前の衝突や汚染を防ぎます。
- **ループの自動生成**: `$cases` を使うと、テストケース処理などの定型ループを自動で生成します。
- **ファイル展開**: 外部の `.pyx` や `.py` ファイルを相対パスで読み込み、1つのファイルに結合します。
- **ワンクリック実行**: トランスパイル（変換）から実行、そして**提出用コードのクリップボードコピー**までを一瞬で行います。

---

## 🚀 クイックスタート

1. 拡張子が `.pyx` のファイルを作成します（例: `main.pyx`）。
2. Pyx記法を使ってコードを書きます。
3. **`F5`** キーで実行、または **`Ctrl+Shift+B`** で「実行＋クリップボードへのコピー」を行います。

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
ライブラリごとに `import` やマクロを隔離できます。`$using` で必要なときだけ読み込みます（カンマ区切りで複数指定可）。

```python
$namespace MathLib
import math
!macro gcd(a, b):
    math.gcd(a, b)
$

# 必要な名前空間を読み込む（展開される）
$using MathLib

print(gcd(12, 18))
```

### 4. テストケースループ (`$cases`)
直下のコードブロックを指定された回数（または変数の値）分、`for` ループで囲みます。競プロのマルチテストケース問題に便利です。

```python
!define _I: int(input())

# 以下のブロックを T 回ループ実行する
$cases _I
    n = int(input())
    print(n * 2)
```
*Note: 引数が `1` の場合（例: `$cases 1`）、ループは生成されずそのまま展開されます。*

### 5. 外部ファイル展開 (`$expand`)
相対パスで指定したファイルを読み込んで結合します。自作ライブラリの管理に役立ちます。

```python
$expand ./library/graph.pyx
```

---

## ⌨️ ショートカットキー

| キー | コマンド | 説明 |
| :--- | :--- | :--- |
| **`F5`** | `Pyx: Run Only` | トランスパイルしてターミナルで実行します。 |
| **`Ctrl+Shift+B`** | `Pyx: Run and Copy` | トランスパイルして実行し、**変換後のPythonコードをクリップボードにコピー**します。 |

---

## 🔧 自動処理・仕様

この拡張機能は、裏側で以下の処理を自動的に行っています：

- **ヘッダー挿入**: 生成されたコードの先頭に、AI関与否定などの免責事項ヘッダーを自動挿入します。
- **オリジナルコード**: 変換前のPyxコードをコメントブロックとして出力ファイルに埋め込みます。
- **WSLサポート**: WSL環境で発生しやすいクリップボードの文字化けを自動的に回避します。
- **パス管理**: 実行ファイルのディレクトリを `sys.path` に自動追加するため、同階層のモジュール読み込みがエラーになりません。

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
[免責事項ヘッダー...]
'''
'''
[オリジナルコード...]
'''

# ... (展開されたimportなど) ...

for _ in range(int(input())):
    s = input()
    print(f"Hello, {s}!")
```

---

## 📦 インストール方法

1. 作成された `.vsix` パッケージをインストールしてください。
2. システムに `python` (または `python3`) がインストールされている必要があります。
3. 必要なPythonパッケージ（`atcoder` ライブラリなど）は適宜インストールしてください。

---
---

# Pyx Language Extension

**Pyx** is a powerful preprocessor and language extension for Python, designed to supercharge your coding speed—especially for Competitive Programming.

It adds C-style macros, namespaces, automatic loop expansion, and file inclusion to Python, all while maintaining clean syntax highlighting in VS Code.

## ✨ Features

- **Macros & Defines**: Define reusable code blocks and inline macros.
- **Namespaces**: Organize your macros and imports into isolated blocks.
- **Loop Shortcuts**: `$cases` automatically wraps code in loops.
- **File Expansion**: Import external `.pyx` or `.py` files directly into your code.
- **One-Click Execution**: Run and copy the transpiled Python code to your clipboard instantly.

---

## 🚀 Quick Start

1. Create a file with the `.pyx` extension (e.g., `main.pyx`).
2. Write your code using Pyx syntax.
3. Press **`F5`** to run, or **`Ctrl+Shift+B`** to run and copy the result to the clipboard.

---

## 📖 Syntax Guide

### 1. Macros (`!macro`)
Define function-like macros. Arguments can have default values.

```python
!macro pr(x):
    print("Value:", x)

!macro add(a, b=10):
    print(a + b)

pr(100)      # -> print("Value:", 100)
add(5)       # -> print(5 + 10)
```

### 2. Defines (`!define`)
Define simple text replacements or code blocks.

```python
!define INF: 10**18
!define _I: int(input())

x = _I       # -> x = int(input())
```

### 3. Namespaces (`$namespace` & `$using`)
Isolate imports and macros to avoid pollution. You can load multiple namespaces at once.

```python
$namespace MathLib
import math
!macro gcd(a, b):
    math.gcd(a, b)
$

$using MathLib

print(gcd(12, 18))
```

### 4. Test Cases Loop (`$cases`)
Automatically wraps the following code in a `for` loop. Perfect for competitive programming test cases.

```python
!define _I: int(input())

# Run the following block T times
$cases _I
    n = int(input())
    print(n * 2)
```
*Note: If the argument is `1` (e.g., `$cases 1`), no loop is generated.*

### 5. File Expansion (`$expand`)
Include other files relative to the current file.

```python
$expand ./library/graph.pyx
```

---

## ⌨️ Keybindings

| Key | Command | Description |
| :--- | :--- | :--- |
| **`F5`** | `Pyx: Run Only` | Transpiles and runs the code in the terminal. |
| **`Ctrl+Shift+B`** | `Pyx: Run and Copy` | Transpiles, runs, and **copies the Python code** to clipboard. |

---

## 🔧 Configuration

The extension automatically handles:
- **Header Insertion**: Adds a disclaimer header to the output.
- **Original Code**: Includes the original Pyx code as a comment in the output.
- **WSL Support**: Fixes clipboard encoding issues on WSL.
- **Path Management**: Automatically adds the file directory to `sys.path` so local imports work.

---

## 📝 Example

**main.pyx**
```python
$namespace IO
!define _I: int(input())
!define _S: input()
!macro pr(x):
    print(x)
$

$using IO

# Solve for T test cases
$cases _I
    s = _S
    pr(f"Hello, {s}!")
```

**Output (Generated Python)**
```python
'''
[Disclaimer Header...]
'''
'''
[Original Code...]
'''

# ... (imports if any) ...

for _ in range(int(input())):
    s = input()
    print(f"Hello, {s}!")
```

---

## 📦 Installation

1. Install the `.vsix` package.
2. Ensure you have `python` (or `python3`) installed.
3. (Optional) On Linux/WSL, install `xclip` or `xsel` if clipboard issues persist (though `clip.exe` is supported for WSL).

---

**Happy Coding!**