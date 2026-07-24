import ast
import io
import sys
import tokenize
import os
import re
import subprocess
# --------------------------------------------------------
# Secret Detection
# --------------------------------------------------------

SECRET_PATTERNS = [
    (
        "Databricks Personal Access Token",
        re.compile(r"\bdapi[a-zA-Z0-9]{32,}\b"),
    ),
]
def find_utility_in_comments(source):
    """
    Returns line numbers where 'utility.' appears in comments.
    """
    lines = []

    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)

        for token in tokens:
            if token.type == tokenize.COMMENT and "utility." in token.string:
                lines.append(token.start[0])

    except tokenize.TokenError:
        pass

    return lines


def check_utility(tree, source):
    """
    Checks:
    1. databricks utility import exists
    2. utility methods are used
    """

    warnings = []

    import_found = False
    utility_used = False
    utility_names = {"utility"}

    for node in ast.walk(tree):

        # Check imports
        if isinstance(node, ast.ImportFrom):

            # from databricks import utility
            if node.module == "databricks":

                for alias in node.names:
                    if alias.name == "utility":
                        import_found = True
                        utility_names.add(alias.asname or alias.name)


        elif isinstance(node, ast.Import):

            # import databricks.utility as utility
            for alias in node.names:
                if alias.name == "databricks.utility":
                    import_found = True
                    utility_names.add(alias.asname or "utility")


        # Check usage: utility.xxx()
        elif isinstance(node, ast.Attribute):

            if isinstance(node.value, ast.Name):

                if node.value.id in utility_names:
                    utility_used = True


    comment_lines = find_utility_in_comments(source)


    if not import_found:
        warnings.append(
            "Missing import: databricks utility import not found."
        )


    if not utility_used:

        if comment_lines:
            warnings.append(
                f"'utility.' found only in comments at line(s): "
                f"{', '.join(map(str, comment_lines))}"
            )
        else:
            warnings.append(
                "No databricks utility method usage found."
            )

    return warnings



def check_try_except(tree):
    """
    Checks:
    1. Try exists
    2. Except exists
    3. Except contains raise
    """

    warnings = []

    try_nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Try)
    ]


    if not try_nodes:

        warnings.append(
            "No try-except block found."
        )

        return warnings


    for node in try_nodes:

        if not node.handlers:

            warnings.append(
                f"Line {node.lineno}: Try block has no except."
            )

            continue


        for handler in node.handlers:

            raise_found = any(
                isinstance(child, ast.Raise)
                for child in ast.walk(handler)
            )


            if not raise_found:

                warnings.append(
                    f"Line {handler.lineno}: Except block missing raise statement."
                )


    return warnings

def check_secrets(source):
    """
    Checks for secrets such as Databricks Personal Access Tokens.
    """

    warnings = []

    for secret_name, pattern in SECRET_PATTERNS:

        matches = pattern.finditer(source)

        for match in matches:

            line_number = source.count(
                "\n",
                0,
                match.start()
            ) + 1

            warnings.append(
                f"{secret_name} detected at line {line_number}."
            )

    return warnings

def validate_file(file_path):

    warnings = []


    try:

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            source = file.read()


    except Exception as e:

        warnings.append(
            f"Unable to read file: {e}"
        )

        return warnings



    try:

        tree = ast.parse(source)


    except SyntaxError as e:

        warnings.append(
            f"Syntax error at line {e.lineno}: {e.msg}"
        )

        return warnings



    warnings.extend(
        check_utility(tree, source)
    )

    warnings.extend(
        check_try_except(tree)
    )
    warnings.extend(
        check_secrets(source)
    )

    return warnings

# --------------------------------------------------------
# NEW: Git debug context
# --------------------------------------------------------

def debug_git_context():
    """
    Prints git context so you can see WHY certain files are being
    passed in — e.g. whether the diff is scoped to the latest commit
    only, or to the whole PR history against the base branch.
    """

    print("===== Git Debug Context =====")

    commands = {
        "Current HEAD commit":        ["git", "log", "-1", "--oneline"],
        "Current branch":             ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        "Files changed vs HEAD~1":    ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        "Files changed vs origin/main (full PR diff)":
                                       ["git", "diff", "--name-only", "origin/main...HEAD"],
    }

    for label, cmd in commands.items():
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout.strip() or "(none)"
            print(f"\n{label}:")
            print(output)
        except Exception as e:
            print(f"\n{label}: could not run ({e})")

    print("\n==============================\n")


def main():

    print(
        "===== Custom PR Validator Running ====="
    )


    passed_files = sys.argv[1:]


    print(
        "Received files:",
        passed_files
    )


    files = [

        f for f in passed_files

        if f.endswith(".py")
        and os.path.exists(f)
        and ".github/workflows" not in f

    ]


    print(
        "Python files checked:",
        files
    )


    if not files:

        print(
            "❌ No Python files supplied for validation."
        )

        sys.exit(1)



    total_warnings = 0



    for file in files:

        print(
            f"\nChecking: {file}"
        )


        warnings = validate_file(file)


        for warning in warnings:

            total_warnings += 1

            print(
                f"::error file={file}::{warning}"
            )



    print(
        "\n---------------------------------------"
    )


    if total_warnings > 0:

        print(
            f"❌ Validation failed with {total_warnings} issue(s)."
        )

        sys.exit(1)



    print(
        "✅ All validations passed."
    )

    sys.exit(0)



if __name__ == "__main__":
    main()