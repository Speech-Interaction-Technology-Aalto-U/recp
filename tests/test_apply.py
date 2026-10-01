import pytest
from recp.utils.apply import (
    apply_cartesian_product,
    apply_dir_files,
    apply_index,
    apply_match,
    apply_replace,
    apply_run_if,
    apply_shard
)
from recp.utils.exceptions import (
    LengthError,
    RecipeError
)


def test_cartesian_product():
    cmds = apply_cartesian_product(["echo A B"], A=[1, 2], B=["x", "y"])
    assert cmds == ["echo 1 x", "echo 1 y", "echo 2 x", "echo 2 y"]


def test_cartesian_product_requires_lists():
    with pytest.raises(RecipeError):
        apply_cartesian_product(["echo A"], A=1)


def test_dir_files(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.wav").touch()
    (tmp_path / "sub" / "b.wav").touch()
    (tmp_path / "c.txt").touch()

    cmds = apply_dir_files(
        ["X F", "Y F"],
        token="F",
        dir=str(tmp_path),
        ext="wav"
    )

    assert cmds == [
        f"X {tmp_path}/a.wav",
        f"X {tmp_path}/sub/b.wav",
        f"Y {tmp_path}/a.wav",
        f"Y {tmp_path}/sub/b.wav"
    ]


def test_dir_files_tokens(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.wav").touch()

    cmds = apply_dir_files(
        ["NAME STEM REL RELDIR"],
        token="FILE",
        dir=str(tmp_path),
        name_token="NAME",
        stem_token="STEM",
        rel_token="REL",
        rel_dir_token="RELDIR"
    )

    assert cmds == ["b.wav b sub/b.wav sub"]


def test_dir_files_empty_input():
    assert apply_dir_files([], token="F", dir=".") == []


def test_index():
    assert apply_index(["a I", "b I"], token="I", offset=1, zfill=2) == [
        "a 01",
        "b 02"
    ]


def test_match():
    cmds = apply_match(
        ["echo T"],
        var="b",
        token="T",
        choices=["a", "b"],
        values=[1, 2]
    )
    assert cmds == ["echo 2"]


def test_match_not_found():
    with pytest.raises(RecipeError):
        apply_match(["T"], var="c", token="T", choices=["a"], values=[1])


def test_replace_single_values():
    assert apply_replace(["echo N M"], N=5, M="x") == ["echo 5 x"]


def test_replace_lists():
    cmds = apply_replace(["echo N M"], N=[1, 2], M=["a", "b"])
    assert cmds == ["echo 1 a", "echo 2 b"]


def test_replace_errors():
    with pytest.raises(LengthError):
        apply_replace(["N M"], N=[1, 2], M=["a"])

    with pytest.raises(RecipeError):
        apply_replace(["N M"], N=[1, 2], M="a")


def test_run_if():
    assert apply_run_if(["echo"], var="a", value="a") == ["echo"]
    assert apply_run_if(["echo"], var="a", value=["b", "c"]) == []


def test_shard():
    cmds = [str(i) for i in range(7)]
    shards = [apply_shard(cmds, index=i, num=3) for i in range(3)]

    assert shards == [["0", "3", "6"], ["1", "4"], ["2", "5"]]
    assert apply_shard(cmds, index="1", num="3") == ["1", "4"]


def test_shard_errors():
    with pytest.raises(RecipeError):
        apply_shard(["a"], index="$SLURM_ARRAY_TASK_ID", num=3)

    with pytest.raises(RecipeError):
        apply_shard(["a"], index=3, num=3)
