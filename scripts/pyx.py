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

MAX_EXPANSION_DEPTH = 1000

# ---------------------------------------------------------
# Data Structures
# ---------------------------------------------------------
class SourceLine:
    def __init__(self, content, filename, lineno):
        self.content = content
        self.filename = filename
        self.lineno = lineno

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
    if not source_lines: return []
    indent_len = 0
    first_valid = next((l for l in source_lines if l.content.strip()), None)
    if first_valid:
        indent_len = len(first_valid.content) - len(first_valid.content.lstrip())

    dedented = []
    for sl in source_lines:
        txt = sl.content
        if not txt.strip():
            dedented.append(SourceLine("\n", sl.filename, sl.lineno))
        else:
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
                    body.append(SourceLine(inline_body + "\n", sl.filename, sl.lineno))
                else:
                    i += 1
                    while i < len(source_lines):
                        next_sl = source_lines[i]
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
        
        for name, definition in self.active_definitions.items():
            if not definition.is_macro:
                pattern = r'\b' + re.escape(name) + r'\b'
                if re.search(pattern, line_content):
                    return True, self.expand_body(definition, [], sl, name)
        
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
            return [SourceLine(new_content, original_sl.filename, original_sl.lineno)]
        else:
            expanded_lines = []
            for body_sl in definition.body_lines:
                temp_txt = safe_replace(body_sl.content, replacements)
                new_content = base_indent + temp_txt.rstrip('\n') + "\n"
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
        expansion_counter = 0

        while i < len(main_code_lines):
            sl = main_code_lines[i]
            sline = sl.content.strip()

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
            
            expanded, new_sl_lines = self.process_line_expansion(sl)
            if expanded:
                expansion_counter += 1
                if expansion_counter > MAX_EXPANSION_DEPTH:
                    raise RuntimeError(f"Infinite macro expansion detected at line {sl.lineno}: {sline}")
                main_code_lines[i:i+1] = new_sl_lines
                continue
            
            expansion_counter = 0
            
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

    if args.header_b64:
        try:
            header_content = base64.b64decode(args.header_b64).decode('utf-8')
        except:
            header_content = DEFAULT_HEADER
    else:
        header_content = DEFAULT_HEADER

    transpiler = PyxTranspiler()
    try:
        final_sl_list = transpiler.transpile(args.file)
    except Exception as e:
        print(f"Transpile Error: {e}")
        return

    final_output_lines = []
    line_mapping = {}

    if not args.no_header:
        header_block = f"{args.comment_style}\n{header_content}\n{args.comment_style}\n"
        for line in header_block.splitlines(True):
            final_output_lines.append(line)

    if not args.no_original:
        orig_block = f"{args.comment_style}\n[Original Code]\n{original_code}\n{args.comment_style}\n"
        for line in orig_block.splitlines(True):
            final_output_lines.append(line)

    current_line_idx = len(final_output_lines)
    for sl in final_sl_list:
        final_output_lines.append(sl.content)
        line_mapping[current_line_idx] = sl
        current_line_idx += 1
    
    final_output = "".join(final_output_lines)

    if args.out:
        with open(args.out, 'w', encoding='utf-8-sig') as f:
            f.write(final_output)
        print(f"Saved to {args.out}")

    if args.run:
        print(">> Executing...")
        print("-" * 20)
        
        file_dir = os.path.dirname(os.path.abspath(args.file))
        if file_dir not in sys.path:
            sys.path.insert(0, file_dir)
            
        exec_globals = {}
        
        # ★ここが重要：トランスパイラ自身のエラーをフィルタリングする準備
        this_script_path = os.path.abspath(__file__)

        try:
            code_obj = compile(final_output, "generated_pyx.py", "exec")
            exec(code_obj, exec_globals)
        except KeyboardInterrupt:
            print("\n>> Execution Interrupted.")
        except Exception:
            # エラー表示ロジック
            print("-" * 20)
            print("Runtime Error (Mapped to Source):")
            
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb_list = traceback.extract_tb(exc_traceback)
            
            for frame in tb_list:
                # ★修正ポイント：pyx.py 自体のフレームは無視する
                if os.path.abspath(frame.filename) == this_script_path:
                    continue

                filename = frame.filename
                lineno = frame.lineno
                funcname = frame.name
                line_text = frame.line
                
                if filename == "generated_pyx.py":
                    mapped_idx = lineno - 1
                    if mapped_idx in line_mapping:
                        src_sl = line_mapping[mapped_idx]
                        print(f'  File "{src_sl.filename}", line {src_sl.lineno}, in {funcname}')
                        print(f'    {src_sl.content.strip()}')
                    else:
                        print(f'  File "Generated Code", line {lineno}, in {funcname}')
                        print(f'    {line_text}')
                else:
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