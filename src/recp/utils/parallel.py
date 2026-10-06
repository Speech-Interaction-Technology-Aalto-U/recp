import os
import re
import sys
import time
import codecs
import contextlib
import shlex
import shutil
import threading
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from .display import (
    print_error,
    print_hint,
    style
)

OUTPUT_MODES = ("auto", "board", "grouped", "prefix")
ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b[@-_]"
)
NEWLINE_RE = re.compile(r"(\r\n|\n|\r)")
STATUS_STYLES = {
    "queued": ("Queued", ("dim",)),
    "running": ("Running", ("cyan",)),
    "done": ("Done", ("green",)),
    "failed": ("Failed", ("error",)),
    "cancelled": ("Cancelled", ("warning",)),
}
PREFIX_COLORS = ("cyan", "magenta", "green", "warning")

# Seconds between redraws of the board, and between progress bar updates
# printed in prefix mode
BOARD_REFRESH_INTERVAL = 0.25
PREFIX_PROGRESS_INTERVAL = 2.0


def resolve_output_mode(mode: str, stream=None) -> str:
    """Returns the output mode used for parallel steps.

    Args:
        mode (str): One of `auto`, `board`, `grouped` or `prefix`. `auto`
            uses `board` when printing to a terminal that supports it, and
            `grouped` otherwise.
        stream (TextIO | None): Output stream. Defaults to `sys.stdout`.

    Returns:
        (str): One of `board`, `grouped` or `prefix`.
    """
    if mode != "auto":
        return mode

    stream = stream or sys.stdout

    if not (hasattr(stream, "isatty") and stream.isatty()):
        return "grouped"

    if os.environ.get("TERM") == "dumb":
        return "grouped"

    # NOTE: The legacy Windows console does not support cursor movement
    if os.name == "nt" and not os.environ.get("WT_SESSION"):
        return "grouped"

    return "board"


def strip_ansi(text: str) -> str:
    """Removes ANSI escape sequences (colors, cursor movement) from a string.

    Args:
        text (str): Input string.

    Returns:
        (str): String without escape sequences.
    """
    return ANSI_ESCAPE_RE.sub("", text)


def collapse_cr(text: str) -> str:
    """Keeps only the last frame of lines redrawn with carriage returns, such
    as progress bars.

    Args:
        text (str): Command output.

    Returns:
        (str): Output with one frame per line.
    """
    lines = []

    for line in text.replace("\r\n", "\n").split("\n"):
        frames = [f for f in line.split("\r") if f != ""]
        lines.append(frames[-1] if frames else "")

    return "\n".join(lines)


def format_duration(seconds: float | None) -> str:
    """Formats a duration as `mm:ss`, or `h:mm:ss` if longer than an hour.

    Args:
        seconds (float | None): Duration in seconds.

    Returns:
        (str): Formatted duration, or `-` if `seconds` is `None`.
    """
    if seconds is None:
        return "-"

    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes:02d}:{secs:02d}"


def _split_cmd(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)

    except ValueError:
        return cmd.split()


def _is_option_value(tokens: list[str], idx: int, common: set[str]) -> bool:
    return (
        idx > 0
        and tokens[idx - 1].startswith("-")
        and tokens[idx - 1] in common
    )


def infer_labels(cmds: list[str]) -> list[str]:
    """Returns a short label for each command, made of the part that differs
    from the other commands, if all commands have the same number of
    arguments. For example, the commands `run --weight 0.5` and
    `run --weight 1.0` are labeled as `--weight 0.5` and `--weight 1.0`.

    Args:
        cmds (list[str]): Commands of a step.

    Returns:
        (list[str]): A label per command. Labels are empty if they cannot be
            inferred.
    """
    if len(cmds) < 2:
        return [""] * len(cmds)

    tokens = [_split_cmd(cmd) for cmd in cmds]

    # Only commands generated from the same template are labeled, since
    # labels of unrelated commands would not be meaningful
    if len({len(t) for t in tokens}) > 1:
        return [""] * len(cmds)

    common = set.intersection(*(set(t) for t in tokens))
    labels = []

    for cmd_tokens in tokens:
        # Shortest differing token, preferring values of options (e.g.
        # `--weight 0.5`) since the option name describes the value
        candidates = [
            (not _is_option_value(cmd_tokens, i, common), len(t), i)
            for i, t in enumerate(cmd_tokens) if t not in common
        ]

        if len(candidates) == 0:
            labels.append("")
            continue

        *_, idx = min(candidates)
        label = cmd_tokens[idx]

        if _is_option_value(cmd_tokens, idx, common):
            label = f"{cmd_tokens[idx - 1]} {label}"

        labels.append(label)

    if "" not in labels and len(set(labels)) == len(labels):
        return labels

    # Fall back to all differing option values (e.g. `--model a --seed 0`),
    # leaving out paths since they are usually derived from other values,
    # and then to all differing tokens
    def option_labels(include_paths: bool) -> list[str]:
        return [
            " ".join(
                f"{cmd_tokens[i - 1]} {t}"
                for i, t in enumerate(cmd_tokens)
                if t not in common
                and _is_option_value(cmd_tokens, i, common)
                and (include_paths or os.sep not in t and "/" not in t)
            )
            for cmd_tokens in tokens
        ]

    all_labels = [
        " ".join(t for t in cmd_tokens if t not in common)
        for cmd_tokens in tokens
    ]

    for labels in (option_labels(False), option_labels(True), all_labels):
        if "" not in labels and len(set(labels)) == len(labels):
            return labels

    return [""] * len(cmds)


@dataclass
class Job:
    """A command run in a parallel step.

    Args:
        id (int): Command ID, unique within a recipe run.
        cmd (str): Command.
        label (str): Short name of the command. If empty, the command itself
            is used.
        log_file (str | None): File where the output is written, if any.
    """
    id: int
    cmd: str
    label: str = ""
    log_file: str | None = None
    status: str = "queued"
    start: float | None = None
    end: float | None = None
    returncode: int | None = None
    last_line: str = ""
    output: list[str] = field(default_factory=list)
    _partial: str = ""
    _after_cr: bool = False
    _last_progress: float = 0.0

    @property
    def name(self) -> str:
        """Label of the command, or the command itself if it has no label."""
        return self.label or self.cmd

    @property
    def elapsed(self) -> float | None:
        """Seconds the command has been running, or ran for."""
        if self.start is None:
            return None

        return (self.end or time.time()) - self.start

    @property
    def current_line(self) -> str:
        """Last line of output, including an unfinished progress bar."""
        partial = strip_ansi(self._partial).strip()
        return partial if partial else self.last_line

    def feed(self, text: str) -> list[tuple[str, bool]]:
        """Adds output of the command.

        Args:
            text (str): Output text.

        Returns:
            (list[tuple[str, bool]]): Completed lines, each with a flag that
                is `True` if the line is a frame redrawn with a carriage
                return (e.g. a progress bar).
        """
        self.output.append(text)
        lines = []

        for part in NEWLINE_RE.split(text):
            if part in ("\n", "\r\n"):
                lines.append((self._partial, False))
                self._set_last_line(self._partial)
                self._partial = ""
                self._after_cr = False

            elif part == "\r":
                self._after_cr = True

            elif part:
                if self._after_cr:
                    if self._partial:
                        lines.append((self._partial, True))
                        self._set_last_line(self._partial)

                    self._partial = ""
                    self._after_cr = False

                self._partial += part

        return lines

    def flush(self) -> str:
        """Returns the unfinished last line of output and clears it."""
        partial, self._partial = self._partial, ""
        self._set_last_line(partial)
        return partial

    def _set_last_line(self, line: str) -> None:
        line = strip_ansi(line).strip()

        if line:
            self.last_line = line


class ParallelRunner:
    """Runs the commands of a step in parallel and shows their output.

    Output modes:
        - `grouped`: The output of each command is printed when it finishes.
        - `board`: Like `grouped`, plus a table with the status and last
            output line of each command, redrawn under the output.
        - `prefix`: Output lines are printed as they arrive, prefixed with
            the command ID and label.

    Args:
        jobs (list[Job]): Commands to run.
        cwd (str | None): Folder where the commands are run.
        env (dict): Environment variables passed to the commands.
        num_jobs (int): Maximum number of commands run at the same time.
        indent (str): Indentation used when printing.
        mode (str): Output mode.
        title (str): Title of the board, usually the step name.
        ignore_errors (bool): If `True`, commands are run even after a
            command fails. Otherwise, no new commands are started after a
            failure, but running commands are allowed to finish.
        on_change (Callable[[Job], None] | None): Called whenever the status
            of a command changes.
        stream (TextIO | None): Output stream. Defaults to `sys.stdout`.
    """
    def __init__(
            self,
            jobs: list[Job],
            cwd: str | None,
            env: dict,
            num_jobs: int,
            indent: str = "",
            mode: str = "grouped",
            title: str = "",
            ignore_errors: bool = False,
            on_change: Callable[[Job], None] | None = None,
            stream=None
    ) -> None:
        super().__init__()

        self.jobs = jobs
        self.cwd = cwd
        self.env = env
        self.num_jobs = num_jobs
        self.indent = indent
        self.mode = mode
        self.title = title
        self.ignore_errors = ignore_errors
        self.on_change = on_change
        self.stream = stream or sys.stdout

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._done = threading.Event()
        self._interrupted = False
        self._num_done = 0
        self._start = time.time()
        self._board_height = 0
        self._id_width = len(str(max((j.id for j in jobs), default=0)))
        self._label_width = max((len(j.label) for j in jobs), default=0)

    def run(self) -> list[int]:
        """Runs all commands.

        Returns:
            (list[int]): Exit code of each command that was run.
        """
        renderer = None

        if self.mode == "board":
            self._write("\033[?25l")
            renderer = threading.Thread(target=self._render_loop, daemon=True)
            renderer.start()

        try:
            with ThreadPoolExecutor(max_workers=self.num_jobs) as executor:
                futures = [executor.submit(self._run_job, j) for j in self.jobs]

                try:
                    returncodes = [f.result() for f in futures]

                except KeyboardInterrupt:
                    self._interrupted = True
                    self._stop.set()

                    for future in futures:
                        future.cancel()

                    raise

        finally:
            self._done.set()

            if renderer is not None:
                renderer.join()

            with self._lock:
                for job in self.jobs:
                    if job.status == "queued":
                        job.status = "cancelled"
                        self._notify(job)

                if self.mode == "board":
                    self._clear_board()
                    self._print_final_table()
                    self._write("\033[?25h")

        return [rc for rc in returncodes if rc is not None]

    def _run_job(self, job: Job) -> int | None:
        if self._stop.is_set():
            return None

        with self._lock:
            job.status = "running"
            job.start = time.time()
            self._notify(job)

        with contextlib.ExitStack() as stack:
            log = None

            if job.log_file is not None:
                with contextlib.suppress(OSError):
                    log = stack.enter_context(
                        open(job.log_file, "w", encoding="utf-8")
                    )

            returncode = self._stream_output(job, log)

        with self._lock:
            job.end = time.time()
            job.returncode = returncode

            if returncode == 0:
                job.status = "done"

            elif self._interrupted:
                job.status = "cancelled"

            else:
                job.status = "failed"

            self._num_done += 1
            self._notify(job)

            if self.mode == "prefix":
                self._print_prefix_end(job)

            else:
                self._emit(lambda: self._print_job(job))

            if returncode != 0 and not self.ignore_errors:
                self._stop.set()

        return returncode

    def _stream_output(self, job: Job, log) -> int:
        try:
            process = subprocess.Popen(
                job.cmd,
                shell=True,
                cwd=self.cwd,
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )

        except OSError as e:
            with self._lock:
                job.feed(f"{e}\n")

            return 127

        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        fd = process.stdout.fileno()

        while True:
            chunk = os.read(fd, 65536)
            text = decoder.decode(chunk, final=not chunk)

            if text:
                if log is not None:
                    log.write(text)
                    log.flush()

                with self._lock:
                    lines = job.feed(text)

                    if self.mode == "prefix":
                        self._print_prefix_lines(job, lines)

            if not chunk:
                break

        process.stdout.close()
        return process.wait()

    def _notify(self, job: Job) -> None:
        if self.on_change is not None:
            with contextlib.suppress(OSError):
                self.on_change(job)

    # --------------------------------------------------------------------------
    # SECTION: GROUPED AND BOARD OUTPUT
    # --------------------------------------------------------------------------
    def _print_job(self, job: Job) -> None:
        """Prints the header and full output of a finished command."""
        progress_repr = f"[{self._num_done}/{len(self.jobs)}]"

        if self.mode == "board":
            status, tags = STATUS_STYLES[job.status]
            print(
                f"{self.indent}"
                f"{style('Command:'.ljust(13) + f'#{job.id}  {job.name}', 'dim')}"
                f"  {style(status.lower(), *tags)} "
                f"{style(f'in {format_duration(job.elapsed)}', 'dim')} "
                f"{style(progress_repr, 'dim')}",
                file=self.stream
            )

        else:
            print(
                f"{self.indent}{style('Command:'.ljust(13) + job.cmd, 'dim')} "
                f"{style(progress_repr, 'dim')}",
                file=self.stream
            )

        output = collapse_cr("".join(job.output))

        if output:
            print(output, end="" if output.endswith("\n") else "\n",
                  file=self.stream)

        self.stream.flush()

        if job.returncode != 0:
            print_error(
                f"Command failed with exit code {job.returncode}",
                indent=self.indent
            )

            if self.mode == "board" and job.log_file is not None:
                print_hint(
                    f"Command and output saved, see 'recp log {job.id}'",
                    indent=self.indent
                )

    def _emit(self, fn: Callable[[], None]) -> None:
        """Prints above the board, if any."""
        if self.mode != "board":
            fn()
            return

        self._clear_board()
        fn()
        sys.stderr.flush()
        self._draw_board()

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()

    def _render_loop(self) -> None:
        with self._lock:
            self._draw_board()

        while not self._done.wait(BOARD_REFRESH_INTERVAL):
            with self._lock:
                self._clear_board(redraw=True)

    def _clear_board(self, redraw: bool = False) -> None:
        # Move to the first line of the board and clear until the end of the
        # screen
        clear = (
            f"\033[{self._board_height}F\033[J" if self._board_height else ""
        )

        if redraw:
            lines = self._board_lines()
            self._board_height = len(lines)
            self._write(clear + "".join(f"{line}\n" for line in lines))

        else:
            self._board_height = 0
            self._write(clear)

    def _draw_board(self) -> None:
        lines = self._board_lines()
        self._board_height = len(lines)
        self._write("".join(f"{line}\n" for line in lines))

    def _counts_repr(self) -> list[tuple[str, tuple[str, ...]]]:
        counts = dict.fromkeys(STATUS_STYLES, 0)

        for job in self.jobs:
            counts[job.status] += 1

        cells = [
            (f"{counts['done']} done", ("green",) if counts["done"] else ()),
            (" · ", ("dim",)),
            (
                f"{counts['running']} running",
                ("cyan",) if counts["running"] else ()
            ),
            (" · ", ("dim",)),
            (f"{counts['queued']} queued", ()),
            (" · ", ("dim",)),
            (
                f"{counts['failed']} failed",
                ("error",) if counts["failed"] else ()
            ),
        ]

        if counts["cancelled"]:
            cells += [
                (" · ", ("dim",)),
                (f"{counts['cancelled']} cancelled", ("warning",))
            ]

        return cells

    def _table_lines(
            self,
            jobs: list[Job],
            width: int,
            last_line: bool
    ) -> list[str]:
        label_width = min(
            max((len(j.name) for j in jobs), default=5),
            max(12, width // 3)
        )
        id_width = max(self._id_width, 1)
        header = [
            (
                " " + "#".ljust(id_width) + "  " + "Status".ljust(11)
                + "Time".ljust(9) + "Label".ljust(label_width)
                + ("  Last line" if last_line else ""),
                ("dim",)
            )
        ]
        lines = [_fit(header, width)]

        for job in jobs:
            status, tags = STATUS_STYLES[job.status]
            name = job.name

            if len(name) > label_width:
                name = name[:label_width - 1] + "…"

            cells = [
                (" " + str(job.id).ljust(id_width) + "  ", ()),
                (status.ljust(11), tags),
                (
                    format_duration(job.elapsed).ljust(9),
                    ("dim",) if job.start is None else ()
                ),
                (name.ljust(label_width), ()),
            ]

            if last_line and job.status == "running":
                cells.append(("  " + job.current_line, ("dim",)))

            lines.append(_fit(cells, width))

        return lines

    def _board_lines(self) -> list[str]:
        width, height = shutil.get_terminal_size((80, 24))
        width = max(width - 1, 20)
        rule = style("─" * width, "dim")
        elapsed = format_duration(time.time() - self._start)
        title = [(" " + self.title, ("b",)), ("  ", ())]
        counts = self._counts_repr()
        used = sum(len(t) for t, _ in title + counts)
        pad = max(width - used - len(elapsed), 1)
        summary = _fit(title + counts + [(" " * pad + elapsed, ("dim",))],
                       width)

        # Show running commands first, then the most recently finished ones,
        # then queued ones, but always in ID order
        max_rows = max(height - 6, 1)
        jobs = self.jobs

        if len(jobs) > max_rows:
            running = [j for j in jobs if j.status == "running"]
            finished = sorted(
                (j for j in jobs if j.end is not None),
                key=lambda j: j.end,
                reverse=True
            )
            queued = [j for j in jobs if j.status == "queued"]
            selected = (running + finished + queued)[:max(max_rows - 1, 1)]
            jobs = sorted(selected, key=lambda j: j.id)

        lines = [rule, summary, *self._table_lines(jobs, width, True)]

        if len(jobs) < len(self.jobs):
            lines.append(
                style(f" … {len(self.jobs) - len(jobs)} more", "dim")
            )

        return [*lines, rule]

    def _print_final_table(self) -> None:
        width = max(shutil.get_terminal_size((80, 24)).columns - 1, 20)
        title = [(" " + self.title, ("b",)), ("  ", ())]
        elapsed = format_duration(time.time() - self._start)
        lines = [
            "",
            _fit(title + self._counts_repr()
                 + [(f"  in {elapsed}", ("dim",))], width)
        ]

        # Long tables only show the commands that did not succeed
        jobs = self.jobs

        if len(jobs) > 20:
            jobs = [j for j in jobs if j.status != "done"]

        if jobs:
            lines += self._table_lines(jobs, width, False)

        self._write("".join(f"{line}\n" for line in lines))

    # --------------------------------------------------------------------------
    # SECTION: PREFIX OUTPUT
    # --------------------------------------------------------------------------
    def _prefix(self, job: Job) -> str:
        tag = str(job.id).rjust(self._id_width)

        if self._label_width:
            tag += " " + job.label.ljust(self._label_width)

        color = PREFIX_COLORS[(job.id - 1) % len(PREFIX_COLORS)]
        return style(f"[{tag}]", color)

    def _print_prefix_lines(
            self,
            job: Job,
            lines: list[tuple[str, bool]]
    ) -> None:
        now = time.time()

        for line, is_progress in lines:
            if is_progress:
                if now - job._last_progress < PREFIX_PROGRESS_INTERVAL:
                    continue

                job._last_progress = now

            print(f"{self._prefix(job)} {line}", file=self.stream)

        self.stream.flush()

    def _print_prefix_end(self, job: Job) -> None:
        partial = job.flush()

        if partial:
            print(f"{self._prefix(job)} {partial}", file=self.stream)

        if job.returncode == 0:
            print(
                f"{self._prefix(job)} "
                f"{style(f'done in {format_duration(job.elapsed)}', 'dim')} "
                f"{style(f'[{self._num_done}/{len(self.jobs)}]', 'dim')}",
                file=self.stream,
                flush=True
            )

        else:
            print_error(
                f"Command #{job.id} failed with exit code {job.returncode}",
                indent=self.indent
            )


def _fit(cells: list[tuple[str, tuple[str, ...]]], width: int) -> str:
    """Joins styled cells into a line, truncated to a maximum width.

    Args:
        cells (list[tuple[str, tuple[str, ...]]]): Text and style tags of
            each cell.
        width (int): Maximum number of characters.

    Returns:
        (str): Styled line.
    """
    line = ""
    remaining = width

    for text, tags in cells:
        if remaining <= 0:
            break

        text = text.replace("\t", " ")[:remaining]
        remaining -= len(text)
        line += style(text, *tags) if text.strip() else text

    return line
