import sys
import re
import os
import argparse
import pyperclip

# ---------------------------------------------------------
# Helper: スマートな引数分割 (カッコのネスト対応)
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

# ---------------------------------------------------------
# 定義クラス
# ---------------------------------------------------------
class Definition:
    def __init__(self, name, args_str, body_lines, is_macro):
        self.name = name
        self.is_macro = is_macro
        # 本体のインデントを整理して保存
        self.body_lines = self._dedent_block(body_lines)
        self.params = [] 

        # 引数解析 (初期値対応)
        if is_macro and args_str.strip():
            raw_args = smart_split_args(args_str)
            for raw_arg in raw_args:
                if '=' in raw_arg:
                    parts = raw_arg.split('=', 1)
                    self.params.append({
                        'name': parts[0].strip(),
                        'default': parts[1].strip()
                    })
                else:
                    self.params.append({
                        'name': raw_arg.strip(),
                        'default': None
                    })

    def _dedent_block(self, lines):
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
# トランスパイラ
# ---------------------------------------------------------
class PyxTranspiler:
    def __init__(self):
        self.namespaces = {} 
        self.active_definitions = {} 

    def load_file(self, filepath):
        if not os.path.exists(filepath):
            print(f"Error: File not found: {filepath}")
            sys.exit(1)
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.readlines()

    # $expand の解決
    def expand_files(self, filepath, visited=None):
        if visited is None: visited = set()
        abs_path = os.path.abspath(filepath)
        if abs_path in visited: return []
        visited.add(abs_path)

        raw_lines = self.load_file(filepath)
        expanded_lines = []
        base_dir = os.path.dirname(abs_path)

        for line in raw_lines:
            sline = line.strip()
            if sline.startswith('$expand'):
                try:
                    target_rel = sline.split(None, 1)[1].strip()
                    target_full = os.path.join(base_dir, target_rel)
                    expanded_lines.extend(self.expand_files(target_full, visited))
                except IndexError:
                    pass 
            else:
                expanded_lines.append(line)
        return expanded_lines

    # $namespace ブロックの抽出
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

    # 行リストから定義を抽出
    def parse_definitions_from_lines(self, lines):
        definitions = {}
        i = 0
        while i < len(lines):
            line = lines[i]
            sline = line.strip()
            
            # Regex修正: コロンの後ろ(group 3/2)もキャプチャする
            # !macro Name(Args): Body
            match_macro = re.match(r'^!macro\s+(\w+)\s*\((.*?)\)\s*:\s*(.*)$', sline)
            # !define Name: Body
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
                
                # 1行定義かブロック定義か判定
                if inline_body and inline_body.strip():
                    # 1行定義 (!define _S: input など)
                    body.append(inline_body)
                    # 行カウンタはそのまま（次の行は別のコードとして処理）
                else:
                    # ブロック定義 (次の行から読み込む)
                    i += 1
                    while i < len(lines):
                        next_line = lines[i]
                        # 空行はスキップせず含めるが、インデントが戻ったら終了
                        if next_line.strip() and not (next_line.startswith(' ') or next_line.startswith('\t')):
                            i -= 1
                            break
                        body.append(next_line)
                        i += 1
                
                definitions[name] = Definition(name, args_str, body, is_macro)
            else:
                pass 
            i += 1
        return definitions

    # 行のマクロ適用
    def process_line_expansion(self, line):
        for name, definition in self.active_definitions.items():
            if definition.is_macro:
                # !macro: name(...)
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

            else:
                # !define: name
                pattern = r'\b' + re.escape(name) + r'\b'
                match = re.search(pattern, line)
                if match:
                    return True, self.expand_body(definition, [], line, name)
        
        return False, [line]

    def expand_body(self, definition, call_args, original_line, match_str):
        indent_match = re.match(r'^(\s*)', original_line)
        base_indent = indent_match.group(1) if indent_match else ""
        
        # 引数マッピング
        replacements = {}
        for i, param in enumerate(definition.params):
            p_name = param['name']
            p_default = param['default']
            val = "None"
            
            if i < len(call_args):
                val = call_args[i]
            elif p_default is not None:
                val = p_default
            
            replacements[p_name] = val

        # インライン判定
        is_inline = (len(definition.body_lines) == 1)

        # ★修正ポイント: 単語境界を考慮した置換関数
        def safe_replace(text, mapping):
            for k, v in mapping.items():
                # \bN\b とすることで None の N にはマッチさせない
                pattern = r'\b' + re.escape(k) + r'\b'
                text = re.sub(pattern, v, text)
            return text

        if is_inline:
            body = definition.body_lines[0].strip()
            # body内の変数を置換
            body = safe_replace(body, replacements)
            # 行全体への適用（ここは単純置換でOK、match_strは一意なので）
            return [original_line.replace(match_str, body)]
        else:
            expanded_lines = []
            for body_line in definition.body_lines:
                temp = body_line
                temp = safe_replace(temp, replacements)
                expanded_lines.append(base_indent + temp + "\n")
            return expanded_lines

    def transpile(self, main_file):
        all_lines = self.expand_files(main_file)
        main_code_lines = self.extract_namespaces(all_lines)
        
        if 'default' in self.namespaces:
            defs = self.parse_definitions_from_lines(self.namespaces['default'])
            self.active_definitions.update(defs)

        final_lines = []
        i = 0
        while i < len(main_code_lines):
            line = main_code_lines[i]
            sline = line.strip()
            
            if sline.startswith('$using'):
                try:
                    target_ns = sline.split()[1]
                    if target_ns in self.namespaces:
                        defs = self.parse_definitions_from_lines(self.namespaces[target_ns])
                        self.active_definitions.update(defs)
                except IndexError: pass
                i += 1
                continue
            
            # 行単位で定義チェック (1行定義対応)
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
            else:
                final_lines.append(line)
                i += 1

        return "".join(final_lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file', help='Input file')
    parser.add_argument('--run', '-r', action='store_true')
    parser.add_argument('--copy', '-c', action='store_true')
    parser.add_argument('--out', '-o')
    args = parser.parse_args()

    if not os.path.exists(args.file):
        return

    transpiler = PyxTranspiler()
    try:
        py_code = transpiler.transpile(args.file)
    except Exception as e:
        print(f"Error: {e}")
        return

    py_code = re.sub(r'\n{3,}', '\n\n', py_code)

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(py_code)
        print(f"Saved to {args.out}")

    if args.copy:
        try:
            pyperclip.copy(py_code)
            print(">> Code copied.")
        except: pass

    if args.run:
        print(">> Executing...")
        print("-" * 20)
        exec_globals = {}
        try:
            exec(py_code, exec_globals)
        except Exception as e:
            print(f"Runtime Error: {e}")

if __name__ == '__main__':
    main()