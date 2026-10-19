"""cli.py: the review page's documents without the GUI."""

import subprocess
import sys

from helpers import CLI


def run_cli(*args, tmp_path):
    return subprocess.run([sys.executable, '-X', 'utf8', str(CLI), *args, '--conf-dir', str(tmp_path / 'conf'),
                           '--no-ru-annotations', '-o', str(tmp_path / 'out')],
                          capture_output=True, text=True, encoding='utf-8')


def test_lpwgs_mode_writes_one_standard_and_two_10x(trio_db, tmp_path):
    result = run_cli(trio_db, '-m', 'lpwgs', '-t', 'sample2', tmp_path=tmp_path)
    assert result.returncode == 0, result.stderr
    names = sorted(p.name for p in (tmp_path / 'out').iterdir())
    assert names == ['Заключение (sample2).docx', 'Заключение LPWGS (sample1).docx', 'Заключение LPWGS (sample3).docx']


def test_unknown_sample_and_template_fail_clearly(trio_db, tmp_path):
    assert 'not found' in run_cli(trio_db, '-t', 'nope', tmp_path=tmp_path).stderr
    assert 'Неизвестный шаблон' in run_cli(trio_db, '--template', 'XYZ', tmp_path=tmp_path).stderr
