import os
import sys
from typing import TextIO


def get_text_color_tags() -> dict:
    return {
        "<error>": "\033[91m",
        "</error>": "\033[0m",
        "<warning>": "\033[93m",
        "</warning>": "\033[0m",
        "<green>": "\033[92m",
        "</green>": "\033[0m",
        "<cyan>": "\033[96m",
        "</cyan>": "\033[0m",
        "<magenta>": "\033[35m",
        "</magenta>": "\033[0m",
    }


def get_text_decorator_tags() -> dict:
    return {
        "<b>": "\033[1m",
        "</b>": "\033[0m",
        "<dim>": "\033[2m",
        "</dim>": "\033[0m",
        "<i>": "\033[3m",
        "</i>": "\033[0m",
        "<u>": "\033[4m",
        "</u>": "\033[0m"
    }


def supports_color(stream: TextIO = sys.stdout) -> bool:
    """Checks if colors should be used when printing to a stream. Colors are
    disabled if the `NO_COLOR` environment variable is set or if the stream is
    not a terminal, unless the `FORCE_COLOR` environment variable is set.

    Args:
        stream (TextIO): Output stream.

    Returns:
        bool: `True` if colors should be used.
    """
    if os.environ.get("NO_COLOR"):
        return False
    
    if os.environ.get("FORCE_COLOR"):
        return True
    
    return hasattr(stream, "isatty") and stream.isatty()


def _decorate_str(message: str, stream: TextIO = sys.stdout) -> str:
    """Replaces colors and decorators in a string. If colors are not
    supported, tags are removed instead.

    Args:
        message (str): The input string to be decorated.
        stream (TextIO): Output stream where the string will be printed.

    Returns:
        str: The decorated string.
    """
    use_color = supports_color(stream)

    # Replace colors and decorators
    for k, v in get_text_decorator_tags().items():
        message = message.replace(k, v if use_color else "")

    for k, v in get_text_color_tags().items():
        message = message.replace(k, v if use_color else "")

    return message


def style(text: str, *tags: str, stream: TextIO = sys.stdout) -> str:
    """Applies colors and decorators to a string. Unlike `printc`, tags inside
    `text` are not replaced, so it is safe to use with user-defined text.

    Args:
        text (str): The input string to be decorated.
        *tags (str): Tag names without brackets (e.g. `b`, `green`).
        stream (TextIO): Output stream where the string will be printed.

    Returns:
        str: The decorated string.
    """
    if not supports_color(stream) or len(tags) == 0:
        return text

    all_tags = {**get_text_decorator_tags(), **get_text_color_tags()}
    prefix = "".join(all_tags[f"<{tag}>"] for tag in tags)
    return f"{prefix}{text}\033[0m"


def printc(message: str, stream: TextIO = sys.stdout) -> None:
    """Prints a formatted string.

    Args:
        message (str): The string to print.
        stream (TextIO): Output stream.
    """
    return print(_decorate_str(message, stream=stream), file=stream)


def printc_exit(message: str, code: int = 0) -> None:
    """Prints a formatted string and exits the program with a specified exit
    code.

    Args:
        message (str): The string to print.
        code (int): Exit code.
    """
    printc(message=message)
    sys.exit(code)


def print_error(message: str, indent: str = "") -> None:
    """Prints an error.
    
    Args:
        message (str): Error message print.
        indent (str): Indentation printed before the error.
    """
    prefix = style("error", "b", "error", stream=sys.stderr)
    sys.stdout.flush()
    print(f"{indent}{prefix}: {message}", file=sys.stderr)


def print_warning(message: str, indent: str = "") -> None:
    """Prints a warning.
    
    Args:
        message (str): Warning message to print.
        indent (str): Indentation printed before the warning.
    """
    prefix = style("warning", "b", "warning", stream=sys.stderr)
    sys.stdout.flush()
    print(f"{indent}{prefix}: {message}", file=sys.stderr)


def print_hint(message: str, indent: str = "") -> None:
    """Prints a hint.
    
    Args:
        message (str): Hint message to print.
        indent (str): Indentation printed before the hint.
    """
    prefix = style("hint", "b", "cyan", stream=sys.stderr)
    sys.stdout.flush()
    print(f"{indent}{prefix}: {message}", file=sys.stderr)


def exit_error(message: str, code: int = 1) -> None:
    """Prints an error and stops the execution of the program.
    
    Args:
        message (str): Error message to print.
        code (int): Exit code.
    """
    print_error(message=message)
    sys.exit(code)


def exit_warning(message: str, code: int = 1) -> None:
    """Prints a warning and stops the execution of the program.

    Args:
        message (str): Warning message to print.
        code (int): Exit code.
    """
    print_warning(message=message)
    sys.exit(code)
