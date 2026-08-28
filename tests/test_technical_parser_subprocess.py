from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from classifire.services import technical_parser_oci as oci
from classifire.services.technical_parser_execution import (
    TechnicalParserExecutionError,
)


@unittest.skipUnless(os.name == "posix", "POSIX process-group boundary")
class SubprocessOciRuntimeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = oci._SubprocessOciRuntimeAdapter()

    def _run(
        self,
        program: str,
        *,
        stdin_writer=None,
        timeout_seconds: float = 2.0,
        stdout_limit: int = 64,
        on_terminate=None,
    ):
        return self.adapter.run(
            (sys.executable, "-c", program),
            stdin_writer=stdin_writer,
            timeout_seconds=timeout_seconds,
            stdout_limit=stdout_limit,
            stderr_limit=0,
            environment={},
            on_terminate=on_terminate,
        )

    def test_exact_stdin_and_stdout_limit(self) -> None:
        result = self._run(
            "import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data[::-1])",
            stdin_writer=lambda stream: stream.write(b"abc"),
            stdout_limit=3,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"cba")
        self.assertEqual(result.stderr, b"")

    def test_controller_file_verification_rejects_fifo_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory(prefix="classifire-posix-fifo-") as temporary:
            fifo_path = Path(temporary) / "runtime"
            os.mkfifo(fifo_path)
            started = time.monotonic()
            with self.assertRaises(oci.TechnicalParserOciConfigurationError):
                oci._verified_file(
                    fifo_path,
                    expected_sha256="0" * 64,
                    maximum_bytes=1024,
                    path_code="PARSER_OCI_RUNTIME_PATH_INVALID",
                    sha_code="PARSER_OCI_RUNTIME_SHA256_INVALID",
                    retain_payload=False,
                )
            self.assertLess(time.monotonic() - started, 1.0)

    def test_stdout_limit_plus_one_and_any_stderr_fail(self) -> None:
        with self.assertRaises(oci._BoundedCommandError) as overflow:
            self._run(
                "import sys; sys.stdout.buffer.write(b'abcd')",
                stdout_limit=3,
            )
        self.assertEqual(overflow.exception.kind, "stdout_overflow")

        with self.assertRaises(oci._BoundedCommandError) as stderr:
            self._run("import sys; sys.stderr.buffer.write(b'x')")
        self.assertEqual(stderr.exception.kind, "stderr_output")

    def test_host_input_failure_is_preserved_after_process_cleanup(self) -> None:
        expected = TechnicalParserExecutionError("PARSER_EXECUTION_SOURCE_INVALID")

        def fail_input(_stream) -> None:
            raise expected

        with self.assertRaises(TechnicalParserExecutionError) as raised:
            self._run(
                "import sys; sys.stdin.buffer.read()",
                stdin_writer=fail_input,
            )
        self.assertIs(raised.exception, expected)

    def test_timeout_kills_parent_and_descendant_process_group(self) -> None:
        with tempfile.TemporaryDirectory(prefix="classifire-posix-tree-") as temporary:
            pid_path = Path(temporary) / "descendant.pid"
            program = (
                "import pathlib,subprocess,sys,time; "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='ascii'); "
                "time.sleep(60)"
            )
            started = time.monotonic()
            with self.assertRaises(oci._BoundedCommandError) as raised:
                self.adapter.run(
                    (sys.executable, "-c", program, str(pid_path)),
                    stdin_writer=None,
                    timeout_seconds=0.5,
                    stdout_limit=0,
                    stderr_limit=0,
                    environment={},
                )
            self.assertEqual(raised.exception.kind, "timeout")
            self.assertLess(time.monotonic() - started, 5.0)
            descendant_pid = int(pid_path.read_text(encoding="ascii"))
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    os.kill(descendant_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            else:
                self.fail("descendant process survived timeout cleanup")

    def test_failed_termination_is_reported(self) -> None:
        with mock.patch.object(oci, "_terminate_process_tree", return_value=False):
            with self.assertRaises(oci._BoundedCommandError) as raised:
                self._run("import sys; sys.stderr.buffer.write(b'x')")
        self.assertEqual(raised.exception.kind, "termination_failed")

    def test_each_thread_start_failure_runs_both_cleanup_layers(self) -> None:
        for failing_start in (1, 2, 3):
            with self.subTest(failing_start=failing_start):
                self._assert_thread_start_failure_is_contained(failing_start)

    def _assert_thread_start_failure_is_contained(self, failing_start: int) -> None:
        starts = 0
        process_tree_calls: list[int] = []
        callback_calls: list[bool] = []
        original_start = threading.Thread.start
        original_terminate = oci._terminate_process_tree

        def fail_selected_start(thread: threading.Thread) -> None:
            nonlocal starts
            starts += 1
            if starts == failing_start:
                raise RuntimeError("injected thread start failure")
            original_start(thread)

        def record_termination(process: subprocess.Popen[bytes]) -> bool:
            process_tree_calls.append(process.pid)
            return original_terminate(process)

        with (
            mock.patch.object(threading.Thread, "start", fail_selected_start),
            mock.patch.object(
                oci,
                "_terminate_process_tree",
                record_termination,
            ),
            self.assertRaises(RuntimeError),
        ):
            self._run(
                "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'ok')",
                stdin_writer=lambda stream: stream.write(b"input"),
                on_terminate=lambda: callback_calls.append(True),
            )
        self.assertEqual(callback_calls, [True])
        self.assertEqual(len(process_tree_calls), 1)


if __name__ == "__main__":
    unittest.main()
