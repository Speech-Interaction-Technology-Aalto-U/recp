import os
import sys
import json
import time
import shutil
from datetime import datetime
from typing import Any
from platformdirs import PlatformDirs
from .display import style
from .exceptions import RecpError
from .parallel import collapse_cr, format_duration


def get_runs_dir() -> str:
    """Returns the folder where the logs of parallel commands are stored.

    Returns:
        (str): Folder where each run of a recipe gets its own subfolder.
    """
    platform = PlatformDirs(appname="recp", appauthor="Esteban Gómez")
    return os.path.join(platform.user_state_dir, "runs")


def _write_json(file: str, obj: dict) -> None:
    """Writes a `.json` file atomically, so that readers never see a partially
    written file.

    Args:
        file (str): Output `.json` file.
        obj (dict): Data to write.
    """
    tmp_file = f"{file}.{os.getpid()}.tmp"

    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)

    os.replace(tmp_file, file)


def _read_json(file: str) -> dict | None:
    """Reads a `.json` file.

    Args:
        file (str): Input `.json` file.

    Returns:
        (dict | None): File data, or `None` if it does not exist or is not
            valid.
    """
    try:
        with open(file, encoding="utf-8") as f:
            return json.load(f)

    except (OSError, ValueError):
        return None


def _pid_alive(pid: int | None) -> bool:
    """Checks if a process is still running.

    Args:
        pid (int | None): Process ID.

    Returns:
        (bool): `True` if the process is running or it cannot be checked.
    """
    # NOTE: On Windows, signal 0 is CTRL_C_EVENT, so it cannot be used
    if pid is None or os.name == "nt":
        return True

    try:
        os.kill(pid, 0)

    except ProcessLookupError:
        return False

    except PermissionError:
        return True

    return True


class RunStore:
    """Stores the state and output of the parallel commands of a recipe run.
    Each run gets a folder containing a `run.json` file, and a `<id>.json`
    and `<id>.log` file per command.

    Args:
        recipe_file (str): Recipe `.yaml` file being run.
        root (str | None): Folder containing all runs. Defaults to the recp
            state folder.
        keep (int): Number of runs kept. Older runs are deleted.
    """
    def __init__(
            self,
            recipe_file: str,
            root: str | None = None,
            keep: int = 20
    ) -> None:
        super().__init__()

        self.root = root or get_runs_dir()
        started = datetime.now()
        recipe_name = os.path.splitext(os.path.basename(recipe_file))[0]
        self.next_id = 1
        os.makedirs(self.root, exist_ok=True)

        # NOTE: A suffix is added if the same process starts several runs
        # within a second
        base_id = f"{started:%Y%m%d-%H%M%S}-{os.getpid()}"
        self.id = base_id
        suffix = 1

        while True:
            self.dir = os.path.join(self.root, self.id)

            try:
                os.mkdir(self.dir)
                break

            except FileExistsError:
                suffix += 1
                self.id = f"{base_id}-{suffix}"
        self._meta = {
            "id": self.id,
            "recipe": recipe_name,
            "file": os.path.abspath(recipe_file),
            "pid": os.getpid(),
            "started": started.timestamp(),
            "finished": None,
            "returncode": None
        }
        _write_json(os.path.join(self.dir, "run.json"), self._meta)
        self.prune(keep=keep)

    def prune(self, keep: int) -> None:
        """Deletes the oldest runs.

        Args:
            keep (int): Number of runs kept.
        """
        runs = list_runs(self.root)

        for run_id in runs[:max(len(runs) - keep, 0)]:
            if run_id != self.id:
                shutil.rmtree(os.path.join(self.root, run_id), True)

    def log_file(self, cmd_id: int) -> str:
        """Returns the file where the output of a command is written.

        Args:
            cmd_id (int): Command ID within the run.

        Returns:
            (str): Output `.log` file.
        """
        return os.path.join(self.dir, f"{cmd_id}.log")

    def update(self, job: Any, step: str) -> None:
        """Saves the state of a command.

        Args:
            job (Job): Command whose state is saved.
            step (str): Name of the step of the command.
        """
        _write_json(
            os.path.join(self.dir, f"{job.id}.json"),
            {
                "id": job.id,
                "step": step,
                "label": job.label,
                "cmd": job.cmd,
                "status": job.status,
                "start": job.start,
                "end": job.end,
                "returncode": job.returncode
            }
        )

    def finish(self, returncode: int) -> None:
        """Marks the run as finished.

        Args:
            returncode (int): Exit code of the run.
        """
        self._meta["finished"] = datetime.now().timestamp()
        self._meta["returncode"] = returncode
        _write_json(os.path.join(self.dir, "run.json"), self._meta)


def list_runs(root: str | None = None) -> list[str]:
    """Returns the IDs of the stored runs, oldest first.

    Args:
        root (str | None): Folder containing all runs. Defaults to the recp
            state folder.

    Returns:
        (list[str]): Run IDs.
    """
    root = root or get_runs_dir()

    if not os.path.isdir(root):
        return []

    return sorted(
        d for d in os.listdir(root)
        if os.path.isfile(os.path.join(root, d, "run.json"))
    )


def load_run(run_id: str | None = None, root: str | None = None) -> dict:
    """Loads the state of a run and its commands.

    Args:
        run_id (str | None): Run ID. Defaults to the latest run.
        root (str | None): Folder containing all runs. Defaults to the recp
            state folder.

    Returns:
        (dict): Run data, with its commands sorted by ID in the `commands`
            key. Commands of runs that stopped without finishing them are
            marked as `interrupted`.
    """
    root = root or get_runs_dir()
    runs = list_runs(root)

    if len(runs) == 0:
        raise RecpError(
            "No runs found. Logs are only saved for steps with a 'parallel' "
            "key"
        )

    if run_id is None:
        run_id = runs[-1]

    elif run_id not in runs:
        raise RecpError(
            f"Run {run_id!r} not found. Run 'recp status --list' to list "
            "stored runs"
        )

    run_dir = os.path.join(root, run_id)
    run = _read_json(os.path.join(run_dir, "run.json")) or {}
    commands = []

    for file in os.listdir(run_dir):
        stem, ext = os.path.splitext(file)

        if ext == ".json" and stem.isdigit():
            cmd = _read_json(os.path.join(run_dir, file))

            if cmd is not None:
                cmd["log"] = os.path.join(run_dir, f"{stem}.log")
                commands.append(cmd)

    run["dir"] = run_dir
    run["alive"] = run.get("finished") is None and _pid_alive(run.get("pid"))
    run["commands"] = sorted(commands, key=lambda c: c["id"])

    if run.get("finished") is None and not run["alive"]:
        for cmd in run["commands"]:
            if cmd["status"] in ("queued", "running"):
                cmd["status"] = "interrupted"

    return run


def find_command(run: dict, cmd_id: int) -> dict:
    """Finds a command of a run by its ID.

    Args:
        run (dict): Run data returned by `load_run`.
        cmd_id (int): Command ID.

    Returns:
        (dict): Command data.
    """
    for cmd in run["commands"]:
        if cmd["id"] == cmd_id:
            return cmd

    raise RecpError(
        f"Command #{cmd_id} not found in run {run['id']!r}. Run 'recp status' "
        "to list its commands"
    )


STATUS_TAGS = {
    "queued": ("dim",),
    "running": ("cyan",),
    "done": ("green",),
    "failed": ("error",),
    "cancelled": ("warning",),
    "interrupted": ("warning",),
}


def _format_time(timestamp: float | None) -> str:
    if timestamp is None:
        return "-"

    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def _run_state(run: dict) -> str:
    if run.get("finished") is not None:
        if run.get("returncode") == 130:
            return "interrupted"

        return "failed" if run.get("returncode") else "done"

    return "running" if run["alive"] else "interrupted"


def print_runs(root: str | None = None) -> None:
    """Prints the stored runs, newest last.

    Args:
        root (str | None): Folder containing all runs. Defaults to the recp
            state folder.
    """
    runs = list_runs(root)

    if len(runs) == 0:
        print("No runs found. Logs are only saved for steps with a 'parallel' "
              "key")
        return

    for run_id in runs:
        run = load_run(run_id, root=root)
        state = _run_state(run)
        started = datetime.fromtimestamp(run["started"])
        print(
            f"{style(run_id.ljust(24), 'b', 'cyan')}"
            f"{run.get('recipe', '?').ljust(24)}"
            f"{style(state.capitalize().ljust(13), *STATUS_TAGS[state])}"
            f"{style(f'{started:%Y-%m-%d %H:%M}', 'dim')}  "
            f"{len(run['commands'])} command(s)"
        )


def print_status(run_id: str | None = None, root: str | None = None) -> None:
    """Prints the status of the parallel commands of a run.

    Args:
        run_id (str | None): Run ID. Defaults to the latest run.
        root (str | None): Folder containing all runs. Defaults to the recp
            state folder.
    """
    run = load_run(run_id, root=root)
    state = _run_state(run)
    started = datetime.fromtimestamp(run["started"])
    print(
        f"{style('Run', 'b')} {style(run['id'], 'b', 'cyan')}  "
        f"{run.get('recipe', '?')}  "
        f"{style(f'started {started:%Y-%m-%d %H:%M:%S}', 'dim')}  "
        f"{style(state, *STATUS_TAGS[state])}"
    )

    commands = run["commands"]
    id_width = max((len(str(c["id"])) for c in commands), default=1)
    step_width = max((len(c["step"]) for c in commands), default=4) + 2
    print(style(
        "#".ljust(id_width) + "  " + "Step".ljust(step_width)
        + "Status".ljust(13) + "Time".ljust(10) + "Label",
        "dim"
    ))

    now = datetime.now().timestamp()

    for cmd in commands:
        elapsed = None

        if cmd["start"] is not None:
            elapsed = (cmd["end"] or now) - cmd["start"]

            if cmd["status"] == "interrupted":
                elapsed = None

        print(
            f"{str(cmd['id']).ljust(id_width)}  "
            f"{cmd['step'].ljust(step_width)}"
            f"{style(cmd['status'].capitalize().ljust(13), *STATUS_TAGS[cmd['status']])}"
            f"{format_duration(elapsed).ljust(10)}"
            f"{cmd['label'] or cmd['cmd']}"
        )


def _print_command_header(cmd: dict) -> None:
    status = cmd["status"]
    exit_repr = (
        f" (exit {cmd['returncode']})"
        if cmd["returncode"] not in (None, 0) else ""
    )
    print(style(
        f"#{cmd['id']}  {cmd['step']}  ", "dim"
    ) + style(f"{status}{exit_repr}", *STATUS_TAGS[status]) + style(
        f"  {_format_time(cmd['start'])} → {_format_time(cmd['end'])}", "dim"
    ))
    print(style(f"cmd: {cmd['cmd']}", "dim"))


def print_log(
        cmd_id: int,
        run_id: str | None = None,
        lines: int | None = None,
        root: str | None = None
) -> None:
    """Prints the saved output of a command.

    Args:
        cmd_id (int): Command ID.
        run_id (str | None): Run ID. Defaults to the latest run.
        lines (int | None): If given, only the last `lines` lines are printed.
        root (str | None): Folder containing all runs. Defaults to the recp
            state folder.
    """
    run = load_run(run_id, root=root)
    cmd = find_command(run, cmd_id)
    _print_command_header(cmd)

    try:
        with open(cmd["log"], encoding="utf-8", errors="replace") as f:
            output = collapse_cr(f.read())

    except FileNotFoundError:
        print(style("(no output yet)", "dim"))
        return

    if lines is not None:
        output = "\n".join(output.rstrip("\n").split("\n")[-lines:]) + "\n"

    print(output, end="" if output.endswith("\n") else "\n")


def follow(
        cmd_id: int,
        run_id: str | None = None,
        root: str | None = None,
        poll_interval: float = 0.2
) -> int:
    """Streams the output of a command while it runs.

    Args:
        cmd_id (int): Command ID.
        run_id (str | None): Run ID. Defaults to the latest run.
        root (str | None): Folder containing all runs. Defaults to the recp
            state folder.
        poll_interval (float): Seconds between checks for new output.

    Returns:
        (int): Exit code of the command, or `0` if it is unknown.
    """
    run = load_run(run_id, root=root)
    run_id = run["id"]
    cmd = find_command(run, cmd_id)
    label = cmd["label"] or cmd["cmd"]
    print(style(
        f"Following #{cmd_id} ({label}) · Ctrl-C stops following, not the "
        "command",
        "dim"
    ), flush=True)

    if cmd["status"] == "queued":
        print(style(f"Waiting for #{cmd_id} to start ...", "dim"), flush=True)

    position = 0

    while True:
        # Read the state before the output, so that no output written right
        # before the command finished is missed
        cmd = find_command(load_run(run_id, root=root), cmd_id)

        try:
            with open(cmd["log"], "rb") as f:
                f.seek(position)
                data = f.read()

        except FileNotFoundError:
            data = b""

        if data:
            position += len(data)
            sys.stdout.buffer.write(data)
            sys.stdout.flush()

        if cmd["status"] not in ("queued", "running"):
            break

        time.sleep(poll_interval)

    _print_command_header(cmd)
    return cmd["returncode"] or 0
