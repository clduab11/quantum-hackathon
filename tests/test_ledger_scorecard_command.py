"""`--upload-command` parsing must keep Windows backslash paths intact (no upload is ever run here)."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from ledger.scorecard import split_upload_command

WIN_EXE = r"C:\Users\cld-main\AppData\Local\Python\python.exe"
WIN_SCRIPT = r"C:\Program Files\kaggle wrapper\upload.py"


def test_windows_mode_keeps_backslashes_in_unquoted_and_quoted_words():
    assert split_upload_command(f"{WIN_EXE} upload.py --flag", windows=True) == [
        WIN_EXE, "upload.py", "--flag"]
    assert split_upload_command(f'"{WIN_EXE}" "{WIN_SCRIPT}"', windows=True) == [WIN_EXE, WIN_SCRIPT]


def test_windows_mode_keeps_single_quotes_and_backslash_pairs_inside_a_double_quoted_word():
    code = r"open('C:\\Users\\x\\log', 'a')"
    assert split_upload_command(f'"{WIN_EXE}" -c "{code}"', windows=True) == [WIN_EXE, "-c", code]


def test_posix_mode_still_unescapes_like_shlex():
    assert split_upload_command(r"/usr/bin/python3 -c 'print(1)' my\ file", windows=False) == [
        "/usr/bin/python3", "-c", "print(1)", "my file"]


def test_the_default_follows_the_host_platform():
    sample = f'"{sys.executable}" -c "print(1)"'
    assert split_upload_command(sample) == split_upload_command(sample, windows=os.name == "nt")
    assert split_upload_command(sample)[0] == sys.executable


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_command_is_rejected(blank: str):
    with pytest.raises(ValueError, match="empty"):
        split_upload_command(blank)


def test_list2cmdline_round_trips_through_the_host_parser():
    """The shape the CLI test builds: the host's own quoting survives `split_upload_command`."""
    argv = [sys.executable, "-c", "print('a b')"]
    line = subprocess.list2cmdline(argv) if os.name == "nt" else " ".join(
        __import__("shlex").quote(a) for a in argv)
    assert split_upload_command(line) == argv


@pytest.mark.parametrize("words", [
    ["-c", 'print("hello")'],
    ["--output=C:\\two words\\file"],
    ["C:\\dir with spaces\\", ""],
    ['word"quoted', "C:\\path\\"],
    [r'C:\with spaces\a\"b', 'say "hello there"'],
])
def test_windows_quoting_round_trips_embedded_quotes_and_trailing_backslashes(words):
    argv = [WIN_SCRIPT, *words]
    assert split_upload_command(subprocess.list2cmdline(argv), windows=True) == argv


def test_windows_quoting_allows_quoted_segments_inside_a_word():
    assert split_upload_command('python.exe --output="two words"', windows=True) == [
        'python.exe', '--output=two words']


@pytest.mark.parametrize("command", ['python.exe "unfinished', 'python.exe --out="unfinished'])
def test_windows_unbalanced_quoting_is_refused(command):
    with pytest.raises(ValueError, match="quotation"):
        split_upload_command(command, windows=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows subprocess argument semantics")
def test_windows_parsed_command_executes_exact_arguments_without_an_upload():
    import json

    words = ['a"b', "C:\\dir with spaces\\", '', "'literal'"]
    argv = [sys.executable, '-c', 'import json, sys; print(json.dumps(sys.argv[1:]))', *words]
    parsed = split_upload_command(subprocess.list2cmdline(argv))
    proc = subprocess.run(parsed, capture_output=True, text=True, check=True)
    assert json.loads(proc.stdout) == words
