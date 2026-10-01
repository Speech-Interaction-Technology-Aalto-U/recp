import os
import pytest
from datetime import datetime
from recp.utils.recipe import Recipe


def run_recipe(file: str, **kwargs) -> int:
    return Recipe(file=file).run(**kwargs)


def test_run_str_and_scalar_tag(write_recipe, capfd):
    file = write_recipe(
        "recipe:\n"
        "  first:\n"
        "    tag: build\n"
        "    run: echo first\n"
        "  second:\n"
        "    run: [echo second]\n"
    )

    assert run_recipe(file, tag=["build"]) == 0
    out = capfd.readouterr().out
    assert "first\n" in out
    assert "second\n" not in out


def test_env_is_passed_to_commands(write_recipe, capfd):
    file = write_recipe(
        "env:\n"
        "  ROOT: /data\n"
        "  OUT: $ROOT/out\n"
        "  NAME: recipe\n"
        "recipe:\n"
        "  step:\n"
        "    env:\n"
        "      NAME: step\n"
        "    run:\n"
        "      - python -c \"import os; print(os.environ['OUT'], "
        "os.environ['NAME'])\"\n"
        "      - echo 'cost $$5'\n"
    )

    assert run_recipe(file) == 0
    out = capfd.readouterr().out
    assert "/data/out step\n" in out
    assert "cost $5\n" in out


def test_input_constructor(write_recipe, capfd, monkeypatch):
    file = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    env:\n"
        "      A: !input A_VAR\n"
        "      B: !input {name: B_VAR}\n"
        "      C: !input {name: C_VAR, default: c}\n"
        "      D: !input {name: D_VAR}\n"
        "    run: ['echo \"[$A][$B][$C][$D]\"']\n"
    )
    monkeypatch.setenv("D_VAR", "d")

    assert run_recipe(file) == 0
    assert "[][][c][d]\n" in capfd.readouterr().out


def test_required_input(write_recipe):
    file = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    env:\n"
        "      A: !input {name: A_VAR, required: true}\n"
        "    run: [echo]\n"
    )

    with pytest.raises(SystemExit):
        run_recipe(file)


def test_prompt_constructor(write_recipe, capfd, monkeypatch):
    file = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    env:\n"
        "      PET: !prompt {message: Pet, choices: [cat, dog]}\n"
        "      NUM: !prompt {message: Num, choices: [1, 2], default: 2}\n"
        "    run: ['echo \"[$PET][$NUM]\"']\n"
    )
    responses = iter(["  cat  ", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))

    assert run_recipe(file) == 0
    assert "[cat][2]\n" in capfd.readouterr().out


def test_prompt_without_input(write_recipe, monkeypatch):
    def no_input(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_input)
    with_default = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    env:\n"
        "      A: !prompt {message: A, default: a}\n"
        "    run: [echo $A]\n",
        name="with_default.yaml"
    )
    without_default = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    env:\n"
        "      A: !prompt {message: A}\n"
        "    run: [echo $A]\n",
        name="without_default.yaml"
    )

    assert run_recipe(with_default, dry_run=True) == 0

    with pytest.raises(SystemExit):
        run_recipe(without_default, dry_run=True)


def test_constructors(write_recipe, tmp_path, capfd):
    (tmp_path / "items.txt").write_text("one\n\n# comment\n  two  \n")
    file = write_recipe(
        "env:\n"
        "  REV: !shell echo abc\n"
        "  YEAR: !now '%Y'\n"
        "recipe:\n"
        "  step:\n"
        "    run:\n"
        "      - echo $REV $YEAR\n"
        "      - cmd: echo I\n"
        "        apply:\n"
        "          - fn: replace\n"
        "            args: {I: !lines items.txt}\n"
        "      - cmd: echo S\n"
        "        apply:\n"
        "          - fn: replace\n"
        "            args: {S: !split 'x   y'}\n"
    )

    assert run_recipe(file) == 0
    out = capfd.readouterr().out
    assert f"abc {datetime.now().year}\n" in out
    for value in ("one", "two", "x", "y"):
        assert f"\n{value}\n" in out


def test_shell_constructor_error(write_recipe):
    file = write_recipe(
        "env:\n"
        "  REV: !shell exit 2\n"
        "recipe:\n"
        "  step:\n"
        "    run: [echo]\n"
    )

    with pytest.raises(SystemExit):
        Recipe(file=file)


def test_expr_requires_unsafe(write_recipe):
    file = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    env:\n"
        "      A: !expr 1 + 1\n"
        "    run: [echo]\n"
    )

    with pytest.raises(SystemExit):
        Recipe(file=file)

    assert Recipe(file=file, allow_expr=True).run(dry_run=True) == 0


def test_step_selection(write_recipe, capfd):
    file = write_recipe(
        "recipe:\n"
        "  a:\n"
        "    run: [echo step_a]\n"
        "  b:\n"
        "    run: [echo step_b]\n"
        "  c:\n"
        "    run: [echo step_c]\n"
    )

    assert run_recipe(file, from_step="b") == 0
    out = capfd.readouterr().out
    assert "step_a\n" not in out
    assert "step_b\n" in out and "step_c\n" in out

    assert run_recipe(file, step=["a", "c"]) == 0
    out = capfd.readouterr().out
    assert "step_b\n" not in out
    assert "step_a\n" in out and "step_c\n" in out

    with pytest.raises(SystemExit):
        run_recipe(file, from_step="d")


def test_failure_stops_recipe(write_recipe, capfd):
    file = write_recipe(
        "recipe:\n"
        "  a:\n"
        "    run: ['exit 3', echo after]\n"
        "  b:\n"
        "    run: [echo step_b]\n"
    )

    assert run_recipe(file) == 3
    captured = capfd.readouterr()
    assert "after\n" not in captured.out
    assert "step_b\n" not in captured.out
    assert "--from a" in captured.err


def test_ignore_errors(write_recipe, capfd):
    file = write_recipe(
        "recipe:\n"
        "  a:\n"
        "    run: ['exit 3', echo after]\n"
        "  b:\n"
        "    cwd: missing_folder\n"
        "    run: [echo step_b]\n"
        "  c:\n"
        "    run: [echo step_c]\n"
    )

    assert run_recipe(file, ignore_errors=True) == 1
    captured = capfd.readouterr()
    assert "after\n" in captured.out
    assert "step_b\n" not in captured.out
    assert "step_c\n" in captured.out
    assert "'a', 'b'" in captured.err


def test_skip_if_exists(write_recipe, tmp_path, capfd):
    for name in ("a", "b"):
        (tmp_path / f"{name}.wav").touch()

    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "a.flac").touch()
    file = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    run:\n"
        "      - cmd: echo converting STEM\n"
        "        skip_if_exists: out/STEM.flac\n"
        "        apply:\n"
        "          - fn: dir_files\n"
        "            args: {token: F, dir: ., ext: wav, stem_token: STEM}\n"
    )

    assert run_recipe(file) == 0
    out = capfd.readouterr().out
    assert "\nconverting a\n" not in out
    assert "\nconverting b\n" in out
    assert "Skipped:" in out


def test_parallel(write_recipe, capfd):
    file = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    parallel: 4\n"
        "    run:\n"
        "      - cmd: echo start N; echo end N\n"
        "        apply: [{fn: replace, args: {N: [1, 2, 3, 4, 5]}}]\n"
    )

    assert run_recipe(file) == 0
    out = capfd.readouterr().out

    # Outputs of each command are not mixed
    for n in range(1, 6):
        assert f"start {n}\nend {n}\n" in out


def test_parallel_failure(write_recipe, capfd):
    file = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    parallel: 2\n"
        "    run:\n"
        "      - 'exit 4'\n"
        "      - cmd: sleep 0.2; echo late N\n"
        "        apply: [{fn: replace, args: {N: [1, 2, 3, 4]}}]\n"
    )

    assert run_recipe(file) == 4
    assert run_recipe(file, jobs=1) == 4
    assert "late 4" not in capfd.readouterr().out


@pytest.mark.parametrize(
    "content",
    [
        "",
        "recipe:\n",
        "recipe:\n  step: 5\n",
        "recipe:\n  step:\n    run: [{nocmd: 1}]\n",
        "recipe:\n  step:\n    parallel: 0\n    run: [echo]\n",
        "recipe:\n  step:\n    run: [{cmd: echo, apply: [{fn: nope}]}]\n",
        "recipe: [\n",
    ]
)
def test_invalid_recipes(write_recipe, content):
    file = write_recipe(content)

    with pytest.raises(SystemExit):
        Recipe(file=file).run(dry_run=True)


def test_show_does_not_run_anything(write_recipe, tmp_path, capfd):
    file = write_recipe(
        "env:\n"
        "  REV: !shell touch shell_ran\n"
        "recipe:\n"
        "  step:\n"
        "    env:\n"
        "      A: !input {name: A_VAR, required: true}\n"
        "      B: !expr 1 + 1\n"
        "    run: [echo]\n"
    )

    Recipe(file=file, preview=True).show()
    out = capfd.readouterr().out
    assert not os.path.exists(tmp_path / "shell_ran")
    assert "A (input: A_VAR, required), B" in out
