import sys
import re
import os
import argparse
import subprocess

# ---------------------------------------------------------
# 必須ヘッダー (免責事項)
# ---------------------------------------------------------
HEADER_TEXT = """'''
\u3053\u306e\u30d7\u30ed\u30b0\u30e9\u30e0\u306f\u7279\u5b9a\u306e\u30a2\u30eb\u30b4\u30ea\u30ba\u30e0\u306b\u3088\u308a\u5909\u63db\u3055\u308c\u305f\u3082\u306e\u3067\u3001AI\u306f\u4e00\u5207\u95a2\u4e0e\u3057\u3066\u3044\u307e\u305b\u3093\u3002
This program was transformed by a specific algorithm, and no AI was involved in the process.

github:
https://github.com/potatoo1211/pyx-launguage
'''
"""

# ---------------------------------------------------------
# Helper: クリップボードコピー
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

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def smart_split_args(text):
    args = []
    current = []
    depth = 0
    for char in text:
        if char in '([{': depth += 1
        elif char in ')]}': depth -= 1
        elif char == ',' and depth == 0:
            args.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        args.append("".join(current).strip())
    return [a for a in args if a]

def safe_replace(text, mapping):
    for k, v in mapping.items():
        pattern = r'\b' + re.escape(k) + r'\b'
        text = re.sub(pattern, v, text)
    return text

def dedent_block(lines):
    if not lines: return []
    first_valid_line = next((l for l in lines if l.strip()), None)
    if not first_valid_line: return lines
    indent_len = len(first_valid_line) - len(first_valid_line.lstrip())
    dedented = []
    for line in lines:
        if not line.strip():
            dedented.append("")
        else:
            dedented.append(line[indent_len:] if len(line) >= indent_len else line.lstrip())
    return dedented

# ---------------------------------------------------------
# Definition Class
# ---------------------------------------------------------
class Definition:
    def __init__(self, name, args_str, body_lines, is_macro):
        self.name = name
        self.is_macro = is_macro
        self.body_lines = dedent_block(body_lines)
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
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.readlines()

    def expand_files(self, filepath, visited=None):
        if visited is None: visited = set()
        abs_path = os.path.abspath(filepath)
        if abs_path in visited: return []
        visited.add(abs_path)

        raw_lines = self.load_file(filepath)
        if raw_lines is None:
            print(f"Warning: Could not find file to expand: {filepath}")
            return []

        expanded_lines = []
        base_dir = os.path.dirname(abs_path)

        for line in raw_lines:
            sline = line.strip()
            if sline.startswith('$expand'):
                try:
                    target_rel = sline.split(None, 1)[1].strip()
                    target_full = os.path.join(base_dir, target_rel)
                    expanded_lines.extend(self.expand_files(target_full, visited))
                except IndexError: pass 
            else:
                expanded_lines.append(line)
        return expanded_lines

    def extract_namespaces(self, lines):
        main_lines = []
        current_ns = None
        buffer = []

        for line in lines:
            sline = line.strip()
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
                buffer.append(line)
            else:
                main_lines.append(line)
        return main_lines

    def parse_namespace_content(self, lines):
        definitions = {}
        raw_lines = []
        lines = dedent_block(lines)
        i = 0
        while i < len(lines):
            line = lines[i]
            sline = line.strip()
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
                    body.append(inline_body)
                else:
                    i += 1
                    while i < len(lines):
                        next_line = lines[i]
                        if next_line.strip() and not (next_line.startswith(' ') or next_line.startswith('\t')):
                            i -= 1
                            break
                        body.append(next_line)
                        i += 1
                definitions[name] = Definition(name, args_str, body, is_macro)
            else:
                raw_lines.append(line)
            i += 1
        return definitions, raw_lines

    def process_line_expansion(self, line):
        for name, definition in self.active_definitions.items():
            if not definition.is_macro:
                pattern = r'\b' + re.escape(name) + r'\b'
                if re.search(pattern, line):
                    return True, self.expand_body(definition, [], line, name)
        for name, definition in self.active_definitions.items():
            if definition.is_macro:
                pattern = r'\b' + re.escape(name) + r'\s*\('
                match = re.search(pattern, line)
                if match:
                    start_idx = match.end()
                    depth = 1
                    end_idx = -1
                    for k in range(start_idx, len(line)):
                        if line[k] == '(': depth += 1
                        elif line[k] == ')': depth -= 1
                        if depth == 0:
                            end_idx = k
                            break
                    if end_idx != -1:
                        full_match = line[match.start():end_idx+1]
                        args_str = line[start_idx:end_idx]
                        call_args = smart_split_args(args_str)
                        return True, self.expand_body(definition, call_args, line, full_match)
        return False, [line]

    def expand_body(self, definition, call_args, original_line, match_str):
        indent_match = re.match(r'^(\s*)', original_line)
        base_indent = indent_match.group(1) if indent_match else ""
        replacements = {}
        for i, param in enumerate(definition.params):
            val = "None"
            if i < len(call_args): val = call_args[i]
            elif param['default'] is not None: val = param['default']
            replacements[param['name']] = val
        
        is_inline = (len(definition.body_lines) == 1)
        if is_inline:
            body = definition.body_lines[0].strip()
            body = safe_replace(body, replacements)
            # ★修正: インライン展開でも改行を増やさない
            return [original_line.replace(match_str, body)]
        else:
            expanded_lines = []
            for body_line in definition.body_lines:
                temp = safe_replace(body_line, replacements)
                # ★修正: .rstrip('\n') で元の改行を削除してから、新しい改行を付与
                # これにより二重改行を防ぐ
                expanded_lines.append(base_indent + temp.rstrip('\n') + "\n")
            return expanded_lines

    def transpile(self, main_file):
        all_lines = self.expand_files(main_file)
        main_code_lines = self.extract_namespaces(all_lines)
        if 'default' in self.namespaces:
            defs, raw = self.parse_namespace_content(self.namespaces['default'])
            self.active_definitions.update(defs)
            main_code_lines[0:0] = raw

        final_lines = []
        cases_indent_level = 0
        i = 0
        while i < len(main_code_lines):
            line = main_code_lines[i]
            sline = line.strip()

            if sline.startswith('$using'):
                try:
                    target_ns = sline.split()[1]
                    if target_ns in self.namespaces:
                        defs, raw_code = self.parse_namespace_content(self.namespaces[target_ns])
                        self.active_definitions.update(defs)
                        main_code_lines[i+1:i+1] = raw_code
                except: pass
                i += 1
                continue

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
                    body.append(inline_body)
                else:
                    i += 1
                    while i < len(main_code_lines):
                        next_line = main_code_lines[i]
                        if next_line.strip() and not (next_line.startswith(' ') or next_line.startswith('\t')):
                            i -= 1
                            break
                        body.append(next_line)
                        i += 1
                self.active_definitions[name] = Definition(name, args_str, body, is_macro)
                i += 1
                continue
            
            expanded, new_lines = self.process_line_expansion(line)
            if expanded:
                main_code_lines[i:i+1] = new_lines
                continue
            
            if sline.startswith('$cases'):
                parts = sline.split(None, 1)
                if len(parts) > 1:
                    count_expr = parts[1].strip()
                    if count_expr == '1':
                        pass
                    else:
                        indent_match = re.match(r'^(\s*)', line)
                        base_indent = indent_match.group(1) if indent_match else ""
                        extra_indent = "    " * cases_indent_level
                        loop_line = f"{base_indent}{extra_indent}for _ in range({count_expr}):\n"
                        final_lines.append(loop_line)
                        cases_indent_level += 1
                i += 1
                continue
            
            if cases_indent_level > 0:
                if line.strip():
                    final_lines.append(("    " * cases_indent_level) + line)
                else:
                    final_lines.append(line)
            else:
                final_lines.append(line)
            i += 1
        
        # ヘッダーは呼び出し元で結合するため、ここではコードのみ返す
        return "".join(final_lines)

# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file', help='Input file')
    parser.add_argument('--run', '-r', action='store_true')
    parser.add_argument('--copy', '-c', action='store_true')
    parser.add_argument('--out', '-o')
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: Main file not found: {args.file}")
        return

    # オリジナルコードの読み込み (エラー時は空文字)
    try:
        with open(args.file, 'r', encoding='utf-8') as f:
            original_code = f.read()
    except:
        original_code = "Could not read original file."

    # トランスパイル実行
    transpiler = PyxTranspiler()
    try:
        py_code_body = transpiler.transpile(args.file)
    except Exception as e:
        print(f"Transpile Error: {e}")
        return

    # 最終整形:
    # 1. HEADER
    # 2. オリジナルコード (コメントブロック)
    # 3. トランスパイル後のコード
    
    original_block = f"'''\n[Original Code]\n{original_code}\n'''\n"
    
    # コード本体の余計な改行を整理 (連続する3つ以上の改行を2つに、末尾の空白削除など)
    py_code_body = re.sub(r'\n{3,}', '\n\n', py_code_body)
    
    final_output = HEADER_TEXT + "\n" + original_block + "\n" + py_code_body

    if args.out:
        with open(args.out, 'w', encoding='utf-8-sig') as f:
            f.write(final_output)
        print(f"Saved to {args.out}")

    if args.copy:
        copy_to_clipboard(final_output)

    if args.run:
        print(">> Executing...")
        print("-" * 20)
        
        file_dir = os.path.dirname(os.path.abspath(args.file))
        if file_dir not in sys.path:
            sys.path.insert(0, file_dir)
            
        exec_globals = {}
        try:
            exec(final_output, exec_globals)
        except Exception as e:
            print(f"Runtime Error: {e}")

if __name__ == '__main__':
    main()