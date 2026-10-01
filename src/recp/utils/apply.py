import os
import random
from functools import reduce
from itertools import product
from datetime import datetime
from .io import get_dir_files
from .collections import make_list
from .exceptions import (
    LengthError,
    RecipeError
)


def apply_basename(
        cmd_list: list[str],
        token: str,
        path: str
) -> list[str]:
    """Replaces a given token by the basename of a given path.

    Args:
        cmd_list (list[str]): Input commands.
        token (str): The token within the command strings to be replaced.
        path (str): File system path from which the basename will be extracted.
    
    Returns:
        list[str]: List of modified commands.
    """
    for cmd_idx, cmd in enumerate(cmd_list):
        cmd_list[cmd_idx] = cmd.replace(token, os.path.basename(path))
    
    return cmd_list


def apply_cartesian_product(cmd_list: list[str], **kwargs) -> list[str]:
    """Generates one command per combination of the values of all tokens.

    Args:
        cmd_list (list[str]): Input commands.
        **kwargs: Each key is a token to be replaced, and each value is a
            `list` with the values that token can take.

    Returns:
        list[str]: List of modified commands.
    """
    if not all(isinstance(v, list) for v in kwargs.values()):
        raise RecipeError(
            "All values passed to 'cartesian_product' should be lists"
        )

    # Combine values
    keys = kwargs.keys()
    values = kwargs.values()
    prod = [dict(zip(keys, combo, strict=True)) for combo in product(*values)]

    # Generate commands
    cmd_list_expanded = []

    for cmd in cmd_list:
        for combo in prod:
            expanded_cmd = cmd

            for token, value in combo.items():
                expanded_cmd = expanded_cmd.replace(token, str(value))
            
            cmd_list_expanded.append(expanded_cmd)
    
    return cmd_list_expanded


def apply_date(
        cmd_list: list[str],
        token: str,
        format: str = "%Y-%m-%d"
) -> list[str]:
    """Replaces a given token by a date.

    Args:
        cmd_list (list[str]): Input commands.
        token (str): The token within the command strings to be replaced.
        format (str): Date format to use.
    
    Returns:
        list[str]: List of modified commands.
    """
    for cmd_idx, cmd in enumerate(cmd_list):
        cmd_list[cmd_idx] = cmd.replace(token, datetime.now().strftime(format))
    
    return cmd_list


def apply_dir_files(
        cmd_list: list[str],
        token: str,
        dir: str | list[str],
        ext: str | list[str] = "*",
        recursive: bool = True,
        name_token: str | None = None,
        stem_token: str | None = None,
        rel_token: str | None = None,
        rel_dir_token: str | None = None
) -> list[str]:
    """Replaces a given token by the path to each file in a folder.

    Args:
        cmd_list (list[str]): Input commands.
        token (str): The token within the command strings to be replaced.
        dir (str | list[str]): Path to the folder(s) to be searched.
        ext (str | list[str]): The file extension(s) used to filter files. Only
            files matching these extension(s) will be considered.
        recursive (bool): If `True`, the search is done recursively. 
        name_token (str | None): Token replaced by the file name (e.g.
            `file.wav`).
        stem_token (str | None): Token replaced by the file name without its
            extension (e.g. `file`).
        rel_token (str | None): Token replaced by the path of the file
            relative to `dir` (e.g. `sub/file.wav`).
        rel_dir_token (str | None): Token replaced by the folder of the file
            relative to `dir` (e.g. `sub`, or `.` for files directly in
            `dir`).
    
    Returns:
        list[str]: List of modified commands.
    """
    dirs = list(make_list(dir))
    files = get_dir_files(dir=dirs, ext=ext, recursive=recursive)
    cmd_expanded_list = []

    for cmd in cmd_list:
        for file in files:
            # Path relative to the folder the file was found in
            for d in dirs:
                rel = os.path.relpath(file, d)

                if not rel.startswith(os.pardir):
                    break

            name = os.path.basename(file)
            tokens = {
                token: file,
                name_token: name,
                stem_token: os.path.splitext(name)[0],
                rel_token: rel,
                rel_dir_token: os.path.dirname(rel) or "."
            }
            expanded_cmd = cmd

            # Longer tokens first so that tokens containing other tokens
            # (e.g. __REL_DIR__ and __REL__) are replaced correctly
            for k in sorted(filter(None, tokens), key=len, reverse=True):
                expanded_cmd = expanded_cmd.replace(k, tokens[k])
            
            cmd_expanded_list.append(expanded_cmd)
 
    return cmd_expanded_list


def apply_index(
        cmd_list: list[str],
        token: str,
        offset: int = 0,
        zfill: int = 0
) -> list[str]:
    """Replaces a given token by the command index value.
    
    Args:
        cmd_list (list[str]): Input commands.
        token (str): Token to be replaced.
        offset (int): Offset applied to all values.
        zfill (int | None): Minimum width of the number, padded with leading
            zeros if needed.
    
    Returns:
        list[str]: List of modified commands.
    """
    for cmd_idx, cmd in enumerate(cmd_list):
        cmd_list[cmd_idx] = cmd.replace(
            token,
            str(cmd_idx + offset).zfill(zfill)
        )
    
    return cmd_list


def apply_parent_dir(
        cmd_list: list[str],
        token: str,
        path: str,
        n: int = 1
) -> list[str]:
    """Replaces a given token by the parent path of a given path.

    Args:
        cmd_list (list[str]): Input commands.
        token (str): The token within the command strings to be replaced.
        path (str): The file system path from which the parent directory will
            be extracted.
        n (int): Number of times to apply the function recursively.
    
    Returns:
        list[str]: List of modified commands.
    """
    parent = reduce(
        lambda p, _: os.path.dirname(p),
        range(n),
        os.path.normpath(path),
    )

    for cmd_idx, cmd in enumerate(cmd_list):
        cmd_list[cmd_idx] = cmd.replace(token, parent)
        # cmd_list[cmd_idx] = cmd.replace(
        #     token,
        #     os.path.dirname(os.path.normpath(path))
        # )
    
    return cmd_list


def apply_randchoice(
        cmd_list: list[str],
        token: str,
        choices: list[str],
        seed: int | None = None
) -> list[str]:
    """Replace a token by a random choice from a list of choices.
    
    Args:
        cmd_list (list[str]): Input commands.
        token (str): Token to be replaced.
        choices (list[str]): List of choices.
        seed (int | None): Random seed.
    """
    generator = random.Random(seed)

    for cmd_idx, cmd in enumerate(cmd_list):
        value = generator.choice(choices)
        cmd_list[cmd_idx] = cmd.replace(token, str(value))
    
    return cmd_list


def apply_randint(
        cmd_list: list[str],
        token: str,
        min: int,
        max: int,
        seed: int | None = None
) -> list[str]:
    """Replace a token by a random integer number within a range, including
    both `min` and `max` within this range.
    
    Args:
        cmd_list (list[str]): Input commands.
        token (str): Token to be replaced.
        min (int): Minimum `int` value to be generated.
        max (int): Maximum `int` value to be generated.
        seed (int | None): Random seed.
    """
    generator = random.Random(seed)

    for cmd_idx, cmd in enumerate(cmd_list):
        value = generator.randint(min, max)
        cmd_list[cmd_idx] = cmd.replace(token, str(value))
    
    return cmd_list


def apply_randfloat(
        cmd_list: list[str],
        token: str,
        min: float,
        max: float,
        seed: int | None = None
) -> list[str]:
    """Replace a token by a random floating-point number within the
    `[min, max)` range.
    
    Args:
        cmd_list (list[str]): Input commands.
        token (str): Token to be replaced.
        min (float): Minimum `float` value to be generated (inclusive).
        max (float): Maximum `float` value to be generated (exclusive).
        seed (int | None): Random seed.
    """
    generator = random.Random(seed)

    for cmd_idx, cmd in enumerate(cmd_list):
        value = generator.uniform(min, max)
        cmd_list[cmd_idx] = cmd.replace(token, str(value))
    
    return cmd_list


def apply_replace(cmd_list: list[str], **kwargs) -> list[str]:
    """Replace placeholders by specified values.
    
    Args:
        cmd_list (list[str]): Input commands.
        **kwargs: Each subsequent argument corresponds to the value to be
            replaced, and the value is the updated value it will take.
    
    Returns:
        list[str]: List of modified commands.
    """
    # Each value is a list (multiple replacements)
    if all(isinstance(v, list) for v in kwargs.values()):
        # Check all keys have the same length
        if len({len(v) for v in kwargs.values()}) != 1:
            raise LengthError(
                "All values passed to 'replace' should have the same number "
                "of items"
            )
        
        # Number of commands to generate
        num_cmd_instances = len(list(kwargs.values())[0])

        cmd_list_expanded = []

        for cmd in cmd_list:
            for instance_idx in range(num_cmd_instances):
                expanded_cmd = cmd

                for token, values in kwargs.items():
                    expanded_cmd =\
                        expanded_cmd.replace(token, str(values[instance_idx]))
                
                cmd_list_expanded.append(expanded_cmd)
        
        return cmd_list_expanded
    
    # Lists and single values cannot be mixed
    elif any(isinstance(v, list) for v in kwargs.values()):
        raise RecipeError(
            "Values passed to 'replace' should be either all lists or all "
            "single values"
        )

    # Each value is a single value (single replacement)
    else:
        for cmd_idx, cmd in enumerate(cmd_list):
            for k, v in kwargs.items():
                cmd = cmd.replace(k, str(v))
            
            cmd_list[cmd_idx] = cmd

        return cmd_list


def apply_repeat(cmd_list: list[str], n: int) -> list[str]:
    """Repeat a command or command list `n` times.
    
    Args:
        cmd_list (list[str]): Input commands.
        n (int): Number of repetitions.
    
    Returns:
        list[str]: List of modified commands.
    """
    return cmd_list * n


def apply_match(
        cmd_list: list[str],
        var: str,
        token: str,
        choices: list[str],
        values: list[str],
) -> list[str]:
    """Matches a variable value against multiple choices and replaces a token
    in the command based on the matching value.

    Args:
        cmd_list (list[str]): Input commands.
        var (str): Variable to match.
        token (str): Token to replace.
        choices (list[str]): Possible values for `var`.
        values (list[str]): Values used to replace `token` based on the
            matching value from `choices`.

    Returns:
        list[str]: List of modified commands.
    """
    # Assertions
    if len(choices) != len(values):
        raise LengthError(
            "case and value lists must have the same number of elements, but "
            f"case has {len(choices)} elements and value has {len(values)} "
            "elements"
        )
    
    choices = [str(c) for c in choices]
    var = os.path.expanduser(os.path.expandvars(var))

    # FIXME: Values may be repeated in some cases
    # Turn into sets to filter out repeated values
    # choice = list(dict.fromkeys(choices))  # Preserves order
    # value = list(dict.fromkeys(values))

    if var not in choices:
        raise RecipeError(
            f"Value {var!r} passed to 'match' not found in choices "
            f"{choices!r}"
        )

    value_idx = choices.index(var)

    for cmd_idx, cmd in enumerate(cmd_list):
        cmd_list[cmd_idx] = cmd.replace(token, str(values[value_idx]))
    
    return cmd_list


def apply_run_if(
        cmd_list: list[str],
        var: str,
        value: str | list[str]
) -> list[str]:
    """Conditionally run commands based on a variable's value.

    Args:
        cmd_list (list[str]): Input commands.
        var (str): Variable to compare.
        value (str | list[str]): Value(s) required to proceed.
    
    Returns:
        list[str]: List of modified commands.
    """
    if isinstance(value, list):
        return cmd_list if var in (str(v) for v in value) else []
    
    else:
        return cmd_list if var == str(value) else []


def apply_shard(cmd_list: list[str], index: int, num: int) -> list[str]:
    """Keeps only one shard of the commands, so that the commands can be split
    across multiple processes or jobs (e.g. a SLURM array job). Commands are
    assigned to shards in a round-robin fashion.

    Args:
        cmd_list (list[str]): Input commands.
        index (int): Index of the shard to keep, between `0` and `num - 1`.
        num (int): Total number of shards.

    Returns:
        list[str]: List of commands in the selected shard.
    """
    try:
        index = int(index)
        num = int(num)
    
    except ValueError:
        raise RecipeError(
            f"'index' ({index!r}) and 'num' ({num!r}) passed to 'shard' "
            "should be integers"
        ) from None
    
    if num < 1 or not 0 <= index < num:
        raise RecipeError(
            f"'shard' requires num >= 1 and 0 <= index < num, but got "
            f"index={index} and num={num}"
        )
    
    return cmd_list[index::num]


def get_apply_registry() -> dict:
    """Returns the registry of all functions that can be used within the `run`
    key of a recipe `.yaml` file.
    """
    return {
        "basename": apply_basename,
        "cartesian_product": apply_cartesian_product,
        "date": apply_date,
        "dir_files": apply_dir_files,
        "index": apply_index,
        "match": apply_match,
        "parent_dir": apply_parent_dir,
        "randchoice": apply_randchoice,
        "randint": apply_randint,
        "randfloat": apply_randfloat,
        "replace": apply_replace,
        "repeat": apply_repeat,
        "run_if": apply_run_if,
        "shard": apply_shard,
    }
