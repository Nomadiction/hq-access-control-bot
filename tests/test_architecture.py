import ast
from pathlib import Path

import pytest

import hq_access_bot.whitelist

WHITELIST_MODULES = sorted(Path(hq_access_bot.whitelist.__file__).parent.glob("*.py"))


def collect_imported_packages(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    packages: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            packages |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            packages.add(node.module.split(".")[0])
    return packages


@pytest.mark.parametrize("module_path", WHITELIST_MODULES, ids=lambda path: path.name)
def test_access_list_code_does_not_depend_on_telegram(module_path):
    assert "aiogram" not in collect_imported_packages(module_path)
