import io
import sys
import pytest
from recp.cli.main import main
from recp.utils.config import PackageConfig
from recp.utils.exceptions import RecpError
from recp.utils.parallel import (
    Job,
    ParallelRunner,
    collapse_cr,
    format_duration,
    infer_labels,
    resolve_output_mode
)
from recp.utils.recipe import Recipe
from recp.utils.runs import list_runs, load_run

SWEEP_RECIPE = (
    "recipe:\n"
    "  sweep:\n"
    "    parallel: 2\n"
    "    run:\n"
    "      - cmd: echo -m model --weight W -o out/W\n"
    "        apply: [{fn: replace, args: {W: [1.0, 0.5, 0.25]}}]\n"
)


def run_cli(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["recp", *args])

    try:
        main()

    except SystemExit as e:
        return e.code or 0

    return 0


@pytest.mark.parametrize(
    ("cmds", "labels"),
    [
        (
            ["run --weight 1.0 -o out/a_1.0", "run --weight 0.5 -o out/a_0.5"],
            ["--weight 1.0", "--weight 0.5"]
        ),
        (
            ["ffmpeg a.wav out/a.flac", "ffmpeg b.wav out/b.flac"],
            ["a.wav", "b.wav"]
        ),
        (
            [
                f"train --model {m} --seed {s} -o out/{m}-{s}"
                for m in ("small", "base") for s in (0, 1)
            ],
            [
                "--model small --seed 0", "--model small --seed 1",
                "--model base --seed 0", "--model base --seed 1"
            ]
        ),
        (["echo a", "echo a"], ["", ""]),
        (["echo a"], [""]),
        (["echo a", "echo b; exit 3"], ["", ""]),
    ]
)
def test_infer_labels(cmds, labels):
    assert infer_labels(cmds) == labels


def test_collapse_cr():
    assert collapse_cr("a\r10%\r100%\nb\r\n") == "100%\nb\n"
    assert collapse_cr("\r50%\r") == "50%"


def test_format_duration():
    assert format_duration(None) == "-"
    assert format_duration(65.7) == "01:05"
    assert format_duration(3725) == "1:02:05"


def test_resolve_output_mode():
    assert resolve_output_mode("prefix") == "prefix"
    assert resolve_output_mode("auto", stream=io.StringIO()) == "grouped"


def test_job_feed_progress_bars():
    job = Job(id=1, cmd="cmd")
    assert job.feed("loading\n\r 10%") == [("loading", False)]
    assert job.current_line == "10%"
    assert job.feed("\r 50%\r") == [(" 10%", True)]
    assert job.current_line == "50%"
    assert job.feed("\ndone\n") == [(" 50%", False), ("done", False)]
    assert job.current_line == "done"


def test_parallel_logs_and_status(write_recipe, capfd):
    file = write_recipe(SWEEP_RECIPE)

    assert Recipe(file=file).run() == 0
    out = capfd.readouterr().out
    assert "Logs:" in out

    run = load_run()
    assert run["recipe"] == "recipe"
    assert run["returncode"] == 0
    assert [c["label"] for c in run["commands"]] == [
        "--weight 1.0", "--weight 0.5", "--weight 0.25"
    ]
    assert all(c["status"] == "done" for c in run["commands"])

    with open(run["commands"][1]["log"]) as f:
        assert f.read() == "-m model --weight 0.5 -o out/0.5\n"


def test_parallel_failure_is_logged(write_recipe, monkeypatch, capfd):
    file = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    parallel: 2\n"
        "    run:\n"
        "      - echo first\n"
        "      - echo broken; exit 3\n"
    )

    assert Recipe(file=file).run() == 3
    statuses = [c["status"] for c in load_run()["commands"]]
    assert statuses == ["done", "failed"]
    capfd.readouterr()

    assert run_cli(monkeypatch, "status") == 0
    out = capfd.readouterr().out
    assert "Failed" in out
    assert "echo broken; exit 3" in out

    assert run_cli(monkeypatch, "log", "2") == 0
    out = capfd.readouterr().out
    assert "failed (exit 3)" in out
    assert "broken\n" in out

    assert run_cli(monkeypatch, "follow", "2") == 3
    assert "broken\n" in capfd.readouterr().out

    assert run_cli(monkeypatch, "log", "9") == 1
    assert "not found" in capfd.readouterr().err


def test_ids_continue_across_steps(write_recipe):
    file = write_recipe(
        "recipe:\n"
        "  first:\n"
        "    parallel: 2\n"
        "    run: [echo a, echo b]\n"
        "  middle:\n"
        "    run: echo sequential\n"
        "  second:\n"
        "    parallel: 2\n"
        "    run: [echo c, echo d]\n"
    )

    assert Recipe(file=file).run() == 0
    commands = load_run()["commands"]
    assert [c["id"] for c in commands] == [1, 2, 3, 4]
    assert [c["step"] for c in commands] == [
        "first", "first", "second", "second"
    ]


def test_sequential_steps_are_not_logged(write_recipe):
    file = write_recipe("recipe:\n  step:\n    run: [echo a, echo b]\n")

    assert Recipe(file=file).run() == 0
    assert list_runs() == []

    with pytest.raises(RecpError):
        load_run()


def test_explicit_label(write_recipe):
    file = write_recipe(
        "recipe:\n"
        "  step:\n"
        "    parallel: 2\n"
        "    run:\n"
        "      - cmd: echo W\n"
        "        label: w=W\n"
        "        apply: [{fn: replace, args: {W: [1, 2]}}]\n"
    )

    assert Recipe(file=file).run() == 0
    labels = [c["label"] for c in load_run()["commands"]]
    assert labels == ["w=1", "w=2"]


def test_prefix_output(write_recipe, capfd):
    file = write_recipe(SWEEP_RECIPE)

    assert Recipe(file=file).run(output="prefix") == 0
    out = capfd.readouterr().out
    assert "[1 --weight 1.0 ] -m model --weight 1.0 -o out/1.0\n" in out
    assert "[3 --weight 0.25] done in" in out


def test_board_output():
    stream = io.StringIO()
    jobs = [
        Job(id=1, cmd="echo one", label="one"),
        Job(id=2, cmd="echo two; exit 2", label="two"),
    ]
    runner = ParallelRunner(
        jobs,
        cwd=None,
        env=None,
        num_jobs=2,
        mode="board",
        title="step",
        ignore_errors=True,
        stream=stream
    )

    assert sorted(runner.run()) == [0, 2]
    out = stream.getvalue()
    assert "\033[?25l" in out and out.endswith("\033[?25h")
    assert "#1  one" in out
    assert "one\n" in out
    assert "step  1 done · 0 running · 0 queued · 1 failed" in out
    assert [j.status for j in jobs] == ["done", "failed"]


def test_old_runs_are_pruned(write_recipe):
    file = write_recipe(SWEEP_RECIPE)

    for _ in range(3):
        Recipe(file=file).run(keep_runs=2)

    assert len(list_runs()) == 2


def test_runs_keep_config(monkeypatch, capfd):
    assert run_cli(monkeypatch, "config", "--set", "runs.keep", "5") == 0
    assert PackageConfig(app_name="recp").runs_keep == 5

    assert run_cli(monkeypatch, "config", "--set", "runs.keep", "0") == 1
    assert "positive integer" in capfd.readouterr().err
