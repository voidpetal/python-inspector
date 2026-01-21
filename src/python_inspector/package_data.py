#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) nexB Inc. and others. All rights reserved.
# ScanCode is a trademark of nexB Inc.
# SPDX-License-Identifier: Apache-2.0
# See http://www.apache.org/licenses/LICENSE-2.0 for the license text.
# See https://github.com/aboutcode-org/python-inspector for support or download.
# See https://aboutcode.org for more information about nexB OSS projects.
#

import posixpath
from typing import Dict
from typing import List
from typing import Optional
from urllib.parse import urlparse

from packageurl import PackageURL

from _packagedcode.models import PackageData
from _packagedcode.pypi import get_declared_license
from _packagedcode.pypi import get_description
from _packagedcode.pypi import get_keywords
from _packagedcode.pypi import get_parties
from python_inspector import utils_pypi
from python_inspector.resolution import get_python_version_from_env_tag
from python_inspector.utils_pypi import Environment
from python_inspector.utils_pypi import PypiSimpleRepository


def get_file_match_key(url: str, sha256: Optional[str] = None) -> tuple:
    """
    Extract a match key (filename, sha256) for comparing distribution files.

    This universal approach works across all PyPI-compatible repositories regardless of
    URL path structure, because:
    - Filenames are standardized by PEP 427/491
    - SHA256 hashes are immutable (same file = same hash)
    - URL paths vary by implementation (PyPI.org, Artifactory, etc.)

    Args:
        url: The download URL
        sha256: Optional SHA256 hash (if not in URL fragment)

    Returns:
        Tuple of (filename, sha256_hash)

    Example:
        https://host/path/file-1.0-py3.whl#sha256=abc123 -> ('file-1.0-py3.whl', 'abc123')
        https://host/path/file-1.0.tar.gz -> ('file-1.0.tar.gz', None)

    """
    import re

    # Extract filename from URL (before any # fragment)
    parsed = urlparse(url)
    filename = posixpath.basename(parsed.path)

    # Try to extract SHA256 from URL fragment if not provided
    if not sha256 and parsed.fragment:
        hash_match = re.search(r"sha256=([a-f0-9]{64})", parsed.fragment)
        if hash_match:
            sha256 = hash_match.group(1)

    return (filename, sha256)


async def get_pypi_data_from_purl(
    purl: str, environment: Environment, repos: List[PypiSimpleRepository], prefer_source: bool
) -> Optional[PackageData]:
    """
    Generate `Package` object from the `purl` string of pypi type

    ``purl`` is a package-url of pypi type
    ``environment`` is a `Environment` object defaulting Python version 3.8 and linux OS
    ``repos`` is a list of `PypiSimpleRepository` objects
    ``prefer_source`` is a boolean value to prefer source distribution over wheel,
    if no source distribution is available then wheel is used
    """
    parsed_purl = PackageURL.from_string(purl)
    name = parsed_purl.name
    version = parsed_purl.version
    if not version:
        raise Exception("Version is not specified in the purl")

    # Derive base URL from repos if available, otherwise fallback to PyPI.org
    if repos:
        # Convert to list if needed and use first repo's index_url
        repos_list = list(repos) if not isinstance(repos, list) else repos
        base_path = repos_list[0].index_url.replace("/simple", "/pypi")
    else:
        base_path = "https://pypi.org/pypi"

    api_url = f"{base_path}/{name}/{version}/json"

    from python_inspector.utils import get_response_async

    response = await get_response_async(api_url)
    if not response:
        return None

    info = response.get("info") or {}
    homepage_url = info.get("home_page")
    project_urls = info.get("project_urls") or {}
    code_view_url = get_pypi_codeview_url(project_urls)
    bug_tracking_url = get_pypi_bugtracker_url(project_urls)
    python_version = get_python_version_from_env_tag(python_version=environment.python_version)
    valid_distribution_urls = []
    sdist_url = await get_sdist_download_url(
        purl=parsed_purl, repos=repos, python_version=python_version
    )
    if sdist_url:
        valid_distribution_urls.append(sdist_url)

    valid_distribution_urls = [url for url in valid_distribution_urls if url]

    # if prefer_source is True then only source distribution is used
    # in case of no source distribution available then wheel is used
    if not valid_distribution_urls or not prefer_source:
        wheel_urls = [
            item
            for item in await get_wheel_download_urls(
                purl=parsed_purl,
                repos=repos,
                environment=environment,
                python_version=python_version,
            )
        ]
        wheel_url = choose_single_wheel(wheel_urls)
        if wheel_url:
            valid_distribution_urls.insert(0, wheel_url)

    # Build a dict indexed by filename for universal matching across repositories
    # Match by filename since /simple endpoint URLs and JSON API URLs may have different paths
    # Filenames are standardized (PEP 427/491) and unique per package version
    from urllib.parse import urljoin

    urls_by_filename = {}
    for url_entry in response.get("urls") or []:
        url = url_entry.get("url")
        if url:
            # Resolve relative URLs (from Artifactory) to absolute URLs
            absolute_url = urljoin(api_url, url)

            # Extract filename for matching
            parsed = urlparse(absolute_url)
            filename = posixpath.basename(parsed.path)

            urls_by_filename[filename] = url_entry

    # Iterate over valid distribution URLs and match by filename
    for dist_url in valid_distribution_urls:
        # Extract filename from distribution URL
        parsed = urlparse(dist_url)
        filename = posixpath.basename(parsed.path)

        if filename not in urls_by_filename:
            continue

        url_data = urls_by_filename[filename]
        digests = url_data.get("digests") or {}

        return PackageData(
            primary_language="Python",
            description=get_description(info),
            homepage_url=homepage_url,
            api_data_url=api_url,
            bug_tracking_url=bug_tracking_url,
            code_view_url=code_view_url,
            license_expression=info.get("license_expression"),
            declared_license=get_declared_license(info),
            download_url=dist_url,
            size=url_data.get("size"),
            md5=digests.get("md5") or url_data.get("md5_digest"),
            sha256=digests.get("sha256"),
            release_date=url_data.get("upload_time"),
            keywords=get_keywords(info),
            parties=get_parties(
                info,
                author_key="author",
                author_email_key="author_email",
                maintainer_key="maintainer",
                maintainer_email_key="maintainer_email",
            ),
            **parsed_purl.to_dict(),
        )

    return None


def choose_single_wheel(wheel_urls: List[str]) -> Optional[str]:
    """
    Sort wheel urls descendingly and return the first one
    """
    wheel_urls.sort(reverse=True)
    if wheel_urls:
        return wheel_urls[0]
    else:
        return None


def get_pypi_bugtracker_url(project_urls: Dict) -> Optional[str]:
    bug_tracking_url = project_urls.get("Tracker")
    if not bug_tracking_url:
        bug_tracking_url = project_urls.get("Issue Tracker")
    if not bug_tracking_url:
        bug_tracking_url = project_urls.get("Bug Tracker")
    return bug_tracking_url


def get_pypi_codeview_url(project_urls: Dict) -> Optional[str]:
    code_view_url = project_urls.get("Source")
    if not code_view_url:
        code_view_url = project_urls.get("Code")
    if not code_view_url:
        code_view_url = project_urls.get("Source Code")
    return code_view_url


async def get_wheel_download_urls(
    purl: PackageURL,
    repos: List[PypiSimpleRepository],
    environment: Environment,
    python_version: str,
) -> List[str]:
    """
    Return a list of download urls for the given purl.
    """
    download_urls = []
    for repo in repos:
        for wheel in await utils_pypi.get_supported_and_valid_wheels(
            repo=repo,
            name=purl.name,
            version=purl.version,
            environment=environment,
            python_version=python_version,
        ):
            download_urls.append(await wheel.download_url(repo))
    return download_urls


async def get_sdist_download_url(
    purl: PackageURL, repos: List[PypiSimpleRepository], python_version: str
) -> str:
    """
    Return a list of download urls for the given purl.
    """
    for repo in repos:
        sdist = await utils_pypi.get_valid_sdist(
            repo=repo,
            name=purl.name,
            version=purl.version,
            python_version=python_version,
        )
        if sdist:
            return await sdist.download_url(repo)
