import os
from contextlib import contextmanager
from typing import Any


def make_list(x: Any) -> list[Any]:
    """If `x` is a single element, turns it into a `list` of one element.

    Args:
        x (Any): Element(s) to be returned as a `list`.

    Returns:
        (list): `x` as a `list`.
    """
    return [x] if not isinstance(x, list) and x is not None else x


@contextmanager
def temp_env(merge: dict | None = None):
    """Temporarily modify the environment variables.

    This context manager allows temporary modification of the
    environment variables for the duration of the context. Once the
    context is exited, the environment variables are restored to their
    original state.

    Args:
        merge (dict): A dictionary of environment variables to be
            temporarily added or updated. The keys are the variable
            names and the values are their corresponding values.
    """
    old_env = os.environ.copy()

    try:
        os.environ.update(
            {
                k: "" if v is None else str(v)
                for k, v in (merge or {}).items()
            }
        )
        yield
    
    finally:
        os.environ.clear()
        os.environ.update(old_env)
