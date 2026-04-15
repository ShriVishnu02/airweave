import sys
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from airweave.platform.configs.config import LocalDriveConfig


class TestLocalDriveConfigDefaults:
    def test_valid_path_and_defaults(self, tmp_path):
        """Valid dir is accepted; all defaults are sane."""
        cfg = LocalDriveConfig(root_path=str(tmp_path))
        assert cfg.root_path == str(tmp_path)
        assert cfg.extensions == []
        assert cfg.max_file_size_mb == 0.0
        assert cfg.follow_symlinks is False


class TestLocalDriveConfigRootPathValidator:
    def test_rejects_nonexistent_path(self):
        with pytest.raises(ValidationError, match="does not exist"):
            LocalDriveConfig(root_path="/absolutely/nonexistent/xyz/path")

    def test_rejects_file_not_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("data")
        with pytest.raises(ValidationError, match="not a directory"):
            LocalDriveConfig(root_path=str(f))

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only dangerous path tests")
    @pytest.mark.parametrize("badpath", ["/etc", "/proc", "/sys"])
    def test_rejects_dangerous_system_paths(self, badpath):
        with pytest.raises(ValidationError, match="not allowed"):
            LocalDriveConfig(root_path=badpath)

    @pytest.mark.parametrize("badpath", ["/etc", "/proc", "/sys"])
    def test_rejects_dangerous_system_paths_cross_platform(self, badpath):
        """Cross-platform test: mocks OS calls so the dangerous-path logic
        is validated regardless of whether these paths exist on the host OS."""
        with (
            patch("os.path.realpath", return_value=badpath),
            patch("os.path.exists", return_value=True),
            patch("os.path.isdir", return_value=True),
        ):
            with pytest.raises(ValidationError, match="not allowed"):
                LocalDriveConfig(root_path=badpath)
