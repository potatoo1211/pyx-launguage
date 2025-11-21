import sys
import re
import os
import argparse
import subprocess
import base64
import traceback

# ---------------------------------------------------------
# 定数・設定
# ---------------------------------------------------------
DEFAULT_HEADER = """\u3053\u306e\u30d7\u30ed\u30b0\u30e9\u30e0\u306f\u7279\u5b9a\u306e\u30a2\u30eb\u30b4\u30ea\u30ba\u30e0\u306b\u3088\u308a\u5909\u63db\u3055\u308c\u305f\u3082\u306e\u3067\u3001AI\u306f\u4e00\u5207\u95a2\u4e0e\u3057\u3066\u3044\u307e\u305b\u3093\u3002
This program was transformed by a specific algorithm, and no AI was involved in the process.

github:
https://github.com/potatoo1211/pyx-launguage"""

# 無限ループ検知用リミット (1行に対する展開回数上限)
MAX_EXPANSION_DEPTH = 1000

# ---------------------------------------------------------
# Data Structures
# ---------------------------------------------------------
class SourceLine:
    """ コードの1行と、その由来（ファイル名、行番号）を保持するクラス """
    def __init__(self, content, filename, lineno):
        self.content = content # 行の内容 (改行込み)
        self.filename = filename
        self.lineno = lineno   # 1-based index

    def __repr__(self):
        return f"Line({self.lineno}: {self.content.strip()})"

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
def copy_to_clipboard(text):
    try:
        is_wsl = "microsoft" in os.uname().release.lower()
        if is_wsl:
            proc = subprocess.Popen(['clip.exe'], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode('cp932', errors='ignore'))
            print(">> Code copied to clipboard (WSL mode).")
        else:
            import pyperclip
            pyperclip.copy(text)
            print(">> Code copied to clipboard.")
    except Exception as e:
        print(f">> Copy failed: {e}")

def smart_split_args(text):
    args = []
    current = []
    depth = 0
    in_quote = False
    quote_char = None
    escape = False

    for char in text:
        if escape:
            current.append(char)
            escape = False
            continue
        if char == '\\':
            current.append(char)
            escape = True
            continue

        if in_quote:
            if char == quote_char:
                in_quote = False
                quote_char = None
            current.append(char)
        else:
            if char in '"\'':
                in_quote = True
                quote_char = char
                current.append(char)
            elif char in '([{':
                depth += 1
                current.append(char)
            elif char in ')]}':
                depth -= 1
                current.append(char)
            elif char == ',' and depth == 0:
                args.append("".join(current).strip())
                current = []
            else:
                current.append(char)
    if current:
        args.append("".join(current).strip())
    return [a for a in args if a]

def safe_replace(text, mapping):
    for k, v in mapping.items():
        pattern = r'\b' + re.escape(k) + r'\b'
        text = re.sub(pattern, v, text)
    return text

def dedent_block(source_lines):
    """ SourceLineのリストを受け取り、インデントを除去して返す """
    if not source_lines: return []
    
    # 最初の有効な行を探してインデント幅を決める
    indent_len = 0
    first_valid = next((l for l in source_lines if l.content.strip()), None)
    if first_valid:
        indent_len = len(first_valid.content) - len(first_valid.content.lstrip())

    dedented = []
    for sl in source_lines:
        txt = sl.content
        if not txt.strip():
            # 空行はそのまま、ただし内容は空に
            dedented.append(SourceLine("\n", sl.filename, sl.lineno))
        else:
            # インデント除去
            new_txt = txt[indent_len:] if len(txt) >= indent_len else txt.lstrip()
            dedented.append(SourceLine(new_txt, sl.filename, sl.lineno))
    return dedented

# ---------------------------------------------------------
# Definition Class
# ---------------------------------------------------------
class Definition:
    def __init__(self, name, args_str, body_source_lines, is_macro):
        self.name = name
        self.is_macro = is_macro
        # body_source_lines は SourceLine のリスト
        self.body_lines = dedent_block(body_source_lines)
        self.params = [] 

        if is_macro and args_str.strip():
            raw_args = smart_split_args(args_str)
            for raw_arg in raw_args:
                if '=' in raw_arg:
                    parts = raw_arg.split('=', 1)
                    self.params.append({ 'name': parts[0].strip(), 'default': parts[1].strip() })
                else:
                    self.params.append({ 'name': raw_arg.strip(), 'default': None })

# ---------------------------------------------------------
# Transpiler Logic
# ---------------------------------------------------------
class PyxTranspiler:
    def __init__(self):
        self.namespaces = {} 
        self.active_definitions = {} 

    def load_file(self, filepath):
        """ ファイルを読み込み、SourceLineのリストとして返す """
        if not os.path.exists(filepath):
            return None
        
        abs_path = os.path.abspath(filepath)
        filename = os.path.basename(abs_path)
        lines = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for i, line_content in enumerate(f):
                lines.append(SourceLine(line_content, filename, i + 1))
        return lines

    def expand_files(self, filepath, visited=None):
        """ $expand を再帰的に解決し、SourceLineのリストを結合して返す """
        if visited is None: visited = set()
        abs_path = os.path.abspath(filepath)
        if abs_path in visited: return []
        visited.add(abs_path)

        raw_sl_lines = self.load_file(filepath)
        if raw_sl_lines is None:
            print(f"Warning: Could not find file to expand: {filepath}")
            return []

        expanded_lines = []
        base_dir = os.path.dirname(abs_path)

        for sl in raw_sl_lines:
            sline = sl.content.strip()
            if sline.startswith('$expand'):
                try:
                    target_rel = sline.split(None, 1)[1].strip()
                    target_full = os.path.join(base_dir, target_rel)
                    expanded_lines.extend(self.expand_files(target_full, visited))
                except IndexError: pass 
            else:
                expanded_lines.append(sl)
        return expanded_lines

    def extract_namespaces(self, source_lines):
        main_lines = []
        current_ns = None
        buffer = []

        for sl in source_lines:
            sline = sl.content.strip()
            if sline.startswith('$namespace'):
                parts = sline.split()
                current_ns = parts[1] if len(parts) > 1 else "unknown"
                buffer = []
                continue 
            if sline == '$' and current_ns:
                if current_ns not in self.namespaces:
                    self.namespaces[current_ns] = []
                self.namespaces[current_ns].extend(buffer)
                current_ns = None
                buffer = []
                continue 
            
            if current_ns:
                buffer.append(sl)
            else:
                main_lines.append(sl)
        return main_lines

    def parse_namespace_content(self, source_lines):
        definitions = {}
        raw_sl_lines = []
        
        # namespace内もインデント除去
        source_lines = dedent_block(source_lines)
        
        i = 0
        while i < len(source_lines):
            sl = source_lines[i]
            sline = sl.content.strip()
            
            match_macro = re.match(r'^!macro\s+(\w+)\s*\((.*?)\)\s*:\s*(.*)$', sline)
            match_define = re.match(r'^!define\s+(\w+)\s*:\s*(.*)$', sline)
            
            if match_macro or match_define:
                is_macro = bool(match_macro)
                match = match_macro if is_macro else match_define
                name = match.group(1)
                
                if is_macro:
                    args_str = match.group(2)
                    inline_body = match.group(3)
                else:
                    args_str = ""
                    inline_body = match.group(2)
                
                body = []
                if inline_body and inline_body.strip():
                    # 1行定義の場合、同じ行番号情報を継承した新しいSourceLineを作る
                    body.append(SourceLine(inline_body + "\n", sl.filename, sl.lineno))
                else:
                    i += 1
                    while i < len(source_lines):
                        next_sl = source_lines[i]
                        # 空行でない かつ インデントがない -> ブロック終了
                        if next_sl.content.strip() and not (next_sl.content.startswith(' ') or next_sl.content.startswith('\t')):
                            i -= 1
                            break
                        body.append(next_sl)
                        i += 1
                definitions[name] = Definition(name, args_str, body, is_macro)
            else:
                raw_sl_lines.append(sl)
            i += 1
        return definitions, raw_sl_lines

    def process_line_expansion(self, sl):
        line_content = sl.content
        
        # 1. define (引数なし) 置換
        for name, definition in self.active_definitions.items():
            if not definition.is_macro:
                pattern = r'\b' + re.escape(name) + r'\b'
                if re.search(pattern, line_content):
                    return True, self.expand_body(definition, [], sl, name)
        
        # 2. macro (引数あり) 置換
        for name, definition in self.active_definitions.items():
            if definition.is_macro:
                pattern = r'\b' + re.escape(name) + r'\s*\('
                match = re.search(pattern, line_content)
                if match:
                    start_idx = match.end()
                    depth = 1
                    end_idx = -1
                    
                    in_quote = False
                    quote_char = None
                    escape = False

                    for k in range(start_idx, len(line_content)):
                        char = line_content[k]
                        if escape: escape = False; continue
                        if char == '\\': escape = True; continue
                        
                        if in_quote:
                            if char == quote_char: in_quote = False
                        else:
                            if char in '"\'': in_quote = True; quote_char = char
                            elif char == '(': depth += 1
                            elif char == ')': depth -= 1
                        
                        if depth == 0:
                            end_idx = k
                            break
                    
                    if end_idx != -1:
                        full_match = line_content[match.start():end_idx+1]
                        args_str = line_content[start_idx:end_idx]
                        call_args = smart_split_args(args_str)
                        return True, self.expand_body(definition, call_args, sl, full_match)
        return False, [sl]

    def expand_body(self, definition, call_args, original_sl, match_str):
        indent_match = re.match(r'^(\s*)', original_sl.content)
        base_indent = indent_match.group(1) if indent_match else ""
        
        replacements = {}
        for i, param in enumerate(definition.params):
            val = "None"
            if i < len(call_args): val = call_args[i]
            elif param['default'] is not None: val = param['default']
            replacements[param['name']] = val
        
        is_inline = (len(definition.body_lines) == 1)
        if is_inline:
            body_sl = definition.body_lines[0]
            body_txt = body_sl.content.strip()
            body_txt = safe_replace(body_txt, replacements)
            new_content = original_sl.content.replace(match_str, body_txt)
            # 展開後の行は、呼び出し元の行番号を引き継ぐ（エラー時に呼び出し元を指すため）
            return [SourceLine(new_content, original_sl.filename, original_sl.lineno)]
        else:
            expanded_lines = []
            for body_sl in definition.body_lines:
                temp_txt = safe_replace(body_sl.content, replacements)
                new_content = base_indent + temp_txt.rstrip('\n') + "\n"
                # 複数行展開の場合も、基本は呼び出し元の行番号にマッピングする
                expanded_lines.append(SourceLine(new_content, original_sl.filename, original_sl.lineno))
            return expanded_lines

    def transpile(self, main_file):
        all_lines = self.expand_files(main_file)
        main_code_lines = self.extract_namespaces(all_lines)
        if 'default' in self.namespaces:
            defs, raw = self.parse_namespace_content(self.namespaces['default'])
            self.active_definitions.update(defs)
            main_code_lines[0:0] = raw

        final_sl_lines = []
        cases_indent_level = 0
        
        i = 0
        expansion_counter = 0 # 無限ループ検知用

        while i < len(main_code_lines):
            sl = main_code_lines[i]
            sline = sl.content.strip()

            # $using
            if sline.startswith('$using'):
                parts = sline.split(None, 1)
                if len(parts) > 1:
                    target_ns_list = [ns.strip() for ns in parts[1].split(',')]
                    all_raw_codes = []
                    for target_ns in target_ns_list:
                        if target_ns in self.namespaces:
                            defs, raw_code = self.parse_namespace_content(self.namespaces[target_ns])
                            self.active_definitions.update(defs)
                            all_raw_codes.extend(raw_code)
                    if all_raw_codes:
                        main_code_lines[i+1:i+1] = all_raw_codes
                i += 1
                expansion_counter = 0
                continue

            # !macro / !define 定義
            match_macro = re.match(r'^!macro\s+(\w+)\s*\((.*?)\)\s*:\s*(.*)$', sline)
            match_define = re.match(r'^!define\s+(\w+)\s*:\s*(.*)$', sline)
            if match_macro or match_define:
                is_macro = bool(match_macro)
                match = match_macro if is_macro else match_define
                name = match.group(1)
                if is_macro:
                    args_str = match.group(2)
                    inline_body = match.group(3)
                else:
                    args_str = ""
                    inline_body = match.group(2)
                body = []
                if inline_body and inline_body.strip():
                    body.append(SourceLine(inline_body + "\n", sl.filename, sl.lineno))
                else:
                    i += 1
                    while i < len(main_code_lines):
                        next_sl = main_code_lines[i]
                        if next_sl.content.strip() and not (next_sl.content.startswith(' ') or next_sl.content.startswith('\t')):
                            i -= 1
                            break
                        body.append(next_sl)
                        i += 1
                self.active_definitions[name] = Definition(name, args_str, body, is_macro)
                i += 1
                expansion_counter = 0
                continue
            
            # マクロ展開
            expanded, new_sl_lines = self.process_line_expansion(sl)
            if expanded:
                # ★無限ループ検知
                expansion_counter += 1
                if expansion_counter > MAX_EXPANSION_DEPTH:
                    raise RuntimeError(f"Infinite macro expansion detected at line {sl.lineno}: {sline}")
                
                main_code_lines[i:i+1] = new_sl_lines
                continue # インデックスを進めずに再評価
            
            # 展開されなかったらカウンタをリセットして次へ
            expansion_counter = 0
            
            # $cases
            if sline.startswith('$cases'):
                parts = sline.split(None, 1)
                if len(parts) > 1:
                    count_expr = parts[1].strip()
                    if count_expr == '1':
                        pass
                    else:
                        indent_match = re.match(r'^(\s*)', sl.content)
                        base_indent = indent_match.group(1) if indent_match else ""
                        extra_indent = "    " * cases_indent_level
                        loop_txt = f"{base_indent}{extra_indent}for _ in range({count_expr}):\n"
                        final_sl_lines.append(SourceLine(loop_txt, sl.filename, sl.lineno))
                        cases_indent_level += 1
                i += 1
                continue
            
            # 通常行出力
            if cases_indent_level > 0:
                if sl.content.strip():
                    new_content = ("    " * cases_indent_level) + sl.content
                    final_sl_lines.append(SourceLine(new_content, sl.filename, sl.lineno))
                else:
                    final_sl_lines.append(sl)
            else:
                final_sl_lines.append(sl)
            i += 1
        
        return final_sl_lines

# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file', help='Input file')
    parser.add_argument('--run', '-r', action='store_true')
    parser.add_argument('--copy', '-c', action='store_true')
    parser.add_argument('--out', '-o')
    parser.add_argument('--no-header', action='store_true')
    parser.add_argument('--no-original', action='store_true')
    parser.add_argument('--comment-style', default="'''")
    parser.add_argument('--header-b64', default="")

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: Main file not found: {args.file}")
        return

    try:
        with open(args.file, 'r', encoding='utf-8') as f:
            original_code = f.read()
    except:
        original_code = "Could not read original file."

    # ヘッダー準備
    if args.header_b64:
        try:
            header_content = base64.b64decode(args.header_b64).decode('utf-8')
        except:
            header_content = DEFAULT_HEADER
    else:
        header_content = DEFAULT_HEADER

    transpiler = PyxTranspiler()
    try:
        # SourceLineのリストを取得
        final_sl_list = transpiler.transpile(args.file)
    except Exception as e:
        print(f"Transpile Error: {e}")
        return

    # 最終的なコード文字列と、行番号マッピングを作成
    # generated_lines[i] は final_sl_list[source_map[i]] に対応... ではなく
    # 行番号ベースで管理する
    
    final_output_lines = []
    line_mapping = {} # 生成後の行番号(0-based) -> SourceLineオブジェクト

    # 1. 免責事項
    if not args.no_header:
        header_block = f"{args.comment_style}\n{header_content}\n{args.comment_style}\n"
        for line in header_block.splitlines(True):
            final_output_lines.append(line)
            # ヘッダーはマッピングなし (None)

    # 2. オリジナルコード
    if not args.no_original:
        orig_block = f"{args.comment_style}\n[Original Code]\n{original_code}\n{args.comment_style}\n"
        for line in orig_block.splitlines(True):
            final_output_lines.append(line)

    # 3. 本体
    current_line_idx = len(final_output_lines)
    for sl in final_sl_list:
        # 整形（連続改行の削除など）はSourceMapを複雑にするので、
        # ここでは最低限の結合のみ行い、実行時のズレをなくす
        final_output_lines.append(sl.content)
        line_mapping[current_line_idx] = sl
        current_line_idx += 1
    
    final_output = "".join(final_output_lines)
    
    # 整形（空行削除）は保存・コピー用に行うが、実行用（exec）はズレ防止のためそのままが良いかも？
    # いや、ユーザー体験的には整形後のコードがコピーされるので、それに合わせるべき。
    # しかし正規表現で一括置換するとSourceMapが壊れる。
    # 今回は「整形はコピー時のみ」または「整形なし」にするのが安全。
    # ここでは「整形なし」で進める（改行が多くても動作に問題はない）

    # ファイル保存
    if args.out:
        with open(args.out, 'w', encoding='utf-8-sig') as f:
            f.write(final_output)
        print(f"Saved to {args.out}")

    # 実行
    if args.run:
        print(">> Executing...")
        print("-" * 20)
        
        file_dir = os.path.dirname(os.path.abspath(args.file))
        if file_dir not in sys.path:
            sys.path.insert(0, file_dir)
            
        exec_globals = {}
        try:
            # 擬似的なファイル名を指定して実行
            code_obj = compile(final_output, "generated_pyx.py", "exec")
            exec(code_obj, exec_globals)
        except KeyboardInterrupt:
            print("\n>> Execution Interrupted.")
        except Exception:
            # ★エラーハンドリング（Source Map適用）
            print("-" * 20)
            print("Runtime Error (Mapped to Source):")
            
            # スタックトレースを取得
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb_list = traceback.extract_tb(exc_traceback)
            
            for frame in tb_list:
                filename = frame.filename
                lineno = frame.lineno # 1-based
                funcname = frame.name
                line_text = frame.line
                
                if filename == "generated_pyx.py":
                    # マッピングを検索 (linenoは1-basedなので-1する)
                    mapped_idx = lineno - 1
                    if mapped_idx in line_mapping:
                        src_sl = line_mapping[mapped_idx]
                        print(f'  File "{src_sl.filename}", line {src_sl.lineno}, in {funcname}')
                        print(f'    {src_sl.content.strip()}')
                    else:
                        # ヘッダー部分などのエラー
                        print(f'  File "Generated Code", line {lineno}, in {funcname}')
                        print(f'    {line_text}')
                else:
                    # ライブラリ等のエラーはそのまま表示
                    print(f'  File "{filename}", line {lineno}, in {funcname}')
                    print(f'    {line_text}')
            
            print(f"{exc_type.__name__}: {exc_value}")

        finally:
            if args.copy:
                print("-" * 20)
                copy_to_clipboard(final_output)

    elif args.copy:
         copy_to_clipboard(final_output)

if __name__ == '__main__':
    main()