import json
import os
import re
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from ggshield.__main__ import cli
from ggshield.core.errors import ExitCode
from tests.repository import Repository
from tests.unit.conftest import (
    _ONE_LINE_AND_MULTILINE_PATCH,
    UNCHECKED_SECRET_PATCH,
    VALID_SECRET_PATCH,
    assert_invoke_exited_with,
    assert_invoke_ok,
    my_vcr,
)


def create_normally_ignored_file() -> Path:
    path = Path("node_modules", "test.js")
    path.parent.mkdir()
    path.write_text("// Test")
    return path


class TestPathScan:
    """
    Tests related to ggshield secret scan path
    """

    def create_files(self):
        Path("file1").write_text("This is a file with no secrets.")
        Path("file2").write_text("This is a file with no secrets.")

    @my_vcr.use_cassette("test_scan_file")
    @pytest.mark.parametrize("verbose", [True, False])
    def test_scan_file(self, cli_fs_runner, verbose):
        Path("file").write_text("This is a file with no secrets.")
        assert os.path.isfile("file")

        if verbose:
            result = cli_fs_runner.invoke(cli, ["-v", "secret", "scan", "path", "file"])
        else:
            result = cli_fs_runner.invoke(cli, ["secret", "scan", "path", "file"])
        assert result.exit_code == ExitCode.SUCCESS, result.output
        assert not result.exception
        assert "No secrets have been found" in result.output

    def test_scan_file_secret(self, cli_fs_runner):
        """
        GIVEN a file with a secret
        WHEN it is scanned
        THEN the secret is reported
        AND the exit code is not 0
        """
        Path("file_secret").write_text(UNCHECKED_SECRET_PATCH)
        assert os.path.isfile("file_secret")

        cmd = ["secret", "scan", "path", "file_secret"]

        with my_vcr.use_cassette("test_scan_file_secret"):
            result = cli_fs_runner.invoke(cli, cmd)
            assert_invoke_exited_with(result, ExitCode.SCAN_FOUND_PROBLEMS)
            assert result.exception
            assert re.search(
                """>> Secret detected: GitGuardian Development Secret
   Validity: No Checker
   Occurrences: 1
   Known by GitGuardian dashboard: (YES|NO)
   Incident URL: (https://.*|N/A)
   Secret SHA: 4f307a4cae8f14cc276398c666559a6d4f959640616ed733b168a9ee7ab08fd4
""",
                result.output,
            )

    def test_scan_file_secret_with_validity(self, cli_fs_runner):
        Path("file_secret").write_text(VALID_SECRET_PATCH)
        assert os.path.isfile("file_secret")

        with my_vcr.use_cassette("test_scan_path_file_secret_with_validity"):
            result = cli_fs_runner.invoke(
                cli, ["-v", "secret", "scan", "path", "file_secret"]
            )
        assert_invoke_exited_with(result, ExitCode.SCAN_FOUND_PROBLEMS)
        assert result.exception
        assert re.search(
            """>> Secret detected: GitGuardian Test Token Checked
   Validity: Valid
   Occurrences: 1
   Known by GitGuardian dashboard: (YES|NO)
   Incident URL: (https://.*|N/A)
   Secret SHA: 56c126cef75e3d17c3de32dac60bab688ecc384a054c2c85b688c1dd7ac4eefd
""",
            result.output,
        )

    @pytest.mark.parametrize("validity", [True, False])
    def test_scan_file_secret_json_with_validity(self, cli_fs_runner, validity):
        secret = VALID_SECRET_PATCH if validity else UNCHECKED_SECRET_PATCH
        Path("file_secret").write_text(secret)
        assert os.path.isfile("file_secret")

        cassette_name = f"test_scan_file_secret-{validity}"
        with my_vcr.use_cassette(cassette_name):
            cli_fs_runner.mix_stderr = False
            result = cli_fs_runner.invoke(
                cli, ["-v", "secret", "scan", "--json", "path", "file_secret"]
            )
        assert_invoke_exited_with(result, ExitCode.SCAN_FOUND_PROBLEMS)
        assert result.exception

        if validity:
            assert '"validity": "valid"' in result.output
        else:
            assert '"validity": "valid"' not in result.output
        json.loads(result.output)

    @pytest.mark.parametrize("json_output", [False, True])
    def test_scan_file_secret_exit_zero(self, cli_fs_runner, json_output):
        Path("file_secret").write_text(UNCHECKED_SECRET_PATCH)
        assert os.path.isfile("file_secret")

        with my_vcr.use_cassette("test_scan_file_secret"):
            cli_fs_runner.mix_stderr = False
            json_arg = ["--json"] if json_output else []
            result = cli_fs_runner.invoke(
                cli,
                [
                    "secret",
                    "scan",
                    "-v",
                    "path",
                    *json_arg,
                    "--exit-zero",
                    "file_secret",
                ],
            )
            assert_invoke_ok(result)
            assert not result.exception
            if json_output:
                json.loads(result.output)

    def test_files_abort(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli, ["secret", "scan", "path", "file1", "file2"], input="n\n"
        )
        assert_invoke_ok(result)
        assert not result.exception

    @my_vcr.use_cassette()
    def test_files_yes(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli, ["secret", "scan", "path", "file1", "file2", "-r", "-y"]
        )
        assert_invoke_ok(result)
        assert not result.exception

    @my_vcr.use_cassette()
    def test_files_verbose(self, cli_fs_runner: CliRunner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli,
            ["-v", "secret", "scan", "path", "file1", "file2", "-r"],
            input="y\n",
            catch_exceptions=True,
        )
        assert_invoke_ok(result)
        assert not result.exception
        assert "file1\n" in result.output
        assert "file2\n" in result.output
        assert "No secrets have been found" in result.output

    def test_files_verbose_abort(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli, ["-v", "secret", "scan", "path", "file1", "file2", "-r"], input="n\n"
        )
        assert_invoke_ok(result)
        assert not result.exception

    @my_vcr.use_cassette()
    def test_files_verbose_yes(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli, ["-v", "secret", "scan", "path", "file1", "file2", "-r", "-y"]
        )
        assert_invoke_ok(result)
        assert not result.exception
        assert "file1\n" in result.output
        assert "file2\n" in result.output
        assert "No secrets have been found" in result.output

    @patch("ggshield.verticals.secret.secret_scanner.SecretScanner.scan")
    def test_scan_ignored_directory(self, scan_mock, cli_fs_runner):
        self.create_files()
        config = """
version: 2
secret:
    ignored-paths:
        - "file1"

"""
        Path(".gitguardian.yaml").write_text(config)

        result = cli_fs_runner.invoke(
            cli, ["secret", "scan", "path", "file1", "file2", "-y"]
        )

        assert_invoke_exited_with(result, ExitCode.USAGE_ERROR)
        assert "An ignored file or directory cannot be scanned." in result.stdout
        scan_mock.assert_not_called()


class TestScanDirectory:
    """
    Tests related to ggshield secret scan path -r
    """

    @staticmethod
    def path_line(path_str):
        # Turn a path string into a \n terminated line
        # Takes care of Windows paths
        return str(Path(path_str)) + "\n"

    def create_files(self):
        os.makedirs("dir", exist_ok=True)
        os.makedirs("dir/subdir", exist_ok=True)
        Path("file1").write_text("This is a file with no secrets.")
        Path("dir/file2").write_text("This is a file with no secrets.")
        Path("dir/subdir/file3").write_text("This is a file with no secrets.")
        Path("dir/subdir/file4").write_text("This is a file with no secrets.")

    def test_directory_error(self, cli_fs_runner):
        result = cli_fs_runner.invoke(
            cli, ["secret", "scan", "path", "-r", "./ewe-failing-test"]
        )
        assert_invoke_exited_with(result, 2)
        assert result.exception
        assert "does not exist" in result.output

    def test_directory_abort(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli, ["secret", "scan", "path", "./", "-r"], input="n\n"
        )
        assert_invoke_ok(result)
        assert not result.exception

    @my_vcr.use_cassette()
    def test_directory_yes(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(cli, ["secret", "scan", "path", "./", "-r", "-y"])
        assert_invoke_ok(result)
        assert not result.exception

    @my_vcr.use_cassette()
    def test_directory_verbose(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli, ["secret", "scan", "path", "./", "-r", "-v"], input="y\n"
        )
        assert_invoke_ok(result)
        assert not result.exception
        assert "file1\n" in result.output
        assert self.path_line("dir/file2") in result.output
        assert self.path_line("dir/subdir/file3") in result.output
        assert "No secrets have been found" in result.output

    def test_directory_verbose_abort(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli, ["secret", "-v", "scan", "path", "./", "-r"], input="n\n"
        )
        assert_invoke_ok(result)
        assert not result.exception

    def test_directory_verbose_ignored_abort(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli,
            [
                "secret",
                "scan",
                "-v",
                "--exclude",
                "file1",
                "path",
                "./",
                "-r",
                "--exclude",
                "dir/file2",
            ],
            input="n\n",
        )
        assert_invoke_ok(result)
        assert "file1\n" not in result.output
        assert self.path_line("dir/file2") not in result.output
        assert self.path_line("dir/subdir/file3") in result.output
        assert self.path_line("dir/subdir/file4") in result.output
        assert not result.exception

    def test_directory_verbose_ignored_path_abort(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli,
            [
                "secret",
                "scan",
                "-v",
                "path",
                "./",
                "-r",
                "--exclude",
                "dir/subdir/*",
            ],
            input="n\n",
        )
        assert_invoke_ok(result)
        assert "file1\n" in result.output
        assert self.path_line("dir/file2") in result.output
        assert self.path_line("dir/subdir/file3") not in result.output
        assert self.path_line("dir/subdir/file4") not in result.output
        assert not result.exception

    @my_vcr.use_cassette()
    def test_directory_verbose_yes(self, cli_fs_runner):
        self.create_files()
        result = cli_fs_runner.invoke(
            cli, ["secret", "scan", "path", "./", "-r", "-vy"]
        )
        assert result.exit_code == ExitCode.SUCCESS, result.output
        assert not result.exception
        assert "file1\n" in result.output
        assert self.path_line("dir/file2") in result.output
        assert self.path_line("dir/subdir/file3") in result.output
        assert "No secrets have been found" in result.output

    def test_scan_path_should_detect_non_git_files(self, cli_fs_runner):
        """
        GIVEN a path scan on a git repository
        WHEN some files are not followed by git
        THEN those files should still be picked on by ggshield for analysis
        """
        os.makedirs("git_repo")
        Path("git_repo/committed_file.js").write_text(
            "NPM_TOKEN=npm_xxxxxxxxxxxxxxxxxxxxxxxxxx"
        )
        os.system("git init")
        os.system("git add .")
        os.system("git commit -m 'initial commit'")
        Path("git_repo/not_committed.js").write_text(
            "NPM_TOKEN=npm_xxxxxxxxxxxxxxxxxxxxxxxxxx"
        )

        result = cli_fs_runner.invoke(
            cli, ["secret", "scan", "-v", "path", "--recursive", "."]
        )
        assert result.exit_code == ExitCode.SUCCESS, result.output
        assert all(
            string in result.output
            for string in ["Do you want to continue", "not_committed"]
        ), "not_committed files not should have been ignored"
        assert result.exception is None

    @pytest.mark.parametrize(
        "ignored_detectors, nb_secret",
        [
            ([], 2),
            (["-b", "RSA Private Key"], 1),
            (["-b", "SendGrid Key"], 1),
            (["-b", "host"], 2),
            (["-b", "SendGrid Key", "-b", "host"], 1),
            (["-b", "SendGrid Key", "-b", "RSA Private Key"], 0),
        ],
    )
    def test_ignore_detectors(
        self,
        cli_fs_runner,
        ignored_detectors,
        nb_secret,
    ):
        Path("file_secret").write_text(_ONE_LINE_AND_MULTILINE_PATCH)

        with my_vcr.use_cassette("test_scan_path_file_one_line_and_multiline_patch"):
            result = cli_fs_runner.invoke(
                cli,
                [
                    "secret",
                    "scan",
                    "-v",
                    *ignored_detectors,
                    "path",
                    "file_secret",
                    "--exit-zero",
                ],
            )
            assert result.exit_code == ExitCode.SUCCESS, result.output
            if nb_secret:
                plural = nb_secret > 1
                assert (
                    f": {nb_secret} incident{'s' if plural else ''} "
                ) in result.output
            else:
                assert "No secrets have been found" in result.output

    @patch("pygitguardian.GGClient.multi_content_scan")
    @my_vcr.use_cassette("test_scan_context_repository.yaml")
    def test_scan_context_repository(
        self,
        scan_mock: Mock,
        tmp_path: Path,
        cli_fs_runner: CliRunner,
    ) -> None:
        """
        GIVEN a repository with a remote url
        WHEN executing a scan
        THEN repository url is sent
        """
        local_repo = Repository.create(tmp_path)
        remote_url = "https://github.com/owner/repository.git"
        local_repo.git("remote", "add", "origin", remote_url)

        file = local_repo.path / "file_secret"
        file.write_text(_ONE_LINE_AND_MULTILINE_PATCH)
        local_repo.add(file)
        local_repo.create_commit()

        cli_fs_runner.invoke(
            cli,
            [
                "secret",
                "scan",
                "path",
                "-r",
                str(local_repo.path),
            ],
        )

        scan_mock.assert_called_once()
        assert any(
            isinstance(arg, dict)
            and arg.get("GGShield-Repository-URL") == "github.com/owner/repository"
            for arg in scan_mock.call_args[0]
        )
