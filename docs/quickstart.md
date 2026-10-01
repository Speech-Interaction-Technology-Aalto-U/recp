# Quickstart

If you haven't installed `recp` yet, please refer to our [Installation](install.md) guide before proceeding. This guide will help you get up and running with `recp`.

## Minimal recipe
`recp` works by parsing a **recipe file** file describing the steps you want to run. A **recip file** is a `.yaml` file with a defined structure. A minimal example is shown below:

```yaml title="minimal.yaml"
recipe:
  first_step:
    run:
      - echo "Hello, recp!"

  second_step:
    run:
      - python -c "from datetime import datetime; print('The current year is', datetime.now().year)"
```

In this example:

- `recipe` is the root key specifying your recipe.
- `first_step` and `second_step` are the steps of your recipe `.yaml` file. A recipe file can contain multilpe steps.
- `run` is the key specifying what commands are run for each step. A single step can have multiple commands.

To run this recipe, save it as `minimal.yaml` and run it as follows:
```bash
recp run /path/to/your/recipe/minimal.yaml
```

If you run it, you should see the following output:
```bash
Using recipe '/path/to/your/recipe/minimal.yaml' ...
2 step(s) found
Pre-processing recipe data ...
Recipe pre-processing successfully completed
Parsing step environments ...
Step environments processing successfully completed
Pre-processing recipe commands ...
Recipe commands successfully completed
Running commands ...
[1/2] Running step 'first_step' ...
      Command:     echo "Hello, recp!"
Hello, recp!
[2/2] Running step 'second_step' ...
      Command:     python -c "from datetime import datetime; print('The current year is', datetime.now().year)"
The current year is 2026
Summary: 2 step(s) completed, 0 failed, 0 not run
```

This output shows how your recipe file was parsed and then run step by step. So far it looks like a `.sh` would suffice to do this with less verbosity. However, `recp` offer many more options that make it stand out and be useful for automating more complex flows comprised of multiple steps.

## Additional features
Let's take our example one step further by adding some additional instructions to our `.yaml` recipe file:

```yaml title="minimal.yaml"
minimum_required_version: 0.1.0

recipe:
  first_step:
      env:
        YOUR_NAME: !input
          name: MY_NAME
          default: Juhani
      run:
        - echo "Hello, my name is $YOUR_NAME"
  
  second_step:
      run:
        - cmd: echo "The current year is {YEAR}"
          apply:
            - fn: date
              args:
                token: "{YEAR}"
                format: "%Y"
```

Here we can observe a few new features being introduced:


- `first_step` now has an `env` key. This lets you define environment variables for that step. We define `YOUR_NAME`, which reads from the `MY_NAME` environment variable. If `MY_NAME` is not set, `YOUR_NAME` defaults to `Juhani`. The `!input` directive allows capturing this variable from the terminal when the recipe is run using `recp`.   
In the `run` section, we use this variable as `$YOUR_NAME`. This shows how to capture and use environment variables.

- `second_step` now has an expanded command in the `run` key. The command is modified using the `apply` key. Modifiers are functions that take the command in `cmd` and process it to produce one or more new commands. There are many built-in modifiers, and you can also create your own. This lets you generate multiple commands automatically without writing each one manually

- There is a top level `minimum_required_version` that you can use to prevent running
your recipes with outdated `recp` versions.

To run this recipe, update your previous `minimal.yaml` file, and run it as follows:
```bash
MY_NAME="Olavi" recp run /path/to/your/recipe/minimal.yaml
```

You should see the following output:
```bash
Using recipe '/path/to/your/recipe/minimal.yaml' ...
2 step(s) found
Pre-processing recipe data ...
Recipe pre-processing successfully completed
Parsing step environments ...
Step environments processing successfully completed
Pre-processing recipe commands ...
Recipe commands successfully completed
Running commands ...
[1/2] Running step 'first_step' ...
      Command:     echo "Hello, my name is Olavi"
Hello, my name is Olavi
[2/2] Running step 'second_step' ...
      Command:     echo "The current year is 2026"
The current year is 2026
Summary: 2 step(s) completed, 0 failed, 0 not run
```

Here you can see that both steps run correctly and show the expected values. The environment variable `MY_NAME` and the date modifier are both replaced as intended. If `MY_NAME` is not set, the default value `Juhani` is used.

This is just a small glimpse of what `recp` can do. For further details about the structure of a `.yaml` recipe and the available modifiers, please go to the [Reference](reference.md) section.

## Example pipelines
The examples below show how the features of `recp` combine in typical pipelines. They can be used as a starting point for your own recipes.

### Processing a dataset file by file
This recipe resamples all `.wav` files of a corpus to 16 kHz, keeping the folder structure, and then extracts features from the result. Files that were already resampled are skipped, so the recipe can be run again after it stops or after new files are added to the corpus.

```yaml title="prepare_corpus.yaml"
minimum_required_version: 0.3.0

env:
  CORPUS_DIR: !input {name: CORPUS_DIR, required: true}
  OUTPUT_DIR: !input {name: OUTPUT_DIR, default: output}

recipe:
  resample:
    description: Resample all files to 16 kHz
    parallel: auto
    run:
      - cmd: mkdir -p $OUTPUT_DIR/16k/__REL_DIR__ && sox __FILE__ -r 16000 $OUTPUT_DIR/16k/__REL_DIR__/__STEM__.wav
        skip_if_exists: $OUTPUT_DIR/16k/__REL_DIR__/__STEM__.wav
        apply:
          - fn: dir_files
            args:
              token: __FILE__
              dir: $CORPUS_DIR
              ext: wav
              stem_token: __STEM__
              rel_dir_token: __REL_DIR__

  features:
    description: Extract features
    run:
      - python extract_features.py $OUTPUT_DIR/16k $OUTPUT_DIR/features
```

```bash
CORPUS_DIR=/data/corpus recp run prepare_corpus.yaml
```

### Running on a cluster
The same recipe can be split across the jobs of a SLURM array job with the `shard` modifier. Each job processes a different subset of the files:

```yaml
      - cmd: sox __FILE__ -r 16000 $OUTPUT_DIR/16k/__STEM__.wav
        apply:
          - fn: dir_files
            args:
              token: __FILE__
              dir: $CORPUS_DIR
              ext: wav
              stem_token: __STEM__
          - fn: shard
            args:
              index: $SLURM_ARRAY_TASK_ID
              num: 20
```

```bash
sbatch --array=0-19 --wrap "recp run prepare_corpus.yaml --step resample"
```

### Hyperparameter sweeps
This recipe trains every combination of models and seeds, and stores the results of each run in a folder named after the date and time when the recipe was started.

```yaml title="sweep.yaml"
minimum_required_version: 0.3.0

env:
  RUN_DIR: !now "runs/%Y%m%d-%H%M"
  COMMIT: !shell git rev-parse --short HEAD

recipe:
  train:
    run:
      - cmd: python train.py --model __MODEL__ --seed __SEED__ --output $RUN_DIR/__MODEL__-__SEED__ --commit $COMMIT
        apply:
          - fn: cartesian_product
            args:
              __MODEL__: [small, base, large]
              __SEED__: [0, 1, 2]

  evaluate:
    run:
      - python evaluate.py $RUN_DIR
```
