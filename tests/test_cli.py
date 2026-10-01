import sys
import pytest
from recp.cli.main import main


def run_cli(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["recp", *args])

    try:
        main()

    except SystemExit as e:
        return e.code or 0

    return 0


@pytest.fixture
def recipe_file(write_recipe):
    return write_recipe(
        "recipe:\n"
        "  hello:\n"
        "    description: Say hello\n"
        "    run: [echo hello]\n",
        name="hello.yml"
    )


def test_no_args_prints_help(monkeypatch, capsys):
    assert run_cli(monkeypatch) == 0
    assert "usage:" in capsys.readouterr().out


def test_run(monkeypatch, capfd, recipe_file):
    assert run_cli(monkeypatch, "run", recipe_file) == 0
    assert "hello\n" in capfd.readouterr().out


def test_run_missing_file(monkeypatch, capfd):
    assert run_cli(monkeypatch, "run", "missing.yaml") == 1
    assert "error:" in capfd.readouterr().err


def test_saved_recipes(monkeypatch, capfd, recipe_file):
    assert run_cli(monkeypatch, "list") == 0
    assert "No recipes found" in capfd.readouterr().out

    assert run_cli(monkeypatch, "config", "--add", recipe_file) == 0
    assert run_cli(monkeypatch, "list") == 0
    assert "hello" in capfd.readouterr().out

    assert run_cli(monkeypatch, "show", "hello") == 0
    assert "Say hello" in capfd.readouterr().out

    assert run_cli(monkeypatch, "run", "hello") == 0
    assert "hello\n" in capfd.readouterr().out

    assert run_cli(monkeypatch, "show", "missing") == 1
