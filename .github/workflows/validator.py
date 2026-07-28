import ast
import io
import sys
import tokenize
import os
import json
import re
# --------------------------------------------------------
# Secret Detection
# --------------------------------------------------------

SECRET_PATTERNS = [
    (
        "Databricks Personal Access Token",
        re.compile(r"dapi[a-zA-Z0-9]{32,}"),
    ),
    (
        "GitHub Personal Access Token",
        re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    ),
    (
        "GitHub Fine-grained PAT",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82,}\b"),
    ),
    (
        "AWS Access Key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
]
def _clean_cell_source(source_lines):
    """
    Notebook code-cell source is converting into parseable Python:
      - Cell magic (%%sql, %%md, %%bash ...) SQL/markdown ==> blank.
      - Line magic (%foo) / shell (!foo) ==> comment & will 'pass'.
    Line count same -> reported line numbers will be exact.
    """
    for raw in source_lines:
        if raw.strip():
            if raw.lstrip().startswith("%%"):
                return ["\n"] * len(source_lines)   # whole cell = SQL/markdown
            break

    cleaned = []
    for raw in source_lines:
        stripped = raw.lstrip()
        if stripped.startswith("%") or stripped.startswith("!"):
            indent = raw[: len(raw) - len(stripped)]
            cleaned.append(indent + "pass  # notebook-magic\n")
        else:
            cleaned.append(raw)
    return cleaned


def extract_code_from_ipynb(file_path):
    """Reads a Jupyter Notebook (.ipynb) and extracts Python from code cells."""
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            notebook = json.load(f)
        except json.JSONDecodeError:
            return ""

    code_lines = []
    for cell in notebook.get('cells', []):
        if cell.get('cell_type') != 'code':
            continue
        source = cell.get('source', [])
        if isinstance(source, str):
            source = source.splitlines(keepends=True)
        code_lines.extend(_clean_cell_source(source))
        code_lines.append("\n")
    return "".join(code_lines)


def find_utility_in_comments(source):
    lines = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT and "utility." in token.string:
                lines.append(token.start[0])
    except (tokenize.TokenizeError, IndentationError):
        pass
    return lines

def check_utility(tree, source):
    errors = []
    warnings = []
    import_found = False
    utility_used = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "databricks" or module.startswith("databricks."):
                for alias in node.names:
                    imported_name = alias.asname or alias.name
                    if alias.name == "utility" or imported_name == "utility":
                        import_found = True

        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_name = alias.asname or alias.name
                if alias.name == "databricks.utility" or imported_name == "utility":
                    import_found = True

        if isinstance(node, ast.Name) and node.id == "utility":
            utility_used = True
        elif isinstance(node, ast.Attribute) and node.attr == "utility":
            utility_used = True

    comment_lines = find_utility_in_comments(source)

    if not import_found:
        errors.append("Missing import: 'from databricks import utility' is not found.")

    if not utility_used:
        if comment_lines:
            errors.append(
                f"'utility.' is used only inside comments "
                f"(line(s): {', '.join(map(str, comment_lines))}), not in real code."
            )
        else:
            errors.append("'utility' methods are not used in this file.")

    return errors, warnings


def check_try_except(tree):
    errors = []
    warnings = []
    try_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Try)]

    if not try_nodes:
        errors.append("No try-except block found in this file.")
        return errors, warnings

    for node in try_nodes:
        if not node.handlers:
            errors.append(f"Line {node.lineno}: Try block does not contain an 'except' block.")
            continue

        for handler in node.handlers:
            raise_found = any(isinstance(child, ast.Raise) for child in ast.walk(handler))
            if not raise_found:
                warnings.append(f"Line {handler.lineno}: Except block does not contain a 'raise' statement.")

    return errors, warnings


def validate_file(file_path):
    errors = []
    warnings = []

    with open(file_path, "r", encoding="utf-8") as file:
        raw_text = file.read()

    # Secret scan runs on the RAW file — catches tokens anywhere:
    # code cells, markdown cells, cell outputs, metadata, or plain .py source.
    errors.extend(check_secrets(raw_text))

    if file_path.endswith('.ipynb'):
        source = extract_code_from_ipynb(file_path)
    else:
        source = raw_text

    if not source.strip():
        return  warnings

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        error.append(f"SyntaxError: {e}. (Check for a missing 'except' block or unclosed brackets).")
        return errors, warnings

    util_errors, util_warnings = check_utility(tree, source)
    errors.extend(util_errors)
    warnings.extend(util_warnings)

    try_errors, try_warnings = check_try_except(tree)
    errors.extend(try_errors)
    warnings.extend(try_warnings)

    return errors, warnings

def check_secrets(source):
    errors = []

    for secret_name, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(source):
            errors.append(
                f"Potential {secret_name} detected: {match.group(0)}"
            )

    return errors
def main():
    print("===== Custom PR Validator Running =====")

    passed_files = sys.argv[1:]

    files = [
        f for f in passed_files
        if (f.endswith('.py') or f.endswith('.ipynb')) and os.path.exists(f) and ".github/workflows" not in f
    ]

    if not files:
        print("No valid Python or Notebook files to check in this PR.")
        sys.exit(0)

    total_errors = 0
    total_warnings = 0

    for file in files:
        print(f"\nChecking: {file}")
        errors, warnings = validate_file(file)

        for warning in warnings:
            total_warnings += 1
            print(f"::warning file={file}::{warning}")

        for error in errors:
            total_errors += 1
            print(f"::error file={file}::{error}")

    print("\n---------------------------------------")
    print(f"Total Errors: {total_errors}, Total Warnings: {total_warnings}")

    if total_errors == 0:
        print("All mandatory validations passed.")
        sys.exit(0)
    else:
        print(f"Validation failed with {total_errors} error(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()