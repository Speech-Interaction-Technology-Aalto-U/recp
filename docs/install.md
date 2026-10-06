# Installation

## Install with uv (recommended)
`recp` is a command-line tool, so it is best installed as a [`uv` tool](https://docs.astral.sh/uv/concepts/tools/). This installs it in its own isolated environment and makes the `recp` command available everywhere. If you don't have `uv` yet, follow the <a href="https://docs.astral.sh/uv/getting-started/installation/" target="_blank">`uv` installation instructions</a> for your operating system.

Then run:

```
uv tool install recp
```

To verify the installation, run:

```
recp --version
```

This should output:

```text
recp version x.y.z yyyy-zzzz developed by Esteban Gómez (Speech Interaction Technology, Aalto University)
```

Where:

- `x.y.z` represents the major, minor, and patch version.
- `yyyy-zzzz` indicates the development start year and the current year.

To upgrade `recp` to the latest version, run:

```
uv tool upgrade recp
```

`recp` can also be run once without installing it, using `uvx`:

```
uvx recp --version
```

## Install with pip
Alternatively, `recp` can be installed into the current Python environment with `pip`:

```
pip install recp
```

## What's next
Now that you have installed `recp`, check the [Quickstart](quickstart.md) section to begin using it.
