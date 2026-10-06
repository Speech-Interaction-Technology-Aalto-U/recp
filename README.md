<p align="center">
  <img src="https://raw.githubusercontent.com/eagomez2/recp/main/docs/assets/logo.svg" alt="recp logo" width="160">
</p>

# `recp`: command-line pipelines defined in YAML
`recp` (short for recipe) runs processes made of multiple command-line steps. A recipe is a `.yaml` file that lists the steps to run. Each step can have tags, a description, environment variables, a working folder and one or more commands. Commands can be pre-processed with modifiers, so that a single command template is expanded into many commands, e.g. one per file in a folder or one per combination of parameter values.

A recipe can contain many steps, and a subset of them can be selected by name or tag. The `--dry-run` option prints the commands without running them, and a failed run can be resumed from a given step with `--from`. Commands of a step can run in parallel, and commands whose outputs already exist can be skipped, which is useful when processing large datasets.

While the commands of a parallel step run, `recp` shows a table with the status and last output line of each command. Their output is saved, so it can be read later or followed from another terminal:

```
recp run recipe.yaml --jobs 4                   # run up to 4 commands at a time in parallel steps
recp status                                     # status of the commands of the latest run
recp log 3                                      # output of command 3
recp follow 2                                   # stream the output of command 2 while it runs
```

# Installation
`recp` is best installed as a [`uv` tool](https://docs.astral.sh/uv/concepts/tools/):

```
uv tool install recp
```

It can also be installed with `pip`:

```
pip install recp
```

# Quickstart
See the [quickstart guide](https://eagomez2.github.io/recp/quickstart/).

# Documentation
The `recp` documentation is available [online](https://eagomez2.github.io/recp/). You can also build and view it locally by running:

```
uv run --extra docs mkdocs serve
```

# Cite
If `recp` contributed to your work, please consider citing it:

```bibtex
@misc{recp,
  author = {Esteban Gómez},
  title  = {recp},
  year   = 2026,
  url    = {https://github.com/eagomez2/recp}
}
```

# License
For further details about the license of this package, please see [LICENSE](LICENSE).
