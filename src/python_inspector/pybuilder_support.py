"""PyBuilder project support: dependency extraction from build.py.

This provides utilities to detect a PyBuilder project and extract declared
project dependencies without executing arbitrary code (AST parsing only).
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, List

from _packagedcode import models

PYB_CALL_ATTRS = {
    "depends_on": "install",
    "build_depends_on": "build",
    "test_depends_on": "test",
}


def is_pybuilder_project(build_py_text: str) -> bool:
    """Return True if the build.py source text looks like a PyBuilder build script."""
    if not build_py_text:
        return False
    # simple heuristics: presence of use_plugin / depends_on / Project class mention
    lowered = build_py_text.lower()
    return (
        "use_plugin(" in lowered
        or "depends_on(" in lowered
        or "build_depends_on(" in lowered
        or "test_depends_on(" in lowered
    )


def parse_pybuilder_dependencies(build_py_text: str) -> List[models.DependentPackage]:
    """Return a list of DependentPackage extracted from a PyBuilder build.py source.

    We look for calls to project.depends_on()/build_depends_on()/test_depends_on.
    Only literal string arguments are considered to avoid executing code.
    Optional second positional argument is treated as a version spec appended
    directly to the name (as PyBuilder typically uses e.g. depends_on("foo", "~=1.2")).
    """
    if not build_py_text:
        return []
    try:
        tree = ast.parse(build_py_text)
    except SyntaxError:
        return []

    deps: List[models.DependentPackage] = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in PYB_CALL_ATTRS:
                scope = PYB_CALL_ATTRS[func.attr]
                # ensure receiver is named 'project' to reduce false positives
                if isinstance(func.value, ast.Name) and func.value.id == "project":
                    name = _const(node.args[0]) if node.args else None
                    spec = _const(node.args[1]) if len(node.args) > 1 else None
                    if name:
                        extracted_req = f"{name}{spec or ''}" if spec else name
                        deps.append(
                            models.DependentPackage(
                                purl=f"pkg:pypi/{name}",
                                extracted_requirement=extracted_req,
                                scope=scope,
                            )
                        )
            self.generic_visit(node)

    def _const(node):  # type: ignore[override]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value.strip()
        return None

    Visitor().visit(tree)
    return deps


def get_pybuilder_dependencies(build_py_path: Path) -> Iterable[models.DependentPackage]:
    if not build_py_path.is_file():
        return []
    text = build_py_path.read_text(errors="ignore")
    if not is_pybuilder_project(text):
        return []
    return parse_pybuilder_dependencies(text)
