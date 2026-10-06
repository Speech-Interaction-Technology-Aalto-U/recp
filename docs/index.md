---
hide:
  - navigation
  - toc
---

<div class="recp-hero">
<div>
<span class="recp-hero__eyebrow"><img src="assets/logo.svg" alt="">recp</span>
<h1>Command-line pipelines defined in YAML</h1>
<p class="recp-hero__lede"><code>recp</code> runs recipes: <code>.yaml</code> files that group shell commands into steps. Commands can be generated from templates, take values from environment variables or prompts, run in parallel and skip outputs that already exist.</p>
<div class="recp-hero__actions">
<a class="md-button md-button--primary" href="quickstart/">Quickstart</a>
<a class="md-button" href="reference/">Reference</a>
</div>

<div class="highlight"><pre><span></span><code>uv tool install recp</code></pre></div>

</div>
<div class="recp-hero__output">
<div class="highlight"><span class="filename">recp run evaluate.yaml -j 2</span><pre><span></span><code>[1/1] Running step &#x27;infer&#x27; ...
      Parallel:    2 commands at a time
      Command:     #1  --dataset clean  done in 03:12 [1/4]
Processing: 100%|██████████| 800/800
Saved 800 files to out/clean
──────────────────────────────────────────────────────────────────
 infer  1 done · 2 running · 1 queued · 0 failed             04:07
 #  Status     Time     Label              Last line
 1  Done       03:12    --dataset clean
 2  Running    04:07    --dataset noisy    Processing:  58%| 464/800
 3  Running    00:55    --dataset reverb   Processing:  13%| 104/800
 4  Queued     -        --dataset music
──────────────────────────────────────────────────────────────────</code></pre></div>

</div>
</div>

<div class="grid cards recp-cards" markdown>

-   :material-file-code-outline: **Steps**

    ---

    A recipe is a sequence of steps, each with its own commands, environment variables and working folder. Steps can be selected with `--tag` or `--step`, and a failed run can be resumed with `--from`.

-   :material-function-variant: **Modifiers**

    ---

    Modifiers expand one command into many before the recipe runs, e.g. one command per file with `dir_files` or per combination of values with `cartesian_product`.

-   :material-console-line: **Constructors**

    ---

    Constructors such as `!input`, `!prompt` and `!shell` set variables when the recipe is loaded, so the same recipe can be used with different data or settings.

-   :material-view-parallel-outline: **Parallel commands**

    ---

    Steps with a `parallel` key run several commands at a time. Their status is shown in a table while they run, and their output is saved for `recp status`, `recp log` and `recp follow`.

</div>

## About `recp`
`recp` (short for recipe) runs processes made of multiple command-line steps. A recipe is a `.yaml` file that lists the steps to run. Each step can have tags, a description, environment variables, a working folder and one or more commands. Commands can be pre-processed with modifiers, so that a single command template is expanded into many commands, e.g. one per file in a folder or one per combination of parameter values.

A recipe can contain many steps, and a subset of them can be selected by name or tag. The `--dry-run` option prints the commands without running them, and a failed run can be resumed from a given step with `--from`. Commands of a step can run in parallel, and commands whose outputs already exist can be skipped, which is useful when processing large datasets.

## Guides
To begin using `recp`, refer to the guides below:

- [Installation](install.md)
- [Quickstart](quickstart.md)

For a description of each feature, see the [Reference](reference.md).
