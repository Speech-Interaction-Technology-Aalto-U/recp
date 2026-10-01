import os
import json
import shutil
from typing import Any
from platformdirs import PlatformDirs
from .exceptions import (
    FileExtensionError,
    FolderNotFoundError,
    RecpError
)


class PackageConfig:
    """Package configuration parameters.

    Args:
        app_name (str): Application name.
        app_author (str): Application author name.
    """
    def __init__(
            self,
            app_name: str,
            app_author: str = "Esteban Gómez"
    ) -> None:
        super().__init__()

        # Params
        self._platform = PlatformDirs(appname=app_name, appauthor=app_author)
        self.maybe_reset_default_config()
        self.config_file = os.path.join(
            self._platform.user_data_dir,
            "settings.json"
        )
        
        with open(self.config_file) as f:
            self.config = json.load(f)
        
    @property
    def recipes_dir(self) -> str:
        """Returns the folder where user recipes are stored.

        Returns:
            (str): Folder where user recipes are stored.
        """
        return self.config["recipes.dir"]

    def maybe_reset_default_config(self) -> None:
        """Restores the default package configuration if it does not exist."""
        BASE_DIR = self._platform.user_data_dir
        RECIPES_DIR = os.path.join(BASE_DIR, "recipes")
        BASE_SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
        BASE_SETTINGS = {"recipes.dir": RECIPES_DIR}

        os.makedirs(BASE_DIR, exist_ok=True)
        os.makedirs(RECIPES_DIR, exist_ok=True)

        if not os.path.isfile(BASE_SETTINGS_FILE):
            with open(BASE_SETTINGS_FILE, "w") as f:
                json.dump(obj=BASE_SETTINGS, fp=f, indent=2)
    
    def save_config(self) -> None:
        """Saves the `settings.json` configuration file with the update
        configuration parameters.
        """
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)
 
    def set_param(self, param: str, value: Any) -> None:
        """Sets a parameter value in the user configuration file.
        
        Args:
            param (str): Parameter name.
            value (Any): Parameter value.
        """
        if param not in self.config:
            raise RecpError(
                f"Invalid parameter {param!r}. Run 'recp config' to list "
                "existing parameters"
            )
        
        match param:
            case "recipes.dir":
                value = os.path.abspath(
                    os.path.expanduser(os.path.expandvars(value))
                )

                if not os.path.isdir(value):
                    raise FolderNotFoundError(f"Invalid folder {value!r}")
                
                self.config[param] = value
            
            case _:
                raise AssertionError
        
        self.save_config()
    
    def add_recipe(self, file: str) -> None:
        """Adds a new recipe to the user recipes folder.
        
        Args:
            file (str): `.yaml` recipe file to add.
        """
        if not os.path.isfile(file):
            raise FileNotFoundError(f"File {file!r} not found")
        
        if not file.endswith((".yaml", ".yml")):
            raise FileExtensionError(
                "Only .yaml or .yml files can be added as recipes"
            )
        
        dst = os.path.join(self.recipes_dir, os.path.basename(file))
        replaced = os.path.isfile(dst)
        shutil.copy(file, dst)

        if replaced:
            print(f"Recipe {file!r} replaced existing recipe {dst!r}")
        
        else:
            print(f"Recipe {file!r} successfully added to recipes folder")

    def list_recipes(self) -> list[str]:
        """Returns the recipes stored in the user recipes folder.

        Returns:
            (list[str]): Path to each recipe file, sorted by name.
        """
        if not os.path.isdir(self.recipes_dir):
            return []

        return sorted(
            os.path.join(self.recipes_dir, f)
            for f in os.listdir(self.recipes_dir)
            if f.endswith((".yaml", ".yml"))
        )

    def find_recipe(self, name: str) -> str | None:
        """Finds a recipe in the user recipes folder by its name.

        Args:
            name (str): Recipe name without extension.

        Returns:
            (str | None): Path to the recipe file, or `None` if not found.
        """
        for ext in (".yaml", ".yml"):
            file = os.path.join(self.recipes_dir, name + ext)

            if os.path.isfile(file):
                return file

        return None

    def print_params(self) -> None:
        """Prints user parameters to the terminal. """
        print(f"file: {self.config_file!r}")

        for k, v in self.config.items():
            print(f"{k}: {v!r}")
