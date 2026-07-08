import os
import random
from functools import reduce
from itertools import product
from datetime import datetime
from typing import List
from .io import get_dir_files
from .exceptions import LenghtError


def apply_basename(
        cmd_list: List[str],
        token: str,
        path: str
) -> List[str]:
    """Replaces a given token by the parent path of a given path.

    Args:
        cmd_list (List[str]): Input commands.
        token (str): The token within the command strings to be replaced.
        path (str): File system path from which the basename will be extracted.
    
    Returns:
        List[str]: List of modified commands.
    """
    for cmd_idx, cmd in enumerate(cmd_list):
        cmd_list[cmd_idx] = cmd.replace(token, os.path.basename(path))
    
    return cmd_list


def apply_cartesian_product(cmd_list: List[str], **kwargs) -> List[str]:
    # Combine values
    keys = kwargs.keys()
    values = kwargs.values()
    prod = [dict(zip(keys, combo)) for combo in product(*values)]

    # Generatecommands
    cmd_list_expanded = []

    for cmd in cmd_list:
        for instance_idx in range(len(prod)):
            expanded_cmd = cmd

            for token, values in kwargs.items():
                expanded_cmd =\
                    expanded_cmd.replace(token, str(values[instance_idx]))
            
            cmd_list_expanded.append(expanded_cmd)
    
    return cmd_list_expanded


def apply_date(
        cmd_list: List[str],
        token: str,
        format: str = "%Y-%m-%d"
) -> List[str]:
    """Replaces a given token by a date.

    Args:
        cmd_list (List[str]): Input commands.
        token (str): The token within the command strings to be replaced.
        format (str): Date format to use.
    
    Returns:
        List[str]: List of modified commands.
    """
    for cmd_idx, cmd in enumerate(cmd_list):
        cmd_list[cmd_idx] = cmd.replace(token, datetime.now().strftime(format))
    
    return cmd_list


def apply_dir_files(
        cmd_list: List[str],
        token: str,
        dir: str,
        ext: str | List[str] = "*",
        recursive: bool = True
) -> List[str]:
    """Replaces a given token by the path to each file in a foleder.

    Args:
        cmd_list (List[str]): Input commands.
        token (str): The token within the command strings to be replaced.
        dir (str): Path to the folder to be searched.
        ext (str | List[str]): The file extension(s) used to filter files. Only
            files matching these extension(s) will be considered.
        recursive (bool): If `True`, the search is done recursively. 
    
    Returns:
        List[str]: List of modified commands.
    """
    for cmd in cmd_list:
        files = get_dir_files(dir=dir, ext=ext, recursive=recursive)
        cmd_expanded_list = []

        for file in files:
            cmd_expanded_list.append(cmd.replace(token, file))
 
    return cmd_expanded_list


def apply_index(
        cmd_list: List[str],
        token: str,
        offset: int = 0,
        zfill: int = 0
) -> List[str]:
    """Replaces a given token by the command index value.
    
    Args:
        cmd_list (List[str]): Input commands.
        token (str): Token to be replaced.
        offset (int): Offset applied to all values.
        zfill (int | None): Minimum width of the number, padded with leading
            zeros if needed.
    
    Returns:
        List[str]: List of modified commands.
    """
    for cmd_idx, cmd in enumerate(cmd_list):
        cmd_list[cmd_idx] = cmd.replace(
            token,
            str(cmd_idx + offset).zfill(zfill)
        )
    
    return cmd_list


def apply_parent_dir(
        cmd_list: List[str],
        token: str,
        path: str,
        n: int = 1
) -> List[str]:
    """Replaces a given token by the parent path of a given path.

    Args:
        cmd_list (List[str]): Input commands.
        token (str): The token within the command strings to be replaced.
        path (str): The file system path from which the parent directory will
            be extracted.
        n (int): Number of times to apply the function recursively.
    
    Returns:
        List[str]: List of modified commands.
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
        cmd_list: List[str],
        token: str,
        choices: List[str],
        seed: int | None = None
) -> List[str]:
    """Replace a token by a random choice from a list of choices.
    
    Args:
        cmd_list (List[str]): Input commands.
        token (str): Token to be replaced.
        choices (List[str]): List of choices.
        seed (int | None): Random seed.
    """
    generator = random.Random(seed)

    for cmd_idx, cmd in enumerate(cmd_list):
        value = generator.choice(choices)
        cmd_list[cmd_idx] = cmd.replace(token, str(value))
    
    return cmd_list


def apply_randint(
        cmd_list: List[str],
        token: str,
        min: int,
        max: int,
        seed: int | None = None
) -> List[str]:
    """Replace a token by a random integer number within a range, including
    both `min` and `max` within this range.
    
    Args:
        cmd_list (List[str]): Input commands.
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
        cmd_list: List[str],
        token: str,
        min: float,
        max: float,
        seed: int | None = None
) -> List[str]:
    """Replace a token by a random floating-point number within the
    `[min, max)` range.
    
    Args:
        cmd_list (List[str]): Input commands.
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


def apply_replace(cmd_list: List[str], **kwargs) -> List[str]:
    """Replace placeholders by specified values.
    
    Args:
        cmd_list (List[str]): Input commands.
        **kwargs: Each subsequent argument corresponds to the value to be
            replaced, and the value is the updated value it will take.
    
    Returns:
        List[str]: List of modified commands.
    """
    # Each value is a list (multiple replacements)
    if all(isinstance(v, list) for v in kwargs.values()):
        # Check all keys have the same length
        if len({len(v) for v in kwargs.values()}) != 1:
            raise ValueError("All values should have the same number of items")
        
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
    
    # Each value is a single value (single replacement)
    else:
        for cmd_idx, cmd in enumerate(cmd_list):
            for k, v in kwargs.items():
                cmd = cmd.replace(k, v)
            
            cmd_list[cmd_idx] = cmd

        return cmd_list


def apply_repeat(cmd_list: List[str], n: int) -> List[str]:
    """Repeat a command or command list `n` times.
    
    Args:
        cmd_list (List[str]): Input commands.
        n (int): Number of repetitions.
    
    Returns:
        List[str]: List of modified commands.
    """
    return cmd_list * n


def apply_match(
        cmd_list: List[str],
        var: str,
        token: str,
        choices: List[str],
        values: List[str],
) -> List[str]:
    """Matches a variable value against multiple choices and replaces a token
    in the command based on the matching value.

    Args:
        cmd_list (List[str]): Input commands.
        var (str): Variable to match.
        token (str): Token to replace.
        choices (List[str]): Possible values for `var`.
        values (List[str]): Values used to replace `token` based on the
            matching value from `choices`.

    Returns:
        List[str]: List of modified commands.
    """
    # Assertions
    if len(choices) != len(values):
        raise LenghtError(
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

    for cmd_idx, cmd in enumerate(cmd_list):
        value_idx = choices.index(var)
        cmd_list[cmd_idx] = cmd.replace(token, str(values[value_idx]))
    
    return cmd_list


def apply_run_if(
        cmd_list: List[str],
        var: str,
        value: str | List[str]
) -> List[str]:
    """Conditionally run commands based on a variable's value.

    Args:
        cmd_list (List[str]): Input commands.
        var (str): Variable to compare.
        value (str | List[str]): Value(s) required to proceed.
    
    Returns:
        List[str]: List of modified commands.
    """
    if isinstance(value, List):
        return cmd_list if var in (str(v) for v in value) else []
    
    else:
        return cmd_list if var == str(value) else []


def get_apply_registy() -> dict:
    """Returns the registry of all functions that can be used withing the `run`
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
    }
