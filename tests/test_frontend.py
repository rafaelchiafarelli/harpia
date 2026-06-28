"""Front-end error-path tests.

The front-end (pre_lex -> lexer -> MessageCreator) is the foundation the rest of
the pipeline rests on, but it was only covered transitively by the golden
snapshots. These feed deliberately broken .harpia inputs and assert the front-end
rejects each with the right Error type (and that a clean file passes).

Each case runs in a fresh process via run_frontend.py because LexicalAnalyzer
accumulates tokens in class-level state. Pure Python -- no C++ toolchain needed,
so these run on the host too.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_frontend.py")

# name -> (file contents, expected "STAGE ERRORTYPE" or "OK")
CASES = {
    "valid": (
        "message m {\nint a;\nint b;\n};\n", "OK"),
    # pre_lex structural checks
    "unbalanced_brace": (
        "message m {\nint a;\n", "PRELEX BRAKETS_COUNT_ERROR"),
    "unbalanced_paren": (
        "message m {\nint a(;\n};\n", "PRELEX PARENTESIS_COUNT_ERROR"),
    "unbalanced_square": (
        "message m {\nint a[1;\n};\n", "PRELEX SQUARE_COUNT_ERROR"),
    "unclosed_comment": (
        "/* unclosed\nmessage m {\nint a;\n};\n", "PRELEX COMMENTS_COUNT_ERROR"),
    "no_trailing_newline": (
        "message m {\nint a;\n};", "PRELEX FILE_DOES_NOT_END_IN_NEW_LINE"),
    "non_ascii": (
        "message m {\nint é a;\n};\n", "PRELEX NON_ASCII_CHAR"),
    "missing_import": (
        'import "nope.harpia";\nmessage m {\nint a;\n};\n',
        "PRELEX IMPORT_INCOMPLETE_ERROR"),
    # lexer
    "lex_mismatch": (
        "message m {\nint @ a;\n};\n", "LEX LEXICAL_ANALYZER_ERROR"),
    # message construction
    "malformed_map": (
        "message m {\nmap<> a;\n};\n", "MSG MALFORMED_MAP"),
    "no_name": (
        "message {\nint a;\n};\n", "MSG NO_NAME_IN_MESSAGE"),
}


def _run(tmp_path, contents):
    src = tmp_path / "case.harpia"
    src.write_text(contents, encoding="utf-8")
    dest = tmp_path / "dest"
    r = subprocess.run(
        [sys.executable, RUNNER, str(src), str(dest)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, "front-end runner crashed:\n" + r.stdout + r.stderr
    results = [ln[len("RESULT "):] for ln in r.stdout.splitlines()
               if ln.startswith("RESULT ")]
    assert len(results) == 1, "expected one RESULT line, got:\n" + r.stdout
    return results[0]


@pytest.mark.parametrize("name", sorted(CASES))
def test_frontend_case(tmp_path, name):
    contents, expected = CASES[name]
    assert _run(tmp_path, contents) == expected
