## Recipe structure
A recipe file with all available fields is shown below. Each field is described afterward.


```yaml title="recipe.yaml with all available fields"
minimum_required_version: 0.3.0

env:
  OUTPUT_DIR: ~/output

recipe:
  first_step:
    tag:
      - first

    description: >
        Description of the first step

    env:
        USER_NAME: !input
            name: MY_NAME
            default: Juhani
            required: false 

    cwd: $OUTPUT_DIR

    run:
        - echo 'Hello from recp'
        - cmd: echo "My name is $USER_NAME and today is {DAY}"
          apply:
            - fn: date
              args:
                token: "{DAY}"
                format: "%A"
```
A recipe file is a `.yaml` file where:

- `minimum_required_version` is an **optional** field specifying the minimum `recp` version required to run it.
- `env` is an **optional** field containing environmental variables shared by all steps. A step can override them in its own `env` key.
- `recipe` is the **required** root key containing the description of each step to be run.

Each step has:

- A **required** name key (`first_step`) containing the information relative to that particular step.
- An **optional** `tag` key containing a `str` or a `list` of `str`, each one corresponding to a tag that can be use to select a certain subset of steps to be run with the `--tag` option.
- An **optional** `description` key containing a `str` that describes that the step does. This is only for documentation purposes, and will be printed to the terminal when the recipe is run.
- An **optional** `env` key containing environmental variables to be used in that step. They are expanded in the commands and also passed to the processes run by the commands. The environmental variables of a specific step are isolated from all other steps. To share variables across steps you can use the recipe-level `env` key. Additionally, environmental variables can be defined directly in the `.yaml` file, or defined by the user when running the recipe. User defined variables can be configured using the `!input` constructor that has a mandatory `name` key, and an optional `default` key to define the default value, and an optional `required` key containing a `bool` value to specify whether that variable is required or optional.
- An **optional** `cwd` key containing the folder where the commands of that step are run.
- An **optional** `parallel` key containing the number of commands of that step run at the same time (see [Parallel commands](#parallel-commands)).
- A **required** `run` key that contains a `str` or a `list` of the commands to be run. A command can be a `str` or a `dict` containing the `cmd` key and the `apply` key containing a `list` of modifiers to be applied to that command as a pre-processing step to generate one or multiple commands. Each modifier is defined by a `fn` key with the modifier function name, and an `args` key with the corresponding arguments. A `dict` command can also contain a `skip_if_exists` key (see [Skipping existing outputs](#skipping-existing-outputs)).

Environmental variables such as `$HOME` or `$USER_NAME` are expanded by `recp` before the commands are run. Use `$$` to pass a literal `$` to the command instead. The `RECP_RECIPE_FILE` variable contains the absolute path to the recipe file being run.

A recipe can be run using:
```bash
recp run /path/to/your/recipe.yaml
```

Additionally, you can show the commands without running them with the `--dry-run` option, that can be used for debugging purposes.

```bash
recp run /path/to/your/recipe.yaml --dry-run 
```

To filter steps by tag, you can use:
```bash
recp run /path/to/your/recipe.yaml --tag first 
```

This will only collect steps containing the tag `first`. Multiple tags can be used to filter a step, in which case only steps containing all of them will be selected. 

To run only some steps by name, or to resume a recipe from a given step, you can use:
```bash
recp run /path/to/your/recipe.yaml --step first_step
recp run /path/to/your/recipe.yaml --from first_step
```

If a command fails, `recp` stops, prints a summary and exits with the exit code of the failed command. With the `--ignore-errors` option, the remaining commands are run anyway and `recp` exits with code `1` if any of them failed.

The output is colored only when printed to a terminal. Colors can be disabled by setting the `NO_COLOR` environment variable, or forced by setting `FORCE_COLOR`.

To see the steps of a recipe without running it or prompting for any value, you can use:
```bash
recp show /path/to/your/recipe.yaml
```

For further options on `recp run`, you can run:
```bash
recp run --help
```

## Constructors
A recipe `.yaml` file can be created using a certain set of custom constructors to facilitate expressing your commands.

### !input constructor
The `!input` constructor allows you to introduce user variables provided through the terminal into your recipe. It is typically used in the `env` key as exemplified below.

```yaml title="input_constructor_example.yaml"
minimum_required_version: 0.1.0

recipe:
  step:
    env:
      USER_VAR: !input
        name: USER_VAR
        default: default_value
        required: false
    run:
      - "echo 'print user variable: $USER_VAR'"
```

In this case:

- `name` is a **required** key with the name of the environmental variable to be provided by the user. This name can be the same as its parent key or different.
- `default` is an **optional** key. It sets the value to use if the user does not provide the variable.
- `required` is an **optional** key. If `true`, the user must provide the variable to run the recipe.

The recipe can be run as:
```bash
USER_VAR="Juhani" recp run /path/to/input_constructor_example.yaml
```

It will result in the following output:
```bash
Using recipe '/path/to/input_constructor_example.yaml' ...
1 step(s) found
Pre-processing recipe data ...
Recipe pre-processing successfully completed
Parsing step environments ...
Step environments processing successfully completed
Pre-processing recipe commands ...
Recipe commands successfully completed
Running commands ...
[1/1] Running step 'step' ...
      Command:     echo 'print user variable: Juhani'
print user variable: Juhani
Summary: 1 step(s) completed, 0 failed, 0 not run
```

### !prompt constructor

!!! info
    This constructor was introduced in version `0.1.2`, so update your `minimum_required_version` if that key is present.

The `!prompt` constructor works like `!input`, but instead of directly including the variable in your command, it creates a user prompt for entering a value or choice. It's usually used within the `env` key, as shown below.

```yaml title="prompt_constructor_example.yaml"
minimum_required_version: 0.1.2

recipe:
  step:
    env:
      USER_VAR: !prompt
        message: Introduce variable value
    run:
      - "echo 'print user variable: $USER_VAR'"
```

In this case `message` is a **required** key containing the message displayed to the user. You can run the recipe with:
```bash
recp run /path/to/prompt_constructor_example.yaml
```

The result will depend on what the user typed before pressing `enter`.
```bash
1 step(s) found
Pre-processing recipe data ...
Recipe pre-processing successfully completed
Parsing step environments ...
Introduce variable value: Juhani
Step environments processing successfully completed
Pre-processing recipe commands ...
Recipe commands successfully completed
Running commands ...
[1/1] Running step 'step' ...
      Command:     echo 'print user variable: Juhani'
print user variable: Juhani
Summary: 1 step(s) completed, 0 failed, 0 not run
```

Additionally, the input can be configured to be a set of choices:
```yaml title="prompt_constructor_example_choices.yaml"
minimum_required_version: 0.1.2

recipe:
  step:
    env:
      CHOICE: !prompt
        message: Favourite pet
        choices:
          - cat
          - dog
    run:
      - "echo 'You are a $CHOICE person'"
```

In this case, the user can only type one of the available choices. If they enter something else, the program will prompt them to select a valid choice again. For example, if you type `cat` and `press` enter, you will get the following output:
```bash
1 step(s) found
Pre-processing recipe data ...
Recipe pre-processing successfully completed
Parsing step environments ...
Favourite pet [cat/dog]: cat
Step environments processing successfully completed
Pre-processing recipe commands ...
Recipe commands successfully completed
Running commands ...
[1/1] Running step 'step' ...
      Command:     echo 'You are a cat person'
You are a cat person
Summary: 1 step(s) completed, 0 failed, 0 not run
```

Additionally, you can set a default choice using the `default` key:
```yaml title="prompt_constructor_example_choices_default.yaml"
minimum_required_version: 0.1.2

recipe:
  step:
    env:
      CHOICE: !prompt
        message: Favourite pet
        choices:
          - cat
          - dog
        default: cat
    run:
      - "echo 'You are a $CHOICE person'"
```

In this case, the option prefixed with a `*` in the prompt will be selected if the user presses enter without explicitly choosing another option.

Leading and trailing spaces are removed from the user response. If no input is available (e.g. when running in a batch job), the `default` value is used if there is one, otherwise `recp` stops with an error.

### !split constructor
The `!split` constructor splits a `str` by whitespace into a `list` of `str`. It is useful to pass multiple values to a modifier.

```yaml
recipe:
  step:
    run:
      - cmd: echo __NAME__
        apply:
          - fn: replace
            args:
              __NAME__: !split cat dog bird
```

### !lines constructor

!!! info
    This constructor was introduced in version `0.3.0`, so update your `minimum_required_version` if that key is present.

The `!lines` constructor reads a text file and returns a `list` with one item per line. Leading and trailing spaces are removed, and empty lines and lines starting with `#` are ignored. Relative paths are resolved from the folder where `recp` is run.

```yaml title="lines_constructor_example.yaml"
minimum_required_version: 0.3.0

recipe:
  step:
    run:
      - cmd: echo 'Processing speaker __SPEAKER__'
        apply:
          - fn: replace
            args:
              __SPEAKER__: !lines speakers.txt
```

### !shell constructor

!!! info
    This constructor was introduced in version `0.3.0`, so update your `minimum_required_version` if that key is present.

The `!shell` constructor runs a command when the recipe is loaded and returns its output as a `str`. The command is run even when using `--dry-run`.

```yaml title="shell_constructor_example.yaml"
minimum_required_version: 0.3.0

recipe:
  step:
    env:
      COMMIT: !shell git rev-parse --short HEAD
    run:
      - echo 'Current commit is $COMMIT'
```

### !now constructor

!!! info
    This constructor was introduced in version `0.3.0`, so update your `minimum_required_version` if that key is present.

The `!now` constructor returns the date and time when the recipe was loaded, using a `datetime` format (`%Y-%m-%d` by default). All `!now` constructors in a recipe use the same timestamp, so the value is consistent across steps.

```yaml title="now_constructor_example.yaml"
minimum_required_version: 0.3.0

env:
  RUN_ID: !now "%Y%m%d-%H%M"

recipe:
  step:
    run:
      - echo 'Saving results to results/$RUN_ID'
```

### !expr constructor
The `!expr` constructor allows using `python` expressions to be evaluated at runtime.

!!! warning
    This constructor uses `eval()` internally and is considered unsafe. By default, it is disabled, but you can enable it by using the `--unsafe` option when running the recipe.

This constructor can be used in any part of your recipe as follows:

```yaml title="expr_constructor_example.yaml"
minimum_required_version: 0.1.0

recipe:
  step:
    env:
      RESULT: !expr 24 * 60 * 60
    run:
      - echo 'A day has $RESULT seconds'
```

To run this recipe and enable the `!expr` constructor, you must use the `--unsafe` option
as follows:

```bash
recp run /path/to/expr_constructor_example.yaml --unsafe
```

It will result in the following output:
```bash
Using recipe '/path/to/expr_constructor_example.yaml' ...
1 step(s) found
Pre-processing recipe data ...
Recipe pre-processing successfully completed
Parsing step environments ...
Step environments processing successfully completed
Pre-processing recipe commands ...
Recipe commands successfully completed
Running commands ...
[1/1] Running step 'step' ...
      Command:     echo 'A day has 86400 seconds'
A day has 86400 seconds
Summary: 1 step(s) completed, 0 failed, 0 not run
```

## Modifiers
Modifiers are functions that take a command as input and transform it into one or more commands according to some logic. They can be used to write more compact recipes and to add variation or dynamic behavior to your commands.

To use a modifier, you can include then in the `run` key as follows:
```yaml title="modifier_example.yaml"
minimum_required_version: 0.1.0

recipe:
  step:
    run:
      - cmd: echo 'This message will be repeated multiple times'
        apply:
          - fn: repeat
            args:
              n: 3
```
In this case:

- The command in the `run` key is now a `dict`.
- The `apply` key contains all modifiers to be applied. It is a `list` where each item is a `dict` with a `fn` key (the modifier function) and an `args` key (the arguments passed to the modifier).
- When multiple modifiers are defined, they are applied sequentially: the output of one modifier becomes the input to the next.

In this example, the `repeat` modifier will be applied to the command, causing it to be run multiple times, resulting in:

```bash
Using recipe '/path/to/modifier_example.yaml' ...
1 step(s) found
Pre-processing recipe data ...
Recipe pre-processing successfully completed
Parsing step environments ...
Step environments processing successfully completed
Pre-processing recipe commands ...
Recipe commands successfully completed
Running commands ...
[1/1] Running step 'step' ...
      Command:     echo 'This message will be repeated multiple times'
This message will be repeated multiple times
      Command:     echo 'This message will be repeated multiple times'
This message will be repeated multiple times
      Command:     echo 'This message will be repeated multiple times'
This message will be repeated multiple times
Summary: 1 step(s) completed, 0 failed, 0 not run
```

!!! info
    The commands are unwrapped before being run, thus, you can use `--dry-run` the preview the commands that will be run after all modifiers are applied.

A list of supported modifiers is provided below. You can also implement your own by adding it to the `src/recp/utils/apply.py` file.

### basename
Replaces a token by the basename of a given path.

| Name     | Type   | Description                                |
|----------|--------|--------------------------------------------|
| `token`  | `str`  | Token to be replaced.                      |
| `path`   | `str`  | Path whose basename will be extracted.     |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'The file name is __NAME__'
        apply:
          - fn: basename
            args:
              token: __NAME__
              path: /path/to/file.txt
```

Result:
```bash
The file name is file.txt
```

### cartesian_product
Generates one command per combination of the values of all tokens.

| Name        | Type        | Description                                                                     |
|-------------|-------------|---------------------------------------------------------------------------------|
| `**kwargs`  | `List[str]` | Keyword arguments where each key is a token and each value is a list of values. |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'model __MODEL__ with seed __SEED__'
        apply:
          - fn: cartesian_product
            args:
              __MODEL__: [small, large]
              __SEED__: [0, 1]
```

Result:
```bash
model small with seed 0
model small with seed 1
model large with seed 0
model large with seed 1
```

### date
Replaces a token by a date in a specific format.

| Name     | Type   | Description                                | Default    |
|----------|--------|--------------------------------------------|------------|
| `token`  | `str`  | Token to be replaced.                      |            |
| `format` | `str`  | Date format using `datetime` convention.   | `%Y-%m-%d` |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'Today is __DATE__'
        apply:
          - fn: date
            args:
              token: __DATE__
              format: "%Y-%m-%d"
```

Result:
```bash
Today is 2026-01-06
```

### dir_files
Expands a command creating one copy per file in a given folder.

| Name        | Type                | Description                                           | Default |
|-------------|---------------------|-------------------------------------------------------|---------|
| `token`     | `str`               | Token to be replaced.                                 |         |
| `dir`       | `str`               | Input folder.                                         |         |
| `ext`       | `str | List[str]`   | Extension(s) to filter (e.g. `wav` or `.wav`, `*` includes all extensions). | `*`     |
| `recursive` | `bool`              | If `True`, `dir` is searched recursively.             | `True`  |
| `name_token` | `str`              | Token replaced by the file name (e.g. `file.wav`).    |         |
| `stem_token` | `str`              | Token replaced by the file name without extension (e.g. `file`). |         |
| `rel_token` | `str`               | Token replaced by the path relative to `dir` (e.g. `sub/file.wav`). |         |
| `rel_dir_token` | `str`           | Token replaced by the folder relative to `dir` (e.g. `sub`, or `.` for files directly in `dir`). |         |

Example:
```yaml
recipe:
  step:
    env:
      DIR: &dir /path/to/my/dir
    run:
      - cmd: echo '$DIR contains file __FILE__'
        apply:
          - fn: dir_files
            args:
              token: __FILE__
              dir: *dir
```

Result:
```bash
/path/to/my/dir contains file /path/to/my/dir/00_file.yaml
/path/to/my/dir contains file /path/to/my/dir/01_file.yaml
...
```

The optional tokens make it possible to build an output path from each input file. For example, to convert all `.wav` files in a folder to `.flac`, keeping the same subfolders:
```yaml
recipe:
  step:
    run:
      - cmd: mkdir -p out/__REL_DIR__ && ffmpeg -i __FILE__ out/__REL_DIR__/__STEM__.flac
        apply:
          - fn: dir_files
            args:
              token: __FILE__
              dir: corpus
              ext: wav
              stem_token: __STEM__
              rel_dir_token: __REL_DIR__
```

### index
Replaces a token by the command index value.

| Name     | Type  | Description                                                       | Default |
|----------|-------|-------------------------------------------------------------------|---------|
| `token`  | `str` | Token to replace.                                                 |         |
| `offset` | `int` | Offset applied to all values.                                     | `0`     |
| `zfill`  | `int` | Minimum width of the number, padded with leading zeros if needed. | `0`     |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'Command number __INDEX__'
        apply:
          - fn: repeat
            args:
              n: 3
          - fn: index
            args:
              token: __INDEX__
              zfill: 2
              offset: 1
```

Result:
```bash
Command number 01
Command number 02
Command number 03
```

### match
Replaces a token value based on a matching value of a given variable.

| Name        | Type        | Description                                |
|-------------|-------------|--------------------------------------------|
| `var`       | `str`       | Variable to match.                         |
| `token`     | `str`       | Token to be replaced.                      |
| `choices`   | `List[str]` | List of choices.                           |
| `values`    | `List[str]` | List of values (correlative to `choices`). |

Example:
```yaml
recipe:
  step:
    env:
      CHOICE: &choice second
    run:
      - cmd: echo 'The $CHOICE choice is __MATCH__'
        apply:
          - fn: match
            args:
              var: *choice
              token: __MATCH__
              choices: ["first", "second", "third"]
              values: ["bird", "cat", "dog"]
```

Result:
```bash
The second choice is cat
```

### parent_dir
Replaces a token by the path to the parent directory of a given path.

| Name     | Type   | Description                                      |
|----------|--------|--------------------------------------------------|
| `token`  | `str`  | Token to be replaced.                            |
| `path`   | `str`  | Path whose parent directory will be extracted.   |
| `n`      | `int`  | Repeat this function recursively `n` times.      |

Example:
```yaml
recipe:
  step:
    env:
      DIR: &dir /path/to/parent_dir/file.txt
    run:
      - cmd: echo 'The parent dir of $DIR is __PARENT_DIR__'
        apply:
          - fn: parent_dir
            args:
              token: __PARENT_DIR__
              path: *dir
```

Result:
```bash
The parent dir of /path/to/parent_dir/file.txt is /path/to/parent_dir
```

### randchoice
Picks a random choice from a list.

| Name      | Type            | Description                    |
|-----------|-----------------|--------------------------------|
| `token`   | `str`           | Token to replace.              |
| `choices` | `List[str]`     | List of `str` to choosen from. |
| `seed`    | `int | None`    | Random seed.                   |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'My pet is a __CHOICE__'
        apply:
          - fn: randchoice
            args:
              token: __CHOICE__
              choices: ["bird", "cat", "dog"]
```

Result:
```bash
My pet is a bird
```

### randint
Generates a random integer between `min` (included) and `max` (included).

| Name    | Type         | Description                            |
|---------|--------------|----------------------------------------|
| `token` | `str`        | Token to replace.                      |
| `min`   | `int`        | Minimum integer number to generate.    |
| `max`   | `int`        | Maximum integer number to generate.    |
| `seed`  | `int | None` | Random seed.                     |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'The lottery winner is the number __WINNER__'
        apply:
          - fn: randint
            args:
              token: __WINNER__
              min: 0
              max: 100
```

Result:
```bash
The lottery winner is the number 90
```

### randfloat
Generated a random float-point number within the `[min, max)` range.

| Name    | Type         | Description                                            |
|---------|--------------|--------------------------------------------------------|
| `token` | `str`        | Token to replace.                                      |
| `min`   | `int`        | Minimum floating-point number to generate (inclusive). |
| `max`   | `int`        | Maximum floating-point number to generate (exclusive). |
| `seed`  | `int | None` | Random seed.                                           |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'The generated floating-point number is __FLOAT__'
        apply:
          - fn: randfloat
            args:
              token: __FLOAT__
              min: 0.0
              max: 1.0
```

Result:
```bash
The generated floating-point number is 0.4770061600654977
```

### replace
Replace one or multiple tokens by a given value.

| Name        | Type   | Description                                                                        |
|-------------|--------|------------------------------------------------------------------------------------|
| `**kwargs`  | `str`  | Keyword arguments where each key is the a token and each value is the token value.<br>If a `list` of multiple values is passed, one command per value will be generated.   |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'The dog arrived first, and then the cat came'
        apply:
          - fn: replace
            args:
              dog: bird
              cat: fish
```

Result:
```bash
The bird arrived first, and then the fish came
```

Example (multiple values):
```yaml
recipe:
  step:
    run:
      - cmd: echo 'The dog arrived first, and then the cat came'
        apply:
          - fn: replace
            args:
              dog: [bird, lizard]
              cat: [fish, wizard]
```

Result:
```bash
The bird arrived first, and then the fish came
The lizard arrived first, and then the wizard came
```

### repeat
Repeats a command a given number of times.

| Name | Type   | Description                            |
|------|--------|----------------------------------------|
| `n`  | `int`  | Number of times to repeat the command. |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'I tend to repeat myself'
        apply:
          - fn: repeat
            args:
              n: 3
```

Result:
```bash
I tend to repeat myself
I tend to repeat myself
I tend to repeat myself
```

### run_if
Runs a command only if a variable matches a given value.

| Name    | Type   | Description                            |
|---------|--------|----------------------------------------|
| `var`   | `str`  | Number of times to repeat the command. |
| `value` | `str`  | Expected value to run the command.     |

Example:
```yaml
recipe:
  step:
    env:
      RUN: !prompt
        message: Run command?
        choices: ["y", "n"]
        default: "y"
    run:
      - cmd: echo 'The command has been executed'
        apply:
          - fn: run_if
            args:
              var: $RUN
              value: y
```

Result:
```bash
The command has been executed
```

### shard
Keeps only one shard of the commands, so that they can be split across multiple processes or jobs. Commands are assigned to shards in a round-robin fashion.

| Name    | Type  | Description                                        |
|---------|-------|----------------------------------------------------|
| `index` | `int` | Index of the shard to keep, from `0` to `num - 1`. |
| `num`   | `int` | Total number of shards.                            |

Example:
```yaml
recipe:
  step:
    run:
      - cmd: echo 'Processing file __FILE__'
        apply:
          - fn: dir_files
            args:
              token: __FILE__
              dir: corpus
          - fn: shard
            args:
              index: $SLURM_ARRAY_TASK_ID
              num: 20
```

When run as a SLURM array job with `sbatch --array=0-19`, each of the 20 jobs processes a different 1/20 of the files.

## Skipping existing outputs
A `dict` command can contain a `skip_if_exists` key with one or more paths. The command is skipped if all of them exist. The same tokens replaced by the modifiers in `cmd` are also replaced in `skip_if_exists`, so each generated command can point to its own output. Relative paths are resolved from the `cwd` of the step.

```yaml
recipe:
  step:
    run:
      - cmd: ffmpeg -i __FILE__ out/__STEM__.flac
        skip_if_exists: out/__STEM__.flac
        apply:
          - fn: dir_files
            args:
              token: __FILE__
              dir: corpus
              stem_token: __STEM__
```

If the recipe stops halfway through, running it again only processes the files that are missing. Skipped commands are shown as `Skipped:` in the output. Note that an output left incomplete by an interrupted command also counts as existing.

## Parallel commands
By default, the commands of a step are run one after another. The `parallel` key runs up to that number of commands of the step at the same time, or one per CPU core if set to `auto`. Steps are still run one after another.

```yaml
recipe:
  step:
    parallel: 8
    run:
      - cmd: ffmpeg -i __FILE__ out/__STEM__.flac
        apply:
          - fn: dir_files
            args:
              token: __FILE__
              dir: corpus
              stem_token: __STEM__
```

The output of each command is printed when it finishes, so the outputs of different commands are not mixed. If a command fails, no new commands are started, and `recp` stops once the running commands finish. With `--ignore-errors`, all commands are run.

The `--jobs` option overrides the `parallel` key of all steps that have one. For example, `--jobs 1` runs all commands one after another, which is useful for debugging.

## Recipe shortcuts
You can store frequently used recipes in a folder that `recp` reads automatically, and then refer to a recipe just by its name.

To add a new recipe shortcut this way, simply use:
```bash
recp config --add /path/to/your/custom_recipe.yaml
```

Then this recipe can be run as:
```bash
recp run custom_recipe
```

You can see the folder location and other `recp` settings by running:
```bash
recp config
```

To change the default recipes folder you can use:
```bash
recp config --set recipes.dir /path/to/your/new/recipes/folder
```

To list the recipes in the recipes folder, you can use:
```bash
recp list
```

## Editor support
A [JSON Schema](https://raw.githubusercontent.com/eagomez2/recp/main/recipe.schema.json) for recipe files is available. With the [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) for VS Code, or any editor using the YAML language server, it provides autocompletion and validation of recipe files. To enable it, add the following line at the top of your recipe:
```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/eagomez2/recp/main/recipe.schema.json
```

To avoid warnings about the `recp` constructors, add them to your VS Code settings:
```json
"yaml.customTags": [
  "!input mapping", "!input scalar", "!prompt mapping", "!expr scalar",
  "!split scalar", "!lines scalar", "!shell scalar", "!now scalar"
]
```