import os
import sys
import argparse
from datetime import datetime
from importlib.metadata import version
from ..utils.display import (
    exit_error,
    style
)
from ..utils.recipe import Recipe
from ..utils.config import PackageConfig
from ..utils.exceptions import RecpError


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="run command line tools recp",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False
    )
    subparser = parser.add_subparsers(dest="action")

    # Run parser
    run_parser = subparser.add_parser(
        "run",
        description="run recipes in .yaml format",
        help="run recipes in .yaml format",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False
    )
    run_parser.add_argument(
        "recipe",
        type=str,
        help="recipe .yaml file"
    )
    run_parser.add_argument(
        "-t", "--tag",
        nargs="*",
        type=str,
        help="include only steps matching a specific tag"
    )
    run_parser_step_group = run_parser.add_mutually_exclusive_group()
    run_parser_step_group.add_argument(
        "-s", "--step",
        nargs="+",
        type=str,
        help="run only the steps with the given name(s)"
    )
    run_parser_step_group.add_argument(
        "-f", "--from",
        dest="from_step",
        type=str,
        help="run the step with the given name and all steps after it"
    )
    run_parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="show the sequence of commands to be run without running them"
    )
    run_parser.add_argument(
        "--ignore-errors",
        action="store_true",
        help="ignore and skip steps that resulted in errors"
    )
    run_parser.add_argument(
        "--unsafe",
        action="store_true",
        help="enable unsafe !expr constructor in recipe files"
    )
    run_parser.add_argument(
        "-j", "--jobs",
        type=int,
        help="number of commands run at a time in steps with a 'parallel' key"
    )

    # Show parser
    show_parser = subparser.add_parser(
        "show",
        description="show the steps of a recipe without running it",
        help="show the steps of a recipe without running it",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False
    )
    show_parser.add_argument(
        "recipe",
        type=str,
        help="recipe .yaml file"
    )

    # List parser
    subparser.add_parser(
        "list",
        description="list the recipes in the recipes folder",
        help="list the recipes in the recipes folder",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False
    )

    # Config parser
    config_parser = subparser.add_parser(
        "config", # Show available recipes too
        description="configure recp",
        help="configure recp",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False
    )
    config_parser_option_group = config_parser.add_mutually_exclusive_group()
    config_parser_option_group.add_argument(
        "--set",
        type=str,
        nargs=2,
        help="set parameter",
    )
    config_parser_option_group.add_argument(
        "--add",
        type=str,
        help="add a recipe",
    )
    return parser


def resolve_recipe(recipe: str) -> str:
    """Returns the path to a recipe file. If `recipe` has no `.yaml` or `.yml`
    extension, it is searched by name in the recipes folder.

    Args:
        recipe (str): Recipe file or name.

    Returns:
        (str): Path to the recipe file.
    """
    if recipe.endswith((".yaml", ".yml")):
        return recipe

    config = PackageConfig(app_name="recp")
    file = config.find_recipe(recipe)

    if file is None:
        exit_error(
            f"Recipe {recipe!r} not found in recipes folder "
            f"{config.recipes_dir!r}"
        )

    return file


def main() -> None:
    try:
        _main()
    
    except (RecpError, FileNotFoundError) as e:
        exit_error(str(e))


def _main() -> None:
    # Version print
    if len(sys.argv) == 2 and sys.argv[1] in ("-v", "--version"):
        print(
            f"recp version {version('recp')} developed by Esteban Gómez 2025-"
            f"{datetime.now().year} (Speech Interaction Technology, Aalto "
            "University)"
        )
        sys.exit(0)
    
    # Parse args
    parser = get_parser()
    args = parser.parse_args()

    if args.action is None:
        parser.print_help()
        sys.exit(0)

    match args.action:
        case "config":
            config = PackageConfig(app_name="recp")

            if args.set:
                config.set_param(param=args.set[0], value=args.set[1])
            
            elif args.add:
                config.add_recipe(args.add)

            else:
                config.print_params()
        
        case "list":
            config = PackageConfig(app_name="recp")
            recipes = config.list_recipes()

            if len(recipes) == 0:
                print(
                    f"No recipes found in recipes folder "
                    f"{config.recipes_dir!r}. Add one with 'recp config "
                    "--add /path/to/recipe.yaml'"
                )

            names = [os.path.splitext(os.path.basename(r))[0] for r in recipes]
            width = max((len(n) for n in names), default=0) + 2

            for name, file in zip(names, recipes, strict=True):
                print(f"{style(name.ljust(width), 'b', 'cyan')}{file}")
        
        case "show":
            recipe = Recipe(file=resolve_recipe(args.recipe), preview=True)
            recipe.show()

        case "run":
            if args.jobs is not None and args.jobs < 1:
                exit_error("--jobs should be a positive integer")

            # Check if recipe is a preset
            args.recipe = resolve_recipe(args.recipe)

            # Add env variables
            os.environ["RECP_ROOT"] = sys.argv[0]
            os.environ["RECP_RECIPE_FILE"] = os.path.abspath(args.recipe)

            # Create and run recipe
            recipe = Recipe(file=args.recipe, allow_expr=args.unsafe)
            returncode = recipe.run(
                tag=args.tag,
                step=args.step,
                from_step=args.from_step,
                ignore_errors=args.ignore_errors,
                dry_run=args.dry_run,
                jobs=args.jobs
            )
            sys.exit(returncode)
        
        case _:
            raise AssertionError


if __name__ == "__main__":
    main()
