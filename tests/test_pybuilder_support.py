import textwrap
from pathlib import Path

from python_inspector.pybuilder_support import (
    is_pybuilder_project,
    parse_pybuilder_dependencies,
    get_pybuilder_dependencies,
)
from _packagedcode import models


def test_is_pybuilder_project_basic():
    src = """
from pybuilder.core import use_plugin, depends_on
use_plugin('python.core')
use_plugin('python.distutils')

name = 'demo'

"""
    assert is_pybuilder_project(src) is True


def test_parse_pybuilder_dependencies_depends_on_with_spec():
    src = textwrap.dedent(
        """
from pybuilder.core import use_plugin, depends_on
use_plugin('python.core')
use_plugin('python.unittest')
use_plugin('python.distutils')
from pybuilder.core import init

@init
def init(project):
    project.depends_on('requests', '~=2.32')
    project.build_depends_on('wheel', '>=0.42.0')
    project.test_depends_on('pytest', '==8.1.0')
"""
    )
    deps = parse_pybuilder_dependencies(src)
    assert {d.purl for d in deps} == {"pkg:pypi/requests", "pkg:pypi/wheel", "pkg:pypi/pytest"}
    reqs = {d.extracted_requirement for d in deps}
    assert "requests~=2.32" in reqs
    assert "wheel>=0.42.0" in reqs
    assert "pytest==8.1.0" in reqs
    scopes = {d.scope for d in deps}
    assert scopes == {"install", "build", "test"}


def test_get_pybuilder_dependencies_from_file(tmp_path):
    build_py = tmp_path / 'build.py'
    build_py.write_text(
        """
from pybuilder.core import use_plugin, depends_on
use_plugin('python.core')
from pybuilder.core import init
@init
def init(project):
    project.depends_on('click', '>=8.0')
"""
    )
    deps = list(get_pybuilder_dependencies(build_py))
    assert len(deps) == 1
    dep = deps[0]
    assert dep.purl == 'pkg:pypi/click'
    assert dep.extracted_requirement == 'click>=8.0'
    assert dep.scope == 'install'
