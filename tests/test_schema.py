import json
import yaml
import pytest
import jsonschema
from pathlib import Path
from recp.utils.apply import get_apply_registry

ROOT_DIR = Path(__file__).parents[1]


class TagLoader(yaml.SafeLoader):
    """Loader that keeps the value of custom tags such as `!input`."""


def construct_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)

    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)

    return loader.construct_scalar(node)


TagLoader.add_multi_constructor("!", construct_tag)


@pytest.fixture(scope="module")
def schema():
    return json.loads((ROOT_DIR / "recipe.schema.json").read_text())


def test_schema_is_valid(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_modifiers_match_registry(schema):
    command = schema["properties"]["recipe"]["additionalProperties"]
    command = command["properties"]["run"]["anyOf"][1]["items"]["anyOf"][1]
    modifiers = command["properties"]["apply"]["items"]["oneOf"]
    names = {m["properties"]["fn"]["const"] for m in modifiers}

    assert names == set(get_apply_registry())


@pytest.mark.parametrize(
    "file",
    sorted((ROOT_DIR / "examples").glob("*.yaml")),
    ids=lambda f: f.name
)
def test_examples_match_schema(schema, file):
    data = yaml.load(file.read_text(), Loader=TagLoader)
    jsonschema.validate(data, schema)


def test_schema_rejects_typos(schema):
    data = {"recipe": {"step": {"rnu": ["echo"]}}}

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)
