import os
import sys
import yaml
import subprocess
from copy import deepcopy
from datetime import datetime
from typing import Any
from importlib.metadata import version as package_version
from packaging.version import Version
from .collections import (
    make_list,
    temp_env
)
from .apply import get_apply_registry
from .display import (
    exit_error,
    print_error,
    print_hint,
    print_warning,
    style
)
from .parallel import (
    Job,
    ParallelRunner,
    infer_labels,
    resolve_output_mode
)
from .runs import RunStore


class Recipe:
    """Class that represents a recipe loaded from a file and all the additional
    necessary functionality to run the commands on all steps found in the
    recipe.

    Args:
        file (str): Recipe `.yaml` file.
        allow_expr (bool): If `True`, allows using the the `!expr` directive in
            the recipe. This is not allowed by default because this expression
            if considered unsafe.
        preview (bool): If `True`, the `!expr`, `!shell` and `!lines`
            constructors are not evaluated, so that the recipe can be
            inspected without running anything.
    """
    ROOT_KEY = "recipe"
    ENV_KEY = "env"
    MINIMUM_REQUIRED_VERSION_KEY = "minimum_required_version"
    MANDATORY_STEP_KEYS = ("run",)
    OPTIONAL_STEP_KEYS = ("tag", "description", "env", "cwd", "parallel")
    PACKAGE_VERSION = Version(package_version("recp"))
    ESCAPED_DOLLAR = "\0"
    CMD_SEPARATOR = "\x1f"
    def __init__(
            self,
            file: str,
            allow_expr: bool = False,
            preview: bool = False
    ) -> None:
        super().__init__()

        # Params
        self.file = file
        self.allow_expr = allow_expr
        self.preview = preview

        # Single timestamp shared by all !now constructors
        self._now = datetime.now()

        # Load and validate file structure
        self._data = self.load(self.file)
        self.validate_minimum_version_required(self._data)
        self.validate_keys(self._data)

        # Cache apply registry
        self._apply_registry = get_apply_registry()

        # Logs of parallel commands, created when the first one is run
        self._run_store = None

    @staticmethod
    def expandall_recursive(
            path: Any | list[Any],
            max_iters: int = 10
    ) -> Any:
        if isinstance(path, list):
            return [Recipe.expandall_recursive(p, max_iters) for p in path]

        if not isinstance(path, str):
            return path

        seen = set()
        # $$ is an escaped $ that is never expanded
        current = path.replace("$$", Recipe.ESCAPED_DOLLAR)

        for _ in range(max_iters):
            if current in seen:
                raise RecursionError("Cyclic path expansion detected")

            seen.add(current)
            next = os.path.expanduser(os.path.expandvars(current))

            if next == current:
                break

            current = next

        return current.replace(Recipe.ESCAPED_DOLLAR, "$")

    def _yaml_expr_constructor(
            self,
            loader: yaml.loader.SafeLoader,
            node: yaml.nodes.ScalarNode
    ) -> int | float:
        if self.preview:
            return f"!expr {loader.construct_scalar(node)}"

        if not self.allow_expr:
            exit_error(
                f"Invalid !expr constructor at line {node.start_mark.line + 1}"
                f" in recipe file {self.file!r}. The !expr constructor is only"
                " allowed when the --unsafe option is enabled."
            )

        expr = loader.construct_scalar(node)
        return eval(expr)

    def _yaml_input_constructor(
            self,
            loader: yaml.loader.SafeLoader,
            node: yaml.nodes.Node
    ) -> str:
        # Get config
        # NOTE: This constructor is not solved here because steps must be
        # first filtered to solve only necessary constructors
        if isinstance(node, yaml.nodes.MappingNode):
            map = loader.construct_mapping(node)
            map["__constructor__"] = "!input"

            if "name" not in map:
                exit_error(
                    f"!input constructor at line {node.start_mark.line + 1} in"
                    f" recipe file {self.file!r} is missing the 'name' key"
                )

        elif isinstance(node, yaml.nodes.ScalarNode):
            map = {
                "name": str(loader.construct_scalar(node)),
                "default": None,
                "required": False,
                "__constructor__": "!input"
            }

        else:
            exit_error(
                f"!input constructor found on a {node.__class__.__name__!r} at"
                f" line {node.start_mark.line + 1} in recipe file "
                f"{self.file!r}. !input constructors only support str or dict "
                "values."
            )

        return map

    def _yaml_prompt_constructor(
            self,
            loader: yaml.loader.SafeLoader,
            node: yaml.nodes.MappingNode
    ) -> str:
        if not isinstance(node, yaml.nodes.MappingNode):
            exit_error(
                f"!prompt constructor at line {node.start_mark.line + 1} in "
                f"recipe file {self.file!r} should be a dict with at least a "
                "'message' key"
            )

        map = loader.construct_mapping(node, deep=True)
        map["message"] = str(map.get("message", ""))
        map["choices"] = map.get("choices")
        map["default"] = map.get("default")
        map["__constructor__"] = "!prompt"

        # It should be a list of str
        if map["choices"] is not None:
            if not isinstance(map["choices"], list):
                exit_error(
                    f"'choices' of !prompt constructor at line "
                    f"{node.start_mark.line + 1} in recipe file {self.file!r}"
                    " should be a list of str choices"
                )

            map["choices"] = [str(c) for c in map["choices"]]

        if map["default"] is not None:
            map["default"] = str(map["default"])

        return map

    def _yaml_split_constructor(
            self,
            loader: yaml.loader.SafeLoader,
            node: yaml.nodes.ScalarNode
    ) -> list[str]:
        value = loader.construct_scalar(node)
        return str(value).split()

    def _yaml_lines_constructor(
            self,
            loader: yaml.loader.SafeLoader,
            node: yaml.nodes.ScalarNode
    ) -> list[str]:
        file = self.expandall_recursive(str(loader.construct_scalar(node)))

        if self.preview:
            return [f"!lines {file}"]

        if not os.path.isfile(file):
            exit_error(
                f"File {file!r} used in !lines constructor at line "
                f"{node.start_mark.line + 1} in recipe file {self.file!r} not "
                "found"
            )

        # Empty lines and lines starting with # are ignored
        with open(file) as f:
            lines = [line.strip() for line in f]

        return [line for line in lines if line and not line.startswith("#")]

    def _yaml_shell_constructor(
            self,
            loader: yaml.loader.SafeLoader,
            node: yaml.nodes.ScalarNode
    ) -> str:
        cmd = str(loader.construct_scalar(node))

        if self.preview:
            return f"!shell {cmd}"

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            exit_error(
                f"Command {cmd!r} used in !shell constructor at line "
                f"{node.start_mark.line + 1} in recipe file {self.file!r} "
                f"failed with exit code {result.returncode}"
                + (f": {stderr}" if stderr else "")
            )

        return result.stdout.strip()

    def _yaml_now_constructor(
            self,
            loader: yaml.loader.SafeLoader,
            node: yaml.nodes.ScalarNode
    ) -> str:
        format = str(loader.construct_scalar(node)) or "%Y-%m-%d"
        return self._now.strftime(format)

    def load(self, file: str) -> dict:
        """Loads a `.yaml` recipe file.

        Args:
            file (str): `.yaml` recipe file to be loaded.

        Returns:
            (dict): Parsed `.yaml` recipe file.
        """
        # Add custom constructors to a loader that is local to this recipe
        class RecipeLoader(yaml.SafeLoader):
            pass

        RecipeLoader.add_constructor("!expr", self._yaml_expr_constructor)
        RecipeLoader.add_constructor("!input", self._yaml_input_constructor)
        RecipeLoader.add_constructor("!prompt", self._yaml_prompt_constructor)
        RecipeLoader.add_constructor("!split", self._yaml_split_constructor)
        RecipeLoader.add_constructor("!lines", self._yaml_lines_constructor)
        RecipeLoader.add_constructor("!shell", self._yaml_shell_constructor)
        RecipeLoader.add_constructor("!now", self._yaml_now_constructor)

        # Open .yaml file
        if not os.path.isfile(file):
            exit_error(f"Recipe file {file!r} not found")

        with open(file) as f:
            try:
                data = yaml.load(f, Loader=RecipeLoader)

            except yaml.YAMLError as e:
                exit_error(f"Invalid recipe file {file!r}:\n{e}")

        return data

    def validate_minimum_version_required(self, data: dict) -> None:
        """Corroborates the minimum version required is met if the `.yaml`
        recipe file contains a `minimum_required_version` key.

        Args:
            data (dict): Recipe file data.
        """
        if not isinstance(data, dict):
            exit_error(
                f"Recipe file {self.file!r} is empty or is not a valid recipe"
            )

        if data.get(self.MINIMUM_REQUIRED_VERSION_KEY) is not None:
            minimum_required_version = Version(
                str(data["minimum_required_version"])
            )

            if not self.PACKAGE_VERSION >= minimum_required_version:  # noqa: SIM300
                exit_error(
                    f"This recipe requires recp >= {minimum_required_version}"
                    f" but current recp version is {self.PACKAGE_VERSION}"
                )

    def validate_keys(self, data: dict) -> None:
        """Validate keys present in the recipe `.yaml` file.

        Args:
            data (dict): Recipe `.yaml` file data.
        """
        # Check 'recipe' key exists
        if self.ROOT_KEY not in data:
            exit_error(f"Key {self.ROOT_KEY!r} not found in recipe file")

        if not isinstance(data[self.ROOT_KEY], dict):
            exit_error(f"Key {self.ROOT_KEY!r} should contain at least a step")

        # Check recipe-level env
        if (
            data.get(self.ENV_KEY) is not None
            and not isinstance(data[self.ENV_KEY], dict)
        ):
            exit_error(f"Key {self.ENV_KEY!r} should be a dict of variables")

        # Check step keys
        for name, step in data[self.ROOT_KEY].items():
            if not isinstance(step, dict):
                exit_error(f"Step {name!r} should be a dict")

            for mandatory_key in self.MANDATORY_STEP_KEYS:
                if mandatory_key not in step:
                    exit_error(
                        f"Key {mandatory_key!r} not found in step {name!r}"
                    )

            if (
                step.get("env") is not None
                and not isinstance(step["env"], dict)
            ):
                exit_error(f"Key 'env' of step {name!r} should be a dict")

            if step.get("parallel") is not None and not (
                step["parallel"] == "auto"
                or (
                    isinstance(step["parallel"], int)
                    and not isinstance(step["parallel"], bool)
                    and step["parallel"] >= 1
                )
            ):
                exit_error(
                    f"Key 'parallel' of step {name!r} should be a positive "
                    "integer or 'auto'"
                )

            # Check commands
            for cmd_idx, cmd in enumerate(make_list(step["run"]) or []):
                if isinstance(cmd, dict):
                    if "cmd" not in cmd:
                        exit_error(
                            f"Key 'cmd' not found in command #{cmd_idx} of "
                            f"step {name!r}"
                        )

                    if cmd.get("label") is not None and not isinstance(
                        cmd["label"], str | int | float
                    ):
                        exit_error(
                            f"Key 'label' in command #{cmd_idx} of step "
                            f"{name!r} should be a str"
                        )

                    if not all(
                        isinstance(p, str)
                        for p in make_list(cmd.get("skip_if_exists")) or []
                    ):
                        exit_error(
                            f"Key 'skip_if_exists' in command #{cmd_idx} of "
                            f"step {name!r} should be a str or a list of str"
                        )

                    for modifier in make_list(cmd.get("apply")) or []:
                        if (
                            not isinstance(modifier, dict)
                            or "fn" not in modifier
                        ):
                            exit_error(
                                f"Modifiers in command #{cmd_idx} of step "
                                f"{name!r} should be a dict with a 'fn' key"
                            )

                elif not isinstance(cmd, str):
                    exit_error(
                        f"Command #{cmd_idx} of step {name!r} is of type "
                        f"{cmd.__class__.__name__!r}, but only str or dict "
                        "commands are supported"
                    )

    def filter_by_tag(self, data: dict, tag: str | list[str]) -> dict:
        """Filter steps by a given tag.

        Args:
            data (dict): Recipe `.yaml` file data.
            tag (str | list[str]): Tag(s) to select. Values not containing any
                tag in the list are removed from the resulting `dict`.

        Returns:
            (dict): Resulting `.yaml` recipe filtered after selecting steps by
                tag.
        """
        selected_steps = []

        for name in data["recipe"]:
            step_tags = data["recipe"][name].get("tag", [])

            if all(t in step_tags for t in tag):
                selected_steps.append(name)

        data["recipe"] = {
            k: v for k, v in data["recipe"].items() if k in selected_steps
        }

        return data

    def filter_by_step(
            self,
            data: dict,
            step: list[str] | None = None,
            from_step: str | None = None
    ) -> dict:
        """Filter steps by name.

        Args:
            data (dict): Recipe `.yaml` file data.
            step (list[str] | None): Name(s) of the steps to select.
            from_step (str | None): Name of the step to start from. This step
                and all steps after it are selected.

        Returns:
            (dict): Resulting `.yaml` recipe filtered after selecting steps by
                name.
        """
        all_steps = list(self._data["recipe"])

        for name in (step or []) + ([from_step] if from_step else []):
            if name not in all_steps:
                exit_error(
                    f"Step {name!r} not found in recipe. Available steps are: "
                    + ", ".join(f"{s!r}" for s in all_steps)
                )

        if step is not None:
            selected_steps = step

        else:
            selected_steps = all_steps[all_steps.index(from_step):]

        data["recipe"] = {
            k: v for k, v in data["recipe"].items() if k in selected_steps
        }

        return data

    def _solve_env(self, env: dict, name: str) -> dict:
        """Solves the `!input` and `!prompt` constructors in an `env` key.

        Args:
            env (dict): Environment variables.
            name (str): Name of the step owning `env`, used in error messages.

        Returns:
            (dict): Environment variables after solving all constructors.
        """
        for k, v in env.items():
            # !input constructor
            if (
                isinstance(v, dict)
                and v.get("__constructor__") == "!input"
            ):
                if (var := os.environ.get(v["name"])) is None:
                    if v.get("required"):
                        exit_error(
                            f"Environmental variable {v['name']!r} is "
                            f"marked in {name!r} as required but "
                            "was not provided"
                        )

                    else:
                        env[k] = v.get("default")

                else:
                    env[k] = var

            # !prompt constructor
            if (
                isinstance(v, dict)
                and v.get("__constructor__") == "!prompt"
            ):
                if v["choices"] is not None:
                    # Check default is valid if any
                    if v["default"] is not None:
                        if v["default"] not in v["choices"]:
                            exit_error(
                                f"default choice {v['default']!r} of "
                                f"{k!r} in {name!r} not found in choices"
                            )

                        choices_repr = [
                            c if c != v["default"] else f"*{c}"
                            for c in v["choices"]
                        ]
                        choices_repr =\
                            " [" + "/".join(choices_repr) + "]"

                    else:
                        choices_repr =\
                            " [" + "/".join(v["choices"]) + "]"

                    while True:
                        choice = self._input(
                            f"{v['message']}{choices_repr}: ",
                            default=v["default"],
                            var=k
                        )

                        if choice == "" and v["default"] is not None:
                            choice = v["default"]

                        if choice in v["choices"]:
                            env[k] = choice
                            break

                else:
                    if v.get("default") is not None:
                        response = self._input(
                            f"{v['message']} [*{v['default']}]: ",
                            default=v["default"],
                            var=k
                        )

                        env[k] = (
                            v['default'] if response == ""
                            else response
                        )

                    else:
                        env[k] = self._input(f"{v['message']}: ", var=k)

        return env

    def _input(
            self,
            message: str,
            var: str,
            default: str | None = None
    ) -> str:
        """Prompts the user for a value. Leading and trailing spaces are
        removed from the response.

        Args:
            message (str): Message displayed to the user.
            var (str): Name of the variable being prompted.
            default (str | None): Value returned if there is no terminal to
                prompt the user.

        Returns:
            (str): User response.
        """
        try:
            return input(message).strip()

        except EOFError:
            if default is not None:
                print(default)
                return default

            print()
            exit_error(
                f"Could not prompt a value for {var!r} because no input is "
                "available"
            )

    def parse_env(self, data: dict) -> dict:
        """Parse `env` environment key.

        Args:
            data (dict): Recipe `.yaml` file data.

        Returns:
            (dict): Resulting recipe `.yaml` data after solving all
                environmental variables in the `env` key.
        """
        # Recipe-level variables are shared by all steps
        recipe_env = self._solve_env(
            data.get(self.ENV_KEY) or {},
            name=self.ENV_KEY
        )

        for step_name, step in data["recipe"].items():
            env = self._solve_env(step.get("env") or {}, name=step_name)
            step["env"] = {**recipe_env, **env}

        return data

    def parse_run(self, data: dict) -> dict:
        """Parse `run` commands key.

        Args:
            data (dict): Recipe `.yaml` file data.

        Returns:
            (dict): Resulting recipe `.yaml` data after commands.
        """
        for step_name, step in data["recipe"].items():
            cmd_seq = []

            with temp_env(step.get("env", {})):
                # 'run' should be a list of commands
                for cmd_idx, cmd in enumerate(step["run"]):
                    if isinstance(cmd, str):
                        cmd_seq.append({
                            "cmd": self.expandall_recursive(cmd),
                            "label": "",
                            "skip_if_exists": []
                        })

                    elif isinstance(cmd, dict):
                        # NOTE: The command, its label and its skip_if_exists
                        # paths are joined so that modifiers replace the same
                        # tokens in all of them
                        skip_paths = make_list(cmd.get("skip_if_exists")) or []
                        label = str(cmd.get("label") or "")
                        cmd_list = [
                            self.expandall_recursive(
                                self.CMD_SEPARATOR.join(
                                    [str(cmd["cmd"]), label, *skip_paths]
                                )
                            )
                        ]
                        modifiers = make_list(cmd.get("apply")) or []

                        for modifier in modifiers:
                            fn = self._apply_registry.get(modifier["fn"], None)

                            if fn is None:
                                exit_error(
                                    f"Function {modifier['fn']!r} applied in "
                                    f"command #{cmd_idx} of step {step_name!r}"
                                    " not found"
                                )

                            # Solve modifier env variables
                            args = modifier.get("args") or {}
                            modifier["args"] = {
                                k: self.expandall_recursive(v)
                                for k, v in args.items()
                            }

                            try:
                                cmd_list = fn(cmd_list, **modifier["args"])

                            except TypeError as e:
                                exit_error(
                                    f"Invalid arguments for function "
                                    f"{modifier['fn']!r} applied in command "
                                    f"#{cmd_idx} of step {step_name!r}: {e}"
                                )

                        for expanded_cmd in cmd_list:
                            cmd_str, label, *skip_paths = expanded_cmd.split(
                                self.CMD_SEPARATOR
                            )
                            cmd_seq.append({
                                "cmd": cmd_str,
                                "label": label,
                                "skip_if_exists": skip_paths
                            })

                step["run"] = cmd_seq

        return data

    def _export_env(self, env: dict) -> dict:
        """Returns the environment passed to the commands of a step.

        Args:
            env (dict): Step environment variables.

        Returns:
            (dict): Current environment updated with the step variables.
        """
        with temp_env(env):
            return {
                **os.environ,
                **{
                    k: self.expandall_recursive(os.environ[k])
                    for k in env
                }
            }

    def run(
            self,
            tag: tuple[str] | None = None,
            step: list[str] | None = None,
            from_step: str | None = None,
            ignore_errors: bool = False,
            dry_run: bool = False,
            jobs: int | None = None,
            output: str = "auto",
            keep_runs: int = 20
    ) -> int:
        """Run all processed commands in a recipe `.yaml` file.

        Args:
            tag (tuple[str]): Tag(s) to select.
            step (list[str] | None): Name(s) of the steps to run.
            from_step (str | None): Name of the step to start from.
            ignore_errors (bool): If `True`, steps producing errors will not
                stop the execution of subsequent steps.
            dry_run (bool): If `True`, commands to be run are only displayed
                and not run.
            jobs (int | None): If given, overrides the number of commands run
                in parallel in steps with a `parallel` key.
            output (str): How the output of parallel steps is shown. One of
                `auto`, `board`, `grouped` or `prefix`.
            keep_runs (int): Number of runs whose parallel command logs are
                kept.

        Returns:
            (int): Exit code. `0` if all commands succeeded.
        """
        returncode = 1

        try:
            returncode = self._run(
                tag=tag,
                step=step,
                from_step=from_step,
                ignore_errors=ignore_errors,
                dry_run=dry_run,
                jobs=jobs,
                output=resolve_output_mode(output),
                keep_runs=keep_runs
            )
            return returncode

        except KeyboardInterrupt:
            returncode = 130
            raise

        finally:
            if self._run_store is not None:
                self._run_store.finish(returncode)
                self._run_store = None

    def _run(
            self,
            tag: tuple[str] | None,
            step: list[str] | None,
            from_step: str | None,
            ignore_errors: bool,
            dry_run: bool,
            jobs: int | None,
            output: str,
            keep_runs: int
    ) -> int:
        """Implements `run`, see its arguments."""
        # ----------------------------------------------------------------------
        # SECTION: INPUT
        # ----------------------------------------------------------------------
        # Copy original data
        print(
            f"{style('Using', 'b', 'green')} recipe "
            f"{style(repr(self.file), 'cyan')} ..."
        )
        data = deepcopy(self._data)
        print(style(f"{len(data['recipe'])} step(s) found", "dim"))

        # ----------------------------------------------------------------------
        # SECTION: TEXT PROCESSING
        # ----------------------------------------------------------------------
        print(style("Pre-processing recipe data ...", "dim"))
        # Stringify tags, descriptions and commands
        for step_data in data["recipe"].values():
            if "tag" in step_data:
                step_data["tag"] = [
                    str(t) for t in make_list(step_data["tag"]) or []
                ]

            if "description" in step_data:
                step_data["description"] = str(step_data["description"])

            step_data["run"] = make_list(step_data["run"]) or []

        print(style("Recipe pre-processing successfully completed", "dim"))

        # ----------------------------------------------------------------------
        # SECTION: FILTERING
        # ----------------------------------------------------------------------
        # Filter by tag
        if tag is not None:
            print(style("Filtering recipe steps by tags ...", "dim"))
            data = self.filter_by_tag(data, tag)
            print(style("Filtering by tags successfully completed", "dim"))

        # Filter by step name
        if step is not None or from_step is not None:
            print(style("Filtering recipe steps by name ...", "dim"))
            data = self.filter_by_step(
                data,
                step=step,
                from_step=from_step
            )
            print(style("Filtering by name successfully completed", "dim"))

        # ----------------------------------------------------------------------
        # SECTION: CONSTRUCTOR PROCESSING
        # ----------------------------------------------------------------------
        # NOTE: Processed here to only process the filtered steps
        print(style("Parsing step environments ...", "dim"))
        data = self.parse_env(data)
        print(
            style("Step environments processing successfully completed", "dim")
        )

        # ----------------------------------------------------------------------
        # SECTION: RESOLVE COMMANDS
        # ----------------------------------------------------------------------
        print(style("Pre-processing recipe commands ...", "dim"))
        data = self.parse_run(data)
        print(style("Recipe commands successfully completed", "dim"))

        # ----------------------------------------------------------------------
        # SECTION: RUN COMMANDS
        # ----------------------------------------------------------------------
        num_steps = len(data["recipe"])
        completed_steps = []
        failed_steps = []

        if dry_run:
            print(
                f"{style('Running', 'b', 'green')} commands in "
                f"{style('DRY RUN MODE', 'b', 'warning')} ..."
            )

        else:
            print(f"{style('Running', 'b', 'green')} commands ...")

        for step_idx, (step_name, step_data) in enumerate(
            data["recipe"].items()
        ):
            progress_repr = f"[{step_idx + 1}/{num_steps}]"
            indent = " " * (len(progress_repr) + 1)
            print(
                f"{style(progress_repr, 'dim')} "
                f"{style('Running', 'b', 'green')} step "
                f"{style(repr(step_name), 'b', 'cyan')} ..."
            )

            if step_data.get("tag") is not None:
                tags_repr = ", ".join(f"{t!r}" for t in step_data["tag"])
                print(f"{indent}{style('Tags:'.ljust(13), 'dim')}{tags_repr}")

            if step_data.get("description") is not None:
                print(
                    f"{indent}{style('Description:'.ljust(13), 'dim')}"
                    f"{step_data['description']}".rstrip("\n")
                )

            if step_data.get("cwd") is not None:
                with temp_env(step_data["env"]):
                    cwd = self.expandall_recursive(str(step_data["cwd"]))
                    print(
                        f"{indent}{style('CWD:'.ljust(13), 'dim')}"
                        f"{style(cwd, 'cyan')}"
                    )

            else:
                cwd = None

            num_jobs = self._get_num_jobs(step_data, jobs=jobs)

            if num_jobs > 1:
                print(
                    f"{indent}{style('Parallel:'.ljust(13), 'dim')}"
                    f"{num_jobs} commands at a time"
                )

            env = self._export_env(step_data["env"])

            # Skip commands whose outputs already exist
            cmds = []
            labels = []

            for cmd in step_data["run"]:
                if self._outputs_exist(cmd["skip_if_exists"], cwd=cwd):
                    label = "Skipped:"

                elif dry_run:
                    label = "Command:"

                else:
                    cmds.append(cmd["cmd"])
                    labels.append(cmd["label"])
                    continue

                print(
                    f"{indent}{style(label.ljust(13) + cmd['cmd'], 'dim')}"
                )

            if dry_run:
                continue

            if cwd is not None and not os.path.isdir(cwd):
                print_error(f"CWD {cwd!r} not found", indent=indent)
                returncodes = [1]

            elif num_jobs > 1:
                returncodes = self._run_parallel(
                    cmds,
                    labels=labels,
                    step_name=step_name,
                    cwd=cwd,
                    env=env,
                    indent=indent,
                    num_jobs=num_jobs,
                    output=output,
                    keep_runs=keep_runs,
                    ignore_errors=ignore_errors
                )

            else:
                returncodes = self._run_sequential(
                    cmds,
                    cwd=cwd,
                    env=env,
                    indent=indent,
                    ignore_errors=ignore_errors
                )

            failed_returncodes = [rc for rc in returncodes if rc != 0]

            if len(failed_returncodes) == 0:
                completed_steps.append(step_name)
                continue

            failed_steps.append(step_name)

            if not ignore_errors:
                self.print_summary(
                    data,
                    completed_steps=completed_steps,
                    failed_steps=failed_steps
                )
                print_hint(
                    f"To resume, run the recipe again with --from {step_name}"
                )
                returncode = failed_returncodes[0]
                return returncode if returncode > 0 else 1

        if not dry_run:
            self.print_summary(
                data,
                completed_steps=completed_steps,
                failed_steps=failed_steps
            )

        return 1 if failed_steps else 0

    def _get_num_jobs(self, step: dict, jobs: int | None = None) -> int:
        """Returns the number of commands of a step run in parallel.

        Args:
            step (dict): Step data.
            jobs (int | None): If given, overrides the `parallel` key of the
                step, if any.

        Returns:
            (int): Number of commands run in parallel.
        """
        if step.get("parallel") is None:
            return 1

        if jobs is not None:
            return jobs

        if step["parallel"] == "auto":
            return os.cpu_count() or 1

        return step["parallel"]

    def _outputs_exist(self, paths: list[str], cwd: str | None) -> bool:
        """Checks if all outputs of a command exist.

        Args:
            paths (list[str]): Outputs of the command. Relative paths are
                resolved from `cwd`.
            cwd (str | None): Folder where the command is run.

        Returns:
            (bool): `True` if `paths` is not empty and all paths exist.
        """
        if len(paths) == 0:
            return False

        return all(
            os.path.exists(os.path.join(cwd or "", path)) for path in paths
        )

    def _run_sequential(
            self,
            cmds: list[str],
            cwd: str | None,
            env: dict,
            indent: str,
            ignore_errors: bool = False
    ) -> list[int]:
        """Runs commands one after another.

        Args:
            cmds (list[str]): Commands to run.
            cwd (str | None): Folder where the commands are run.
            env (dict): Environment variables passed to the commands.
            indent (str): Indentation used when printing.
            ignore_errors (bool): If `True`, commands are run even after a
                command fails.

        Returns:
            (list[int]): Exit code of each command that was run.
        """
        returncodes = []

        for cmd in cmds:
            print(f"{indent}{style('Command:'.ljust(13) + cmd, 'dim')}")

            # Keep recp and command outputs in order when redirected
            sys.stdout.flush()
            returncode = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                env=env
            ).returncode
            returncodes.append(returncode)

            if returncode != 0:
                print_error(
                    f"Command failed with exit code {returncode}",
                    indent=indent
                )

                if not ignore_errors:
                    break

        return returncodes

    def _run_parallel(
            self,
            cmds: list[str],
            labels: list[str],
            step_name: str,
            cwd: str | None,
            env: dict,
            indent: str,
            num_jobs: int,
            output: str = "grouped",
            keep_runs: int = 20,
            ignore_errors: bool = False
    ) -> list[int]:
        """Runs commands in parallel. The output of each command is saved to
        a log file, and shown as described in `ParallelRunner`.

        Args:
            cmds (list[str]): Commands to run.
            labels (list[str]): Label of each command. Empty labels are
                inferred from the commands.
            step_name (str): Name of the step.
            cwd (str | None): Folder where the commands are run.
            env (dict): Environment variables passed to the commands.
            indent (str): Indentation used when printing.
            num_jobs (int): Maximum number of commands run at the same time.
            output (str): One of `board`, `grouped` or `prefix`.
            keep_runs (int): Number of runs whose logs are kept.
            ignore_errors (bool): If `True`, commands are run even after a
                command fails. Otherwise, no new commands are started after a
                failure, but running commands are allowed to finish.

        Returns:
            (list[int]): Exit code of each command that was run.
        """
        if len(cmds) == 0:
            return []

        store = self._get_run_store(keep_runs=keep_runs)
        inferred_labels = infer_labels(cmds)
        first_id = store.next_id if store is not None else 1
        jobs = [
            Job(
                id=first_id + i,
                cmd=cmd,
                label=label or inferred_label,
                log_file=(
                    store.log_file(first_id + i) if store is not None
                    else None
                )
            )
            for i, (cmd, label, inferred_label) in enumerate(
                zip(cmds, labels, inferred_labels, strict=True)
            )
        ]

        def save_job(job: Job) -> None:
            store.update(job, step=step_name)

        if store is not None:
            store.next_id += len(jobs)
            print(
                f"{indent}{style('Logs:'.ljust(13), 'dim')}"
                f"{style(store.dir, 'cyan')}"
            )

            for job in jobs:
                save_job(job)

        sys.stdout.flush()
        runner = ParallelRunner(
            jobs,
            cwd=cwd,
            env=env,
            num_jobs=num_jobs,
            indent=indent,
            mode=output,
            title=step_name,
            ignore_errors=ignore_errors,
            on_change=save_job if store is not None else None
        )
        return runner.run()

    def _get_run_store(self, keep_runs: int) -> RunStore | None:
        """Returns the store for the logs of parallel commands of this run.

        Args:
            keep_runs (int): Number of runs whose logs are kept.

        Returns:
            (RunStore | None): Run store, or `None` if it cannot be created.
        """
        if self._run_store is None:
            try:
                self._run_store = RunStore(
                    recipe_file=self.file,
                    keep=keep_runs
                )

            except OSError as e:
                print_warning(f"Command logs will not be saved: {e}")

        return self._run_store

    @staticmethod
    def _describe_env(env: dict) -> str:
        """Returns a description of the variables of an `env` key.

        Args:
            env (dict): Environment variables.

        Returns:
            (str): Comma-separated variable names, indicating which ones are
                set by the user with `!input` or `!prompt`.
        """
        names = []

        for k, v in env.items():
            if isinstance(v, dict) and v.get("__constructor__") == "!input":
                required = ", required" if v.get("required") else ""
                names.append(f"{k} (input: {v['name']}{required})")

            elif isinstance(v, dict) and v.get("__constructor__") == "!prompt":
                names.append(f"{k} (prompt)")

            else:
                names.append(k)

        return ", ".join(names)

    def show(self) -> None:
        """Prints the steps of the recipe without running anything."""
        data = self._data
        label_width = 13
        print(
            f"{style('Recipe', 'b', 'green')} "
            f"{style(repr(self.file), 'cyan')}"
        )

        if data.get(self.MINIMUM_REQUIRED_VERSION_KEY) is not None:
            print(
                f"{style('Requires:'.ljust(label_width), 'dim')}"
                f"recp >= {data[self.MINIMUM_REQUIRED_VERSION_KEY]}"
            )

        if data.get(self.ENV_KEY):
            print(
                f"{style('Env:'.ljust(label_width), 'dim')}"
                f"{self._describe_env(data[self.ENV_KEY])}"
            )

        num_steps = len(data["recipe"])

        for step_idx, (step_name, step) in enumerate(data["recipe"].items()):
            progress_repr = f"[{step_idx + 1}/{num_steps}]"
            indent = " " * (len(progress_repr) + 1)
            print(
                f"{style(progress_repr, 'dim')} "
                f"{style(repr(step_name), 'b', 'cyan')}"
            )
            fields = {
                "Tags:": ", ".join(
                    f"{str(t)!r}" for t in make_list(step.get("tag")) or []
                ),
                "Description:": str(step.get("description") or "").strip(),
                "Env:": self._describe_env(step.get("env") or {}),
                "CWD:": str(step.get("cwd") or ""),
                "Parallel:": str(step.get("parallel") or ""),
                "Commands:": str(len(make_list(step["run"]) or []))
            }

            for label, value in fields.items():
                if value != "":
                    print(
                        f"{indent}{style(label.ljust(label_width), 'dim')}"
                        f"{value}"
                    )

    def print_summary(
            self,
            data: dict,
            completed_steps: list[str],
            failed_steps: list[str]
    ) -> None:
        """Prints a summary of the steps that were run.

        Args:
            data (dict): Recipe `.yaml` file data.
            completed_steps (list[str]): Steps whose commands all succeeded.
            failed_steps (list[str]): Steps with at least one failed command.
        """
        num_not_run = (
            len(data["recipe"]) - len(completed_steps) - len(failed_steps)
        )
        summary_color = "error" if failed_steps else "green"
        print(
            f"{style('Summary:', 'b', summary_color)} "
            f"{len(completed_steps)} step(s) completed, "
            f"{len(failed_steps)} failed, {num_not_run} not run"
        )

        if failed_steps:
            print_error(
                "Failed step(s): " + ", ".join(f"{s!r}" for s in failed_steps)
            )
