<p align="center">
  <img src="assets/logo.svg" alt="recp logo" width="160">
</p>

# Welcome to recp
`recp` (short for recipe) is a tool designed to automate processes that involve executing multiple sequential command-line steps. A recipe is defined in a `.yaml` file, which outlines the steps to be performed. Each step can include tags, a description, a set of environment variables to be set for that step, a working directory, and one or more commands to be executed. Additionally, commands can be preprocessed, allowing a single instruction to be expanded into multiple commands, thereby eliminating the need for tedious repeated and error-prone manual steps or scripts lacking flexibility.

A single recipe `.yaml` file can define multiple steps, which can be selected or filtered based on the task at hand. This flexibility allows you to execute only a subset of a larger recipe when needed. The `--dry-run` option enables generating the commands without actually running them, allowing you to verify that everything works as expected before executing time-consuming processes. If a step fails, the recipe can be resumed from that step with the `--from` option. Commands can also run in parallel and skip outputs that already exist, which is useful when processing large datasets.

## Guides
To begin using `recp`, refer to the guides below:

- [Installation](install.md)
- [Quickstart](quickstart.md)

For a more detailed description of individual features, see the [Reference](reference.md) section.
