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

MAX_EXPANSION_DEPTH = 2000

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

class SymbolicContext(dict):
    def __missing__(self, key):
        return key

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
        if isinstance(v, list):
            val_str = ", ".join(map(str, v))
        else:
            val_str = str(v)
        pattern = r'\b' + re.escape(k) + r'\b'
        text = re.sub(pattern, val_str, text)
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

def get_indent_length(text):
    return len(text) - len(text.lstrip())

def try_eval_math(text):
    text = text.strip()
    if re.match(r'^[\d\s+\-*/%().]+$', text):
        try:
            return str(eval(text))
        except:
            pass
    return text

def process_macro_ops(text, replacements):
    def sub_len(match):
        var_name = match.group(1)
        if var_name in replacements:
            val = replacements[var_name]
            if isinstance(val, list): return str(len(val))
            return "1"
        return match.group(0)
    text = re.sub(r'!len\(\s*([a-zA-Z_]\w*)\s*\)', sub_len, text)

    def sub_accessor(match):
        var_name = match.group(1)
        content = match.group(2).strip()
        if var_name in replacements:
            val = replacements[var_name]
            if ':' in content:
                if not isinstance(val, list): val = [val]
                parts = content.split(':')
                start_str = parts[0].strip()
                end_str = parts[1].strip() if len(parts) > 1 else ""
                try:
                    start = int(start_str) if start_str else 0
                    end = int(end_str) if end_str else len(val)
                    step = None
                    if len(parts) > 2:
                        step_str = parts[2].strip()
                        if step_str: step = int(step_str)
                    sliced = val[start:end:step]
                    return ", ".join(map(str, sliced))
                except ValueError: pass
            else:
                try:
                    idx = int(content)
                    if isinstance(val, list):
                        if 0 <= idx < len(val): return str(val[idx])
                        elif -len(val) <= idx < 0: return str(val[idx])
                        else: raise ValueError(f"Macro index out of range: {var_name}![{idx}] (len={len(val)})")
                    else:
                        if idx == 0: return str(val)
                        else: raise ValueError(f"Cannot use index operator ![] on non-variadic: {var_name}")
                except ValueError as e: raise RuntimeError(str(e))
        return match.group(0)
    text = re.sub(r'([a-zA-Z_]\w*)!\[\s*(.*?)\s*\]', sub_accessor, text)
    return text

def evaluate_condition(expr):
    try:
        return bool(eval(expr, {}, SymbolicContext()))
    except:
        return False

def is_index_safe(text, target_idx):
    in_sq = False; in_dq = False; escape = False
    for i, c in enumerate(text):
        if i == target_idx: return not (in_sq or in_dq)
        if c == '#' and not in_sq and not in_dq: return False
        if escape: escape = False; continue
        if c == '\\': escape = True; continue
        if c == "'" and not in_dq: in_sq = not in_sq
        elif c == '"' and not in_sq: in_dq = not in_dq
    return True

def split_comment(text):
    in_sq = False; in_dq = False; escape = False
    for i, c in enumerate(text):
        if c == '#' and not in_sq and not in_dq:
            return text[:i], text[i:] 
        if escape: escape = False; continue
        if c == '\\': escape = True; continue
        if c == "'" and not in_dq: in_sq = not in_sq
        elif c == '"' and not in_sq: in_dq = not in_dq
    return text, ""

def process_mod_ops(text, mod_value):
    if not mod_value:
        return text
    
    code_part, comment_part = split_comment(text)
    pattern = r'^(\s*)(.+?)\s*%([+\-*/])=\s*(.+)$'
    match = re.match(pattern, code_part)
    
    if match:
        indent = match.group(1)
        lhs = match.group(2).strip()
        op = match.group(3)
        rhs = match.group(4).strip()
        mod_expr = f"({mod_value})"
        
        if op == '/':
            new_code = f"{indent}{lhs}=({lhs}*pow({rhs},{mod_expr}-2,{mod_expr}))%{mod_expr}"
        else:
            new_code = f"{indent}{lhs}=({lhs}{op}({rhs}))%{mod_expr}"
        
        combined = f"{new_code} {comment_part}" if comment_part else new_code
        return combined.rstrip() + "\n"
    
    return text

def detect_recursion(source_lines):
    scope_stack = []
    for sl in source_lines:
        text = sl.content
        stripped = text.strip()
        if not stripped: continue
        if stripped.startswith('#'): continue
        indent = get_indent_length(text)
        while scope_stack and indent <= scope_stack[-1][1]:
            scope_stack.pop()
        match_def = re.match(r'^(async\s+)?def\s+([a-zA-Z_]\w*)', stripped)
        if match_def:
            func_name = match_def.group(2)
            scope_stack.append((func_name, indent))
            continue
        if scope_stack:
            current_func, _ = scope_stack[-1]
            pattern = r'\b' + re.escape(current_func) + r'\s*\('
            matches = list(re.finditer(pattern, text))
            for match in matches:
                if is_index_safe(text, match.start()):
                    return True
    return False

# ---------------------------------------------------------
# Definition Class
# ---------------------------------------------------------
class Definition:
    def __init__(self, name_part, args_str, body_source_lines, is_macro, is_debug=False):
        self.is_macro = is_macro
        self.is_debug = is_debug
        self.body_lines = dedent_block(body_source_lines)
        
        while self.body_lines and not self.body_lines[-1].content.strip():
            self.body_lines.pop()

        self.params = [] 
        self.has_variadic = False
        self.variadic_name = None
        
        self.placeholder = None
        self.placeholder_is_variadic = False
        self.placeholder_vars = None
        
        if '.' in name_part:
            parts = name_part.split('.', 1)
            ph = parts[0].strip()
            self.name = parts[1].strip()
            
            if ph.startswith('*'):
                self.placeholder_is_variadic = True
                self.placeholder = ph[1:]
            elif ph.startswith('(') and ph.endswith(')'):
                inner = ph[1:-1]
                self.placeholder_vars = [v.strip() for v in inner.split(',') if v.strip()]
                self.placeholder = ph
            else:
                self.placeholder = ph
        else:
            self.name = name_part

        if is_macro and args_str.strip():
            raw_args = smart_split_args(args_str)
            for raw_arg in raw_args:
                raw_arg = raw_arg.strip()
                if raw_arg.startswith('*'):
                    self.has_variadic = True
                    self.variadic_name = raw_arg[1:].strip()
                    self.params.append({ 'name': self.variadic_name, 'default': None, 'is_variadic': True })
                elif '=' in raw_arg:
                    parts = raw_arg.split('=', 1)
                    self.params.append({ 'name': parts[0].strip(), 'default': parts[1].strip(), 'is_variadic': False })
                else:
                    self.params.append({ 'name': raw_arg, 'default': None, 'is_variadic': False })

# ---------------------------------------------------------
# Transpiler Logic
# ---------------------------------------------------------
class PyxTranspiler:
    def __init__(self, is_exec_mode=False):
        self.namespaces = {} 
        self.active_definitions = {}
        self.is_exec_mode = is_exec_mode
        self.mod_value = None

    def load_file(self, filepath):
        if not os.path.exists(filepath): return None
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
        if raw_sl_lines is None: return []
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
                if current_ns not in self.namespaces: self.namespaces[current_ns] = []
                self.namespaces[current_ns].extend(buffer)
                current_ns = None
                buffer = []
                continue 
            if sline.startswith('$name'):
                parts = sline.split(None, 2)
                if len(parts) >= 3:
                    ns_name = parts[1].strip()
                    content_str = parts[2].strip()
                    if ns_name not in self.namespaces:
                        self.namespaces[ns_name] = []
                    self.namespaces[ns_name].append(SourceLine(content_str + "\n", sl.filename, sl.lineno))
                continue
            if current_ns: buffer.append(sl)
            else: main_lines.append(sl)
        return main_lines

    def parse_namespace_content(self, source_lines):
        definitions = {} 
        raw_sl_lines = []
        source_lines = dedent_block(source_lines)
        
        i = 0
        while i < len(source_lines):
            sl = source_lines[i]
            sline = sl.content.strip()
            
            match_macro = re.match(r'^(\$debug\s+)?!(macro|method)\s+([*a-zA-Z0-9_.,()]+)\s*\((.*?)\)\s*:\s*(.*)$', sline)
            match_define = re.match(r'^(\$debug\s+)?!define\s+([a-zA-Z0-9_.]+)\s*:\s*(.*)$', sline)
            
            if match_macro or match_define:
                is_macro_keyword = bool(match_macro)
                match = match_macro if is_macro_keyword else match_define
                is_debug = bool(match.group(1))
                if is_macro_keyword:
                    name_part = match.group(3)
                    args_str = match.group(4)
                    inline_body = match.group(5)
                else:
                    name_part = match.group(2)
                    args_str = ""
                    inline_body = match.group(3)
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
                d = Definition(name_part, args_str, body, is_macro_keyword, is_debug)
                if d.name not in definitions:
                    definitions[d.name] = {'normal': None, 'debug': None}
                key = 'debug' if is_debug else 'normal'
                definitions[d.name][key] = d
            else:
                raw_sl_lines.append(sl)
            i += 1
        return definitions, raw_sl_lines

    def get_active_definition(self, name):
        if name not in self.active_definitions: return None
        entry = self.active_definitions[name]
        normal_def = entry['normal']
        debug_def = entry['debug']
        if self.is_exec_mode:
            return debug_def if debug_def else normal_def
        else:
            if normal_def: return normal_def
            elif debug_def:
                dummy = Definition(name, "", [], debug_def.is_macro, False)
                dummy.is_deleted = True 
                return dummy
        return None

    def process_line_expansion(self, sl):
        line_content = sl.content
        for name in self.active_definitions.keys():
            definition = self.get_active_definition(name)
            if not definition: continue

            if not definition.is_macro:
                pattern = r'\b' + re.escape(name) + r'\b'
                matches = list(re.finditer(pattern, line_content))
                for match in matches:
                    if is_index_safe(line_content, match.start()):
                        return True, self.expand_body(definition, [], sl, name)
            else:
                # !method detection
                if definition.placeholder or definition.placeholder_vars or definition.placeholder_is_variadic: 
                    obj_pattern = r'((?:\([^)]*\)|[a-zA-Z0-9_]+(?:\[[^\]]*\])*))'
                    pattern = obj_pattern + re.escape('.') + re.escape(name) + r'\s*\('
                    matches = list(re.finditer(pattern, line_content))
                    for match in matches:
                        if not is_index_safe(line_content, match.start()): continue
                        start_idx = match.end()
                        caller_obj = match.group(1)
                        depth = 1; end_idx = -1; in_quote = False; quote_char = None; escape = False
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
                            if depth == 0: end_idx = k; break
                        if end_idx != -1:
                            full_match = line_content[match.start():end_idx+1]
                            if getattr(definition, 'is_deleted', False):
                                new_content = line_content.replace(full_match, "")
                                if not new_content.strip(): return True, []
                                return True, [SourceLine(new_content, sl.filename, sl.lineno)]
                            args_str = line_content[start_idx:end_idx]
                            raw_call_args = smart_split_args(args_str)
                            call_args = [try_eval_math(a) for a in raw_call_args]
                            return True, self.expand_body(definition, call_args, sl, full_match, caller_obj)
                else:
                    pattern = r'(?<!\.)\b' + re.escape(name) + r'\s*\('
                    matches = list(re.finditer(pattern, line_content))
                    for match in matches:
                        if not is_index_safe(line_content, match.start()): continue
                        start_idx = match.end()
                        depth = 1; end_idx = -1; in_quote = False; quote_char = None; escape = False
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
                            if depth == 0: end_idx = k; break
                        if end_idx != -1:
                            full_match = line_content[match.start():end_idx+1]
                            if getattr(definition, 'is_deleted', False):
                                new_content = line_content.replace(full_match, "")
                                if not new_content.strip(): return True, []
                                return True, [SourceLine(new_content, sl.filename, sl.lineno)]
                            args_str = line_content[start_idx:end_idx]
                            raw_call_args = smart_split_args(args_str)
                            call_args = [try_eval_math(a) for a in raw_call_args]
                            return True, self.expand_body(definition, call_args, sl, full_match)
        return False, [sl]

    def expand_body(self, definition, call_args, original_sl, match_str, caller_obj=None):
        if getattr(definition, 'is_deleted', False):
            new_content = original_sl.content.replace(match_str, "")
            if not new_content.strip(): return []
            return [SourceLine(new_content, original_sl.filename, original_sl.lineno)]

        indent_match = re.match(r'^(\s*)', original_sl.content)
        base_indent = indent_match.group(1) if indent_match else ""
        
        replacements = {}
        if caller_obj:
            if definition.placeholder_is_variadic and definition.placeholder:
                val = caller_obj.strip()
                if val.startswith('(') and val.endswith(')'):
                    val = val[1:-1]
                # ★修正: 括弧の中身をリスト化する ( "A,B,C" -> ["A","B","C"] )
                replacements[definition.placeholder] = smart_split_args(val)
            elif definition.placeholder_vars:
                val = caller_obj.strip()
                if val.startswith('(') and val.endswith(')'):
                    inner_vals = smart_split_args(val[1:-1])
                    for var_name, var_val in zip(definition.placeholder_vars, inner_vals):
                        replacements[var_name] = var_val
            elif definition.placeholder:
                replacements[definition.placeholder] = caller_obj

        used_args_count = 0
        for i, param in enumerate(definition.params):
            p_name = param['name']
            if param.get('is_variadic'):
                variadic_args = []
                if used_args_count < len(call_args):
                    variadic_args = call_args[used_args_count:]
                replacements[p_name] = variadic_args
                break 
            else:
                val = "None"
                if used_args_count < len(call_args):
                    val = call_args[used_args_count]
                    used_args_count += 1
                elif param['default'] is not None:
                    val = param['default']
                replacements[p_name] = val
        
        raw_body_lines = [SourceLine(l.content, l.filename, l.lineno) for l in definition.body_lines]
        processed_lines = self.process_conditionals(raw_body_lines, replacements)

        final_lines = []
        for sl in processed_lines:
            txt = sl.content
            txt = process_macro_ops(txt, replacements)
            txt = safe_replace(txt, replacements)
            final_lines.append(SourceLine(txt, sl.filename, sl.lineno))

        valid_lines = [l for l in final_lines if l.content.strip()]
        is_whole_line = original_sl.content.strip() == match_str
        
        if not is_whole_line and len(valid_lines) == 1:
            body_txt = valid_lines[0].content.strip()
            new_content = original_sl.content.replace(match_str, body_txt)
            return [SourceLine(new_content, original_sl.filename, original_sl.lineno)]
        elif not is_whole_line and len(valid_lines) == 0:
            new_content = original_sl.content.replace(match_str, "")
            if not new_content.strip(): return []
            return [SourceLine(new_content, original_sl.filename, original_sl.lineno)]
        
        if not final_lines: return []

        dedented_lines = dedent_block(final_lines)
        expanded_lines = []
        for body_sl in dedented_lines:
            new_content = base_indent + body_sl.content.rstrip('\n') + "\n"
            expanded_lines.append(SourceLine(new_content, body_sl.filename, body_sl.lineno))
        return expanded_lines

    def process_conditionals(self, source_lines, replacements):
        result = []
        i = 0
        while i < len(source_lines):
            sl = source_lines[i]
            sline = sl.content.strip()
            match_if = re.match(r'^!if\s+(.+?):\s*(.*)$', sline)
            if match_if:
                chain_processed = False
                block_to_append = []
                raw_expr = match_if.group(1).strip()
                inline_code = match_if.group(2).strip()
                expr = process_macro_ops(raw_expr, replacements)
                expr = safe_replace(expr, replacements)
                cond_met = evaluate_condition(expr)
                if inline_code:
                    block = [SourceLine(inline_code + "\n", sl.filename, sl.lineno)]
                    i += 1
                else:
                    block, i = self.extract_block(source_lines, i + 1, get_indent_length(sl.content))
                if cond_met:
                    block_to_append = block
                    chain_processed = True
                
                while i < len(source_lines):
                    next_sl = source_lines[i]
                    next_sline = next_sl.content.strip()
                    match_elif = re.match(r'^!elif\s+(.+?):\s*(.*)$', next_sline)
                    match_else = re.match(r'^!else:\s*(.*)$', next_sline)
                    if match_elif:
                        raw_expr = match_elif.group(1).strip()
                        inline_code = match_elif.group(2).strip()
                        expr = process_macro_ops(raw_expr, replacements)
                        expr = safe_replace(expr, replacements)
                        if inline_code:
                            elif_block = [SourceLine(inline_code + "\n", next_sl.filename, next_sl.lineno)]
                            i += 1
                        else:
                            elif_block, i = self.extract_block(source_lines, i + 1, get_indent_length(next_sl.content))
                        if not chain_processed:
                            if evaluate_condition(expr):
                                block_to_append = elif_block
                                chain_processed = True
                    elif match_else:
                        inline_code = match_else.group(1).strip()
                        if inline_code:
                            else_block = [SourceLine(inline_code + "\n", next_sl.filename, next_sl.lineno)]
                            i += 1
                        else:
                            else_block, i = self.extract_block(source_lines, i + 1, get_indent_length(next_sl.content))
                        if not chain_processed:
                            block_to_append = else_block
                            chain_processed = True
                        break
                    else:
                        break
                result.extend(self.process_conditionals(block_to_append, replacements))
                continue
            result.append(sl)
            i += 1
        return result

    def extract_block(self, source_lines, start_idx, base_indent_len):
        block = []
        i = start_idx
        while i < len(source_lines):
            sl = source_lines[i]
            if not sl.content.strip():
                block.append(sl)
                i += 1
                continue
            curr_indent = get_indent_length(sl.content)
            if curr_indent > base_indent_len:
                block.append(sl)
                i += 1
            else:
                break
        return block, i

    def transpile(self, main_file):
        all_lines = self.expand_files(main_file)
        main_code_lines = self.extract_namespaces(all_lines)
        global_defs, raw_code_lines = self.parse_namespace_content(main_code_lines)
        for name, definitions in global_defs.items():
            if name not in self.active_definitions: self.active_definitions[name] = {'normal': None, 'debug': None}
            if definitions['normal']: self.active_definitions[name]['normal'] = definitions['normal']
            if definitions['debug']: self.active_definitions[name]['debug'] = definitions['debug']
        if 'default' in self.namespaces:
            defs, raw = self.parse_namespace_content(self.namespaces['default'])
            for name, d in defs.items():
                if name not in self.active_definitions: self.active_definitions[name] = {'normal': None, 'debug': None}
                if d['normal']: self.active_definitions[name]['normal'] = d['normal']
                if d['debug']: self.active_definitions[name]['debug'] = d['debug']
            raw_code_lines[0:0] = raw

        final_sl_lines = []
        cases_indent_level = 0
        i = 0
        expansion_counter = 0

        while i < len(raw_code_lines):
            sl = raw_code_lines[i]
            sline = sl.content.strip()

            if sline.startswith('$using'):
                parts = sline.split(None, 1)
                if len(parts) > 1:
                    target_ns_list = [ns.strip() for ns in parts[1].split(',')]
                    all_raw_codes = []
                    for target_ns in target_ns_list:
                        if target_ns in self.namespaces:
                            defs, raw_code = self.parse_namespace_content(self.namespaces[target_ns])
                            for name, d in defs.items():
                                if name not in self.active_definitions: self.active_definitions[name] = {'normal': None, 'debug': None}
                                if d['normal']: self.active_definitions[name]['normal'] = d['normal']
                                if d['debug']: self.active_definitions[name]['debug'] = d['debug']
                            all_raw_codes.extend(raw_code)
                    if all_raw_codes:
                        raw_code_lines[i+1:i+1] = all_raw_codes
                i += 1
                expansion_counter = 0
                continue
            
            if sline.startswith('$mod'):
                parts = sline.split()
                if len(parts) > 1:
                    self.mod_value = parts[1].strip()
                i += 1
                continue

            expanded, new_sl_lines = self.process_line_expansion(sl)
            if expanded:
                expansion_counter += 1
                if expansion_counter > MAX_EXPANSION_DEPTH:
                    raise RuntimeError(f"Infinite macro expansion detected at line {sl.lineno}: {sline}")
                raw_code_lines[i:i+1] = new_sl_lines
                continue
            
            expansion_counter = 0
            
            # ?デバッグ行
            debug_match = re.match(r'^(\s*)\?(.*)$', sl.content)
            if debug_match:
                if not self.is_exec_mode:
                    i += 1
                    continue
                else:
                    new_content = debug_match.group(1) + debug_match.group(2)
                    if not new_content.endswith('\n'): new_content += '\n'
                    sl = SourceLine(new_content, sl.filename, sl.lineno)
                    sline = sl.content.strip()

            if sline.startswith('$cases'):
                parts = sline.split(None, 1)
                if len(parts) > 1:
                    count_expr = parts[1].strip()
                    if count_expr == '1': pass
                    else:
                        indent_match = re.match(r'^(\s*)', sl.content)
                        base_indent = indent_match.group(1) if indent_match else ""
                        extra_indent = "    " * cases_indent_level
                        loop_txt = f"{base_indent}{extra_indent}for _ in range({count_expr}):\n"
                        final_sl_lines.append(SourceLine(loop_txt, sl.filename, sl.lineno))
                        cases_indent_level += 1
                i += 1
                continue
            
            processed_content = process_mod_ops(sl.content, self.mod_value)
            sl_to_add = SourceLine(processed_content, sl.filename, sl.lineno)

            if cases_indent_level > 0:
                if sl_to_add.content.strip():
                    new_content = ("    " * cases_indent_level) + sl_to_add.content
                    final_sl_lines.append(SourceLine(new_content, sl_to_add.filename, sl_to_add.lineno))
                else:
                    final_sl_lines.append(sl_to_add)
            else:
                final_sl_lines.append(sl_to_add)
            i += 1
        
        return final_sl_lines

def generate_output(file_path, is_exec_mode, args):
    transpiler = PyxTranspiler(is_exec_mode=is_exec_mode)
    try:
        final_sl_list = transpiler.transpile(file_path)
    except Exception as e:
        print(f"Transpile Error: {e}")
        return None

    has_recursion = detect_recursion(final_sl_list)

    final_output_lines = []
    line_mapping = {}

    if not args.no_header:
        try:
            header_content = base64.b64decode(args.header_b64).decode('utf-8') if args.header_b64 else DEFAULT_HEADER
        except: header_content = DEFAULT_HEADER
        header_block = f"{args.comment_style}\n{header_content}\n{args.comment_style}\n"
        for line in header_block.splitlines(True): final_output_lines.append(line)

    if not args.no_original:
        try:
            with open(file_path, 'r', encoding='utf-8') as f: original_code = f.read()
        except: original_code = ""
        orig_block = f"{args.comment_style}\n[Original Code]\n{original_code}\n{args.comment_style}\n"
        for line in orig_block.splitlines(True): final_output_lines.append(line)

    if has_recursion:
        final_output_lines.append("import sys\n")
        final_output_lines.append("sys.setrecursionlimit(10 ** 6)\n")

    current_line_idx = len(final_output_lines)
    for sl in final_sl_list:
        final_output_lines.append(sl.content)
        line_mapping[current_line_idx] = sl
        current_line_idx += 1
    
    return "".join(final_output_lines), line_mapping

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

    if args.out or args.copy:
        code_export, _ = generate_output(args.file, is_exec_mode=False, args=args) or (None, None)
        if code_export:
            if args.out:
                with open(args.out, 'w', encoding='utf-8-sig') as f: f.write(code_export)
                print(f"Saved to {args.out}")
            if args.copy and not args.run:
                copy_to_clipboard(code_export)

    if args.run:
        print(">> Executing...")
        print("-" * 20)
        code_exec, line_mapping = generate_output(args.file, is_exec_mode=True, args=args) or (None, None)
        
        if code_exec:
            file_dir = os.path.dirname(os.path.abspath(args.file))
            if file_dir not in sys.path: sys.path.insert(0, file_dir)
            exec_globals = {}
            this_script_path = os.path.abspath(__file__)

            try:
                code_obj = compile(code_exec, "generated_pyx.py", "exec")
                exec(code_obj, exec_globals)
            except SyntaxError as e:
                print("Traceback (most recent call last):")
                if e.filename == "generated_pyx.py" and e.lineno is not None:
                    mapped_idx = e.lineno - 1
                    if mapped_idx in line_mapping:
                        src = line_mapping[mapped_idx]
                        print(f'  File "{src.filename}", line {src.lineno}')
                        print(f'    {src.content.strip()}')
                    else:
                        print(f'  File "Generated Code", line {e.lineno}')
                else:
                    print(f'  File "{e.filename}", line {e.lineno}')
                print(f"{type(e).__name__}: {e.msg}")

            except KeyboardInterrupt:
                print("\n>> Execution Interrupted.")
            except Exception:
                print("-" * 20)
                print("Runtime Error (Mapped to Source):")
                exc_type, exc_value, exc_traceback = sys.exc_info()
                tb_list = traceback.extract_tb(exc_traceback)
                for frame in tb_list:
                    if os.path.abspath(frame.filename) == this_script_path: continue
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
                if args.copy and code_export:
                    print("-" * 20)
                    copy_to_clipboard(code_export)

if __name__ == '__main__':
    main()