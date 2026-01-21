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

import pytest

from python_inspector.package_data import get_file_match_key


class TestGetFileMatchKey:
    """Tests for get_file_match_key function"""

    def test_extracts_filename_from_simple_url(self):
        """Test extracting filename from a simple URL without hash"""
        url = "https://files.pythonhosted.org/packages/numpy-1.26.4-py3-none-any.whl"
        result = get_file_match_key(url)
        assert result == ("numpy-1.26.4-py3-none-any.whl", None)

    def test_extracts_filename_and_hash_from_url_with_fragment(self):
        """Test extracting filename and SHA256 from URL with hash fragment"""
        url = (
            "https://files.pythonhosted.org/packages/numpy-1.26.4-py3-none-any.whl#sha256="
            + "a" * 64
        )
        result = get_file_match_key(url)
        assert result[0] == "numpy-1.26.4-py3-none-any.whl"
        assert result[1] == "a" * 64
        assert len(result[1]) == 64  # SHA256 is 64 hex characters

    def test_uses_provided_sha256_over_url_fragment(self):
        """Test that provided SHA256 takes precedence over URL fragment"""
        url = "https://files.pythonhosted.org/packages/file.whl#sha256=abc123" + "0" * 58
        provided_hash = "def456" + "0" * 58
        result = get_file_match_key(url, sha256=provided_hash)
        assert result == ("file.whl", provided_hash)

    def test_handles_pypi_org_style_urls(self):
        """Test PyPI.org style URLs with hash paths"""
        url = "https://files.pythonhosted.org/packages/c1/fa/abc123/package-1.0-py3-none-any.whl"
        result = get_file_match_key(url)
        assert result == ("package-1.0-py3-none-any.whl", None)

    def test_handles_artifactory_simple_style_urls(self):
        """Test Artifactory /simple endpoint style URLs"""
        url = "https://artifactory.example.com/simple/../packages/packages/c1/fa/package-1.0.whl"
        result = get_file_match_key(url)
        assert result == ("package-1.0.whl", None)

    def test_handles_artifactory_json_style_urls(self):
        """Test Artifactory JSON API style URLs"""
        url = "https://artifactory.example.com/pypi/c1/fa/package-1.0.whl"
        result = get_file_match_key(url)
        assert result == ("package-1.0.whl", None)

    def test_handles_relative_urls_resolved(self):
        """Test relative URLs (after resolution)"""
        url = "https://artifactory.example.com/../../packages/file.tar.gz"
        result = get_file_match_key(url)
        assert result == ("file.tar.gz", None)

    def test_extracts_tar_gz_filenames(self):
        """Test extracting .tar.gz filenames"""
        url = "https://pypi.org/packages/source/n/numpy/numpy-1.26.4.tar.gz"
        result = get_file_match_key(url)
        assert result == ("numpy-1.26.4.tar.gz", None)

    def test_handles_empty_fragment(self):
        """Test URL with empty fragment"""
        url = "https://example.com/package.whl#"
        result = get_file_match_key(url)
        assert result == ("package.whl", None)

    def test_ignores_non_sha256_fragments(self):
        """Test that non-SHA256 fragments are ignored"""
        url = "https://example.com/package.whl#md5=abc123"
        result = get_file_match_key(url)
        assert result == ("package.whl", None)

    def test_handles_sha256_fragment_with_uppercase(self):
        """Test SHA256 extraction is case-insensitive for hex"""
        url = "https://example.com/file.whl#sha256=ABCDEF" + "0" * 58
        result = get_file_match_key(url)
        # Note: The regex uses [a-f0-9] which is lowercase only
        # This test documents current behavior - uppercase won't match
        assert result == ("file.whl", None)

    def test_rejects_invalid_sha256_length(self):
        """Test that short hashes are not extracted"""
        url = "https://example.com/file.whl#sha256=abc123"  # Only 6 chars
        result = get_file_match_key(url)
        assert result == ("file.whl", None)

    def test_handles_complex_wheel_filename(self):
        """Test complex wheel filename with platform tags"""
        url = "https://example.com/packages/numpy-1.26.4-cp311-cp311-macosx_10_9_x86_64.whl"
        result = get_file_match_key(url)
        assert result == ("numpy-1.26.4-cp311-cp311-macosx_10_9_x86_64.whl", None)

    def test_handles_url_with_query_parameters(self):
        """Test URL with query parameters (though unusual for packages)"""
        url = "https://example.com/package.whl?token=xyz#sha256=" + "a" * 64
        result = get_file_match_key(url)
        assert result[0] == "package.whl"
        assert result[1] == "a" * 64
