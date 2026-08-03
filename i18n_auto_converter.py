#!/usr/bin/env python3
"""
i18n Auto-Converter for comprehensive_bot.py
Extracts hardcoded Arabic strings, generates i18n keys, replaces with self.tr() calls,
and updates all 17 language JSON files.

Usage:
  python i18n_auto_converter.py              # Full run (backup + extract + replace + JSON update)
  python i18n_auto_converter.py --dry-run    # Preview only, no file changes
  python i18n_auto_converter.py --report     # Only generate extraction report
"""

import re
import json
import os
import sys
import io
import ast
import tokenize
import shutil
from datetime import datetime
from collections import OrderedDict

# ─── Configuration ───
BOT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'comprehensive_bot.py')
I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n')
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n_backups')
LANGUAGES = ['ar', 'en', 'de', 'es', 'fa', 'fr', 'hi', 'id', 'it', 'ja', 'ko', 'pt', 'ru', 'th', 'tr', 'ur', 'zh']

# Lines containing these patterns will have their strings skipped
SKIP_LINE_PATTERNS = [
    'ICON_MAP',
    'logger.',
    'logger[',
    'csv.writer',
    'csv.DictWriter',
    'writer.writerow',
    'writer.writeheader',
    'fieldnames',
    'print(',
    'log_admin_action',
    'log_',
    'description=',
    "'description'",
    '"description"',
]

# Token types to ignore when looking for previous significant token
INSIGNIFICANT_TOKENS = frozenset({
    tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT,
    tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING,
    tokenize.ENDMARKER,
})


class I18nAutoConverter:
    def __init__(self, filepath, dry_run=False):
        self.filepath = filepath
        self.dry_run = dry_run
        self.extracted = []
        self.existing_keys = set()
        self.new_keys = OrderedDict()       # key -> arabic_template
        self.text_to_key = {}               # dedup: arabic_text -> key
        self.skipped_count = 0
        self.extracted_count = 0

    # ─── Helpers ───

    @staticmethod
    def is_arabic(text):
        return bool(re.search(r'[\u0600-\u06FF]', text))

    @staticmethod
    def get_string_prefix(s):
        """Extract prefix characters (f, r, b, u) from a string token."""
        prefix = ''
        i = 0
        while i < len(s) and s[i] in 'fFrRbBuU':
            prefix += s[i]
            i += 1
        return prefix

    @staticmethod
    def extract_string_content(token_string):
        """Return (content, is_triple, is_fstring) from a raw token string."""
        raw = token_string
        prefix = I18nAutoConverter.get_string_prefix(raw)
        raw = raw[len(prefix):]
        is_fstring = 'f' in prefix.lower()

        if raw.startswith('"""') and raw.endswith('"""') and len(raw) >= 6:
            return raw[3:-3], True, is_fstring
        if raw.startswith("'''") and raw.endswith("'''") and len(raw) >= 6:
            return raw[3:-3], True, is_fstring
        if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
            return raw[1:-1], False, is_fstring
        if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
            return raw[1:-1], False, is_fstring
        return raw, False, is_fstring

    @staticmethod
    def unescape_string(token_string):
        """Use ast.literal_eval to get the actual string value (for non-f-strings)."""
        try:
            return ast.literal_eval(token_string)
        except (ValueError, SyntaxError):
            content, _, _ = I18nAutoConverter.extract_string_content(token_string)
            return content

    @staticmethod
    def parse_fstring_vars(content):
        """
        Parse f-string content and return (template, vars_list).
        vars_list is a list of (expression_str, safe_kwarg_name) tuples.
        safe_kwarg_name is None for expressions that can't be converted.
        """
        # Protect escaped braces {{ }} by temporarily replacing them
        protected = content.replace('{{', '\x00').replace('}}', '\x01')

        vars_found = []

        def replace_expr(m):
            expr = m.group(1).strip()
            # Skip if it contains nested braces (shouldn't happen after protection)
            if '{' in expr or '}' in expr:
                return m.group(0)

            # Split off conversion (!r, !s) and format spec (:...)
            base_expr = expr.split('!')[0].split(':')[0].strip()
            after = expr[len(base_expr):]  # e.g. "!r" or ":.2f" or ""

            # Case 1: Simple variable — name
            if re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', base_expr):
                vars_found.append((base_expr, base_expr))
                return '{' + base_expr + after + '}'

            # Case 2: self.attr → use attr
            m2 = re.fullmatch(r'self\.([a-zA-Z_][a-zA-Z0-9_]*)', base_expr)
            if m2:
                attr = m2.group(1)
                vars_found.append((base_expr, attr))
                return '{' + attr + after + '}'

            # Case 3: var['key'] or var["key"] → use var_key
            m3 = re.fullmatch(r"([a-zA-Z_][a-zA-Z0-9_]*)\[['\"]([^'\"]+)['\"]\]", base_expr)
            if m3:
                safe = f"{m3.group(1)}_{m3.group(2)}"
                vars_found.append((base_expr, safe))
                return '{' + safe + after + '}'

            # Case 4: var.attr (not self.) → use attr
            m4 = re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*\.([a-zA-Z_][a-zA-Z0-9_]*)', base_expr)
            if m4:
                attr = m4.group(1)
                vars_found.append((base_expr, attr))
                return '{' + attr + after + '}'

            # Case 5: Complex expression — mark as unresolvable
            vars_found.append((base_expr, None))
            return m.group(0)

        template = re.sub(r'\{([^}]+)\}', replace_expr, protected)
        # Restore escaped braces
        template = template.replace('\x00', '{{').replace('\x01', '}}')
        return template, vars_found

    @staticmethod
    def generate_key(counter, arabic_text):
        """Generate a unique i18n key."""
        # Try to extract a short semantic hint from the text
        # Remove emoji and non-word chars
        clean = re.sub(r'[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F\u200d]', '', arabic_text)
        # Take first few Arabic words
        arabic_words = re.findall(r'[\u0600-\u06FF]+', clean)
        if arabic_words:
            # Use first 2 words, transliterated roughly
            hint = '_'.join(arabic_words[:2])
        else:
            hint = f'auto'
        key = f'a{counter:04d}_{hint}'
        return key

    def load_existing_keys(self):
        """Load existing keys from ar.json."""
        ar_path = os.path.join(I18N_DIR, 'ar.json')
        if os.path.exists(ar_path):
            with open(ar_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.existing_keys = set(data.keys())
                return data
        return {}

    def should_skip_line(self, line_text):
        """Check if strings on this line should be skipped (line-level patterns)."""
        stripped = line_text.strip()
        if stripped.startswith('#'):
            return True
        for pattern in SKIP_LINE_PATTERNS:
            if pattern in line_text:
                return True
        return False

    def build_skip_ranges(self, lines):
        """
        Pre-scan the file to identify line ranges inside multi-line data structures
        that should be skipped (ICON_MAP, default data lists, etc.).
        Returns a set of 0-based line indices to skip.
        """
        skip_lines = set()

        # Patterns that start a multi-line data structure we want to skip
        data_start_patterns = [
            r'ICON_MAP\s*=\s*\{',
            r'ICON_MAP\s*=\s*\{',
            r'translations\s*=\s*\{',
            r'settings\s*=\s*\[',
            r'default_methods\s*=\s*\[',
            r'methods_data\s*=\s*\[',
        ]

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check if this line starts a data structure we want to skip
            is_data_start = False
            for pattern in data_start_patterns:
                if re.search(pattern, line):
                    is_data_start = True
                    break

            # Also check for lines like:  'key': 'value',  (dict entries inside ICON_MAP etc.)
            # These are continuation lines of multi-line dicts

            if is_data_start:
                # Track brace/bracket depth to find the end of this data structure
                depth = 0
                started = False
                j = i
                while j < len(lines):
                    for ch in lines[j]:
                        if ch in '{[':
                            depth += 1
                            started = True
                        elif ch in '}]':
                            depth -= 1
                    skip_lines.add(j)
                    if started and depth <= 0:
                        break
                    j += 1
                i = j + 1
                continue

            # Skip lines that look like dict entries: 'arabic': 'value', or "arabic": value,
            # These are likely ICON_MAP entries or similar data
            if re.match(r"\s*['\"][\u0600-\u06FF]+['\"]\s*:", line):
                skip_lines.add(i)

            # Skip lines inside writer.writerow with Arabic (CSV data)
            if 'writer.writerow' in line and self.is_arabic(line):
                skip_lines.add(i)

            # Skip lines that are part of a multi-line writer.writerow or list literal
            # containing Arabic data (lines starting with [ or having ] at end)
            if stripped.startswith('[') and self.is_arabic(stripped):
                skip_lines.add(i)

            i += 1

        return skip_lines

    def is_in_tr_call(self, tokens, idx):
        """Check if the string at token index idx is the first argument of a tr() call."""
        # Walk backwards to find the previous significant token
        prev = None
        prev2 = None
        j = idx - 1
        while j >= 0:
            if tokens[j].type in INSIGNIFICANT_TOKENS:
                j -= 1
                continue
            if tokens[j].type == tokenize.OP:
                if tokens[j].string == '(':
                    # Look at the token before '('
                    k = j - 1
                    while k >= 0 and tokens[k].type in INSIGNIFICANT_TOKENS:
                        k -= 1
                    if k >= 0 and tokens[k].type == tokenize.NAME and tokens[k].string == 'tr':
                        return True
                    # Also check for self.tr(
                    if k >= 0 and tokens[k].type == tokenize.OP and tokens[k].string == '.':
                        k2 = k - 1
                        while k2 >= 0 and tokens[k2].type in INSIGNIFICANT_TOKENS:
                            k2 -= 1
                        if k2 >= 0 and tokens[k2].type == tokenize.NAME and tokens[k2].string in ('tr', 'get_i18n_text'):
                            return True
                    return False
                else:
                    return False
            else:
                return False
        return False

    def is_in_concatenation(self, tokens, idx):
        """
        Check if the string at token index idx is part of implicit string
        concatenation (adjacent string literals without + operator).
        """
        # Check previous significant token
        j = idx - 1
        while j >= 0 and tokens[j].type in INSIGNIFICANT_TOKENS:
            j -= 1
        prev_is_string = j >= 0 and tokens[j].type == tokenize.STRING

        # Check next significant token
        j = idx + 1
        while j < len(tokens) and tokens[j].type in INSIGNIFICANT_TOKENS:
            j += 1
        next_is_string = j < len(tokens) and tokens[j].type == tokenize.STRING

        return prev_is_string or next_is_string

    def is_docstring(self, tokens, idx):
        """Check if the string at token index idx is a docstring."""
        # A docstring is the first statement in a function/class body
        # Walk backwards past insignificant tokens to find the first significant token
        j = idx - 1
        while j >= 0 and tokens[j].type in INSIGNIFICANT_TOKENS:
            j -= 1
        if j < 0:
            return False
        # If the previous significant token is ':' (end of def/class line) or NEWLINE+INDENT
        if tokens[j].type == tokenize.OP and tokens[j].string == ':':
            return True
        # Also check if it's right after a function definition (skip NEWLINE/INDENT)
        if tokens[j].type == tokenize.INDENT:
            k = j - 1
            while k >= 0 and tokens[k].type in INSIGNIFICANT_TOKENS:
                k -= 1
            if k >= 0 and tokens[k].type == tokenize.OP and tokens[k].string == ':':
                return True
        return False

    def find_lang_variable(self, lines, line_idx):
        """Search backwards for a `lang =` assignment in the current method scope."""
        for i in range(line_idx, max(line_idx - 80, -1), -1):
            if i >= len(lines) or i < 0:
                continue
            line = lines[i]
            # Look for lang = ... or lang=...
            if re.search(r'\blang\s*=\s*', line):
                return 'lang'
            # Look for user_lang = ...
            if re.search(r'\buser_lang\s*=\s*', line):
                return 'user_lang'
        return None

    # ─── Main Processing ───

    def process(self):
        """Extract all hardcoded Arabic strings and prepare replacements."""
        print("=" * 60)
        print("  i18n Auto-Converter")
        print("=" * 60)

        print("\n[1/5] Loading existing i18n keys...")
        self.load_existing_keys()
        print(f"  Found {len(self.existing_keys)} existing keys in ar.json")

        print("\n[2/5] Reading source file...")
        with open(self.filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        lines = source.split('\n')
        line_count = len(lines)
        print(f"  File: {os.path.basename(self.filepath)} ({line_count} lines)")

        print("\n[3/5] Tokenizing...")
        tokens = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                tokens.append(tok)
        except tokenize.TokenizeError as e:
            print(f"  WARNING: Tokenize error at line {e.args[1][0] if len(e.args) > 1 else '?'}: {e}")
            print("  Continuing with partial tokenization...")

        # Find all STRING tokens with Arabic
        arabic_string_tokens = []
        for i, tok in enumerate(tokens):
            if tok.type == tokenize.STRING:
                content, _, _ = self.extract_string_content(tok.string)
                if self.is_arabic(content):
                    arabic_string_tokens.append((i, tok))

        print(f"  Found {len(arabic_string_tokens)} Arabic string tokens")

        # Pre-scan to find data structure line ranges to skip
        skip_line_ranges = self.build_skip_ranges(lines)
        print(f"  Skipping {len(skip_line_ranges)} data-structure lines")

        print("\n[4/5] Processing strings...")
        counter = 0
        for tok_idx, tok in arabic_string_tokens:
            line_idx = tok.start[0] - 1  # 0-based
            col = tok.start[1]

            if line_idx >= len(lines):
                self.skipped_count += 1
                continue

            line_text = lines[line_idx]

            # Skip data structure lines (ICON_MAP, CSV data, etc.)
            if line_idx in skip_line_ranges:
                self.skipped_count += 1
                continue

            # Skip rules
            if self.should_skip_line(line_text):
                self.skipped_count += 1
                continue

            # Skip docstrings
            if self.is_docstring(tokens, tok_idx):
                self.skipped_count += 1
                continue

            # Skip strings already in tr() calls
            if self.is_in_tr_call(tokens, tok_idx):
                self.skipped_count += 1
                continue

            # Skip strings in implicit concatenation (would need + operators)
            if self.is_in_concatenation(tokens, tok_idx):
                self.skipped_count += 1
                continue

            # Extract content
            content, is_triple, is_fstring = self.extract_string_content(tok.string)

            # For f-strings, parse variables
            if is_fstring:
                # Process escape sequences by evaluating as a regular string
                # (remove f prefix, use ast.literal_eval, then parse vars)
                try:
                    raw_without_f = tok.string
                    while raw_without_f and raw_without_f[0] in 'fF':
                        raw_without_f = raw_without_f[1:]
                    content = ast.literal_eval(raw_without_f)
                except (ValueError, SyntaxError):
                    pass  # Keep raw content if eval fails
                template, vars_list = self.parse_fstring_vars(content)
            else:
                # Use ast.literal_eval for proper unescaping
                try:
                    template = ast.literal_eval(tok.string)
                except (ValueError, SyntaxError):
                    template = content
                vars_list = []

            # Skip if any f-string variable couldn't be resolved
            has_unresolved = any(v[1] is None for v in vars_list)
            if has_unresolved:
                self.skipped_count += 1
                continue

            # Skip very short strings (likely not user-facing)
            clean_text = re.sub(r'[\U0001F000-\U0001FFFF\u2600-\u27BF\ufe0f\u200d\s\n]', '', template)
            if len(clean_text) < 3:
                self.skipped_count += 1
                continue

            # Dedup: check if we've already seen this exact template
            if template in self.text_to_key:
                key = self.text_to_key[template]
            else:
                counter += 1
                key = self.generate_key(counter, template)
                # Ensure uniqueness against existing keys
                base_key = key
                suffix = 2
                while key in self.existing_keys or key in self.new_keys:
                    key = f'{base_key}_{suffix}'
                    suffix += 1
                self.text_to_key[template] = key
                self.new_keys[key] = template

            # Find lang variable
            lang_var = self.find_lang_variable(lines, line_idx)
            if not lang_var:
                lang_var = "'ar'"

            # Generate replacement (dedup kwargs by safe_name)
            if vars_list:
                seen_names = set()
                kwargs_parts = []
                for expr, safe_name in vars_list:
                    if safe_name not in seen_names:
                        seen_names.add(safe_name)
                        kwargs_parts.append(f'{safe_name}={expr}')
                kwargs_str = ', '.join(kwargs_parts)
                replacement = f"self.tr('{key}', {lang_var}, {kwargs_str})"
            else:
                replacement = f"self.tr('{key}', {lang_var})"

            self.extracted.append({
                'start': tok.start,
                'end': tok.end,
                'original': tok.string,
                'key': key,
                'replacement': replacement,
                'template': template,
                'vars': [(v[0], v[1]) for v in vars_list],
                'line': line_idx + 1,  # 1-based for report
            })
            self.extracted_count += 1

        print(f"  Extracted: {self.extracted_count}")
        print(f"  Skipped:   {self.skipped_count}")
        print(f"  New keys:  {len(self.new_keys)} (after dedup)")

        return self.extracted

    def apply_replacements(self):
        """Apply all replacements to the source file."""
        if self.dry_run:
            print("\n[5/5] DRY RUN — skipping file modifications")
            return

        print(f"\n[5/5] Applying {len(self.extracted)} replacements...")

        with open(self.filepath, 'r', encoding='utf-8') as f:
            source = f.read()

        lines = source.split('\n')

        # Sort by position (reverse order to preserve offsets)
        replacements = sorted(self.extracted, key=lambda x: (x['start'][0], x['start'][1]), reverse=True)

        for rep in replacements:
            start_line, start_col = rep['start']
            end_line, end_col = rep['end']
            # Convert to 0-based
            start_line -= 1
            end_line -= 1

            if start_line == end_line:
                # Single-line replacement
                line = lines[start_line]
                lines[start_line] = line[:start_col] + rep['replacement'] + line[end_col:]
            else:
                # Multi-line: replace from start to end
                first_line = lines[start_line]
                last_line = lines[end_line]
                new_content = first_line[:start_col] + rep['replacement'] + last_line[end_col:]
                # Replace first line and delete the rest
                lines[start_line] = new_content
                del lines[start_line + 1:end_line + 1]

        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"  [OK] Applied {len(replacements)} replacements to {os.path.basename(self.filepath)}")

    def update_json_files(self):
        """Update all 17 language JSON files with new keys."""
        if self.dry_run:
            print("\n     DRY RUN — skipping JSON updates")
            return

        print("\n     Updating JSON files...")

        # Update ar.json (Arabic = original template)
        ar_path = os.path.join(I18N_DIR, 'ar.json')
        with open(ar_path, 'r', encoding='utf-8') as f:
            ar_data = json.load(f)

        added_ar = 0
        for key, template in self.new_keys.items():
            if key not in ar_data:
                ar_data[key] = template
                added_ar += 1

        with open(ar_path, 'w', encoding='utf-8') as f:
            json.dump(ar_data, f, ensure_ascii=False, indent=2)
        print(f"  [OK] ar.json: +{added_ar} keys")

        # For other languages: copy Arabic as placeholder
        # (tr() method falls back to Arabic, so this is safe)
        for lang in LANGUAGES:
            if lang == 'ar':
                continue
            lang_path = os.path.join(I18N_DIR, f'{lang}.json')
            if not os.path.exists(lang_path):
                print(f"  [!] {lang}.json not found, skipping")
                continue
            with open(lang_path, 'r', encoding='utf-8') as f:
                lang_data = json.load(f)
            added = 0
            for key, template in self.new_keys.items():
                if key not in lang_data:
                    lang_data[key] = template  # Arabic placeholder
                    added += 1
            with open(lang_path, 'w', encoding='utf-8') as f:
                json.dump(lang_data, f, ensure_ascii=False, indent=2)
            print(f"  [OK] {lang}.json: +{added} keys (Arabic placeholder)")

    def create_backup(self):
        """Create timestamped backups of the bot file and JSON files."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, timestamp)
        os.makedirs(backup_path, exist_ok=True)

        # Backup bot file
        shutil.copy2(BOT_FILE, os.path.join(backup_path, 'comprehensive_bot.py'))

        # Backup JSON files
        i18n_backup = os.path.join(backup_path, 'i18n')
        os.makedirs(i18n_backup, exist_ok=True)
        for lang in LANGUAGES:
            lang_path = os.path.join(I18N_DIR, f'{lang}.json')
            if os.path.exists(lang_path):
                shutil.copy2(lang_path, os.path.join(i18n_backup, f'{lang}.json'))

        print(f"  [OK] Backed up to {backup_path}")
        return backup_path

    def save_report(self):
        """Save a detailed extraction report."""
        report_path = os.path.join(os.path.dirname(BOT_FILE), 'i18n_extraction_report.json')
        report = []
        for rep in self.extracted:
            report.append({
                'key': rep['key'],
                'line': rep['line'],
                'template': rep['template'],
                'vars': [{'expr': v[0], 'name': v[1]} for v in rep['vars']],
                'replacement': rep['replacement'],
            })
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n  Report saved: {report_path}")

        # Also save a summary of new keys for translation
        keys_path = os.path.join(os.path.dirname(BOT_FILE), 'i18n_new_keys.json')
        with open(keys_path, 'w', encoding='utf-8') as f:
            json.dump(self.new_keys, f, ensure_ascii=False, indent=2)
        print(f"  New keys saved: {keys_path}")


def main():
    dry_run = '--dry-run' in sys.argv
    report_only = '--report' in sys.argv

    converter = I18nAutoConverter(BOT_FILE, dry_run=dry_run)

    # Step 1: Create backup
    if not dry_run and not report_only:
        print("[0/5] Creating backup...")
        converter.create_backup()

    # Step 2-4: Process
    converter.process()

    if report_only:
        converter.save_report()
        return

    # Step 5: Apply replacements
    converter.apply_replacements()

    # Update JSON files
    converter.update_json_files()

    # Save report
    converter.save_report()

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Extracted:  {converter.extracted_count} strings")
    print(f"  Skipped:    {converter.skipped_count} strings")
    print(f"  New keys:   {len(converter.new_keys)} (after dedup)")
    print(f"  Languages:  {len(LANGUAGES)} files updated")
    if dry_run:
        print("\n  [!] DRY RUN -- no files were modified")
    else:
        print("\n  [OK] All done! Review changes and test the bot.")
        print("  Next steps:")
        print("    1. Review i18n_extraction_report.json")
        print("    2. Translate new keys in en.json")
        print("    3. Fix lang='ar' placeholders in methods that have user language")
        print("    4. Test the bot")
    print("=" * 60)


if __name__ == '__main__':
    main()
