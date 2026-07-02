import ast
import io
import tokenize
from pathlib import Path


def get_python_files():
    """
    Returns all Python files in the repository.
    (Used for testing)
    """
    return [
        str(file)
        for file in Path(".").rglob("*.py")
        if ".github/workflows" not in str(file)
    ]


def find_dbutils_in_comments(source):
    """
    Returns line numbers where dbutils appears in comments.
    """
    lines = []

    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)

        for token in tokens:
            if token.type == tokenize.COMMENT:
                if "dbutils" in token.string:
                    lines.append(token.start[0])

    except tokenize.TokenizeError:
        pass

    return lines


def check_dbutils(tree, source):
    warnings = []

    dbutils_used = any(
        isinstance(node, ast.Name) and node.id == "dbutils"
        for node in ast.walk(tree)
    )

    comment_lines = find_dbutils_in_comments(source)

    if not dbutils_used:

        if comment_lines:
            warnings.append(
                f"dbutils is mentioned only in comments "
                f"(line(s): {', '.join(map(str, comment_lines))})."
            )
        else:
            warnings.append(
                "dbutils is not used in this file."
            )

    return warnings


def check_try_except(tree):
    warnings = []

    for node in ast.walk(tree):

        if isinstance(node, ast.Try):

            for handler in node.handlers:

                raise_found = any(
                    isinstance(child, ast.Raise)
                    for child in ast.walk(handler)
                )

                if not raise_found:

                    warnings.append(
                        f"Line {handler.lineno}: "
                        "Except block should contain a raise statement."
                    )

    return warnings


def validate_file(file_path):

    warnings = []

    with open(file_path, "r", encoding="utf-8") as file:
        source = file.read()

    tree = ast.parse(source)

    warnings.extend(check_dbutils(tree, source))
    warnings.extend(check_try_except(tree))

    return warnings


def main():

    files = get_python_files()

    if not files:
        print("No Python files found.")
        return

    total_warnings = 0

    for file in files:

        print(f"\nChecking: {file}")

        warnings = validate_file(file)

        if warnings:
            for warning in warnings:

                total_warnings += 1

                print(f"::warning file={file}::{warning}")

    print("------------------------------------")

    if total_warnings == 0:
        print("All validations passed.")
    else:
        print(f"Validation completed with {total_warnings} warning(s).")


if __name__ == "__main__":
    main()