import pytest


@pytest.fixture(autouse=True)
def recp_env(tmp_path, monkeypatch):
    """Isolates the recp configuration and disables colors in all tests."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def write_recipe(tmp_path):
    """Writes a recipe file and returns its path."""
    def _write_recipe(content: str, name: str = "recipe.yaml") -> str:
        file = tmp_path / name
        file.write_text(content)
        return str(file)

    return _write_recipe
