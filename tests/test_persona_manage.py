from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Self

_ROOT = Path(__file__).parents[1]
_V2_DIGEST = "0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603"
_V1_DIGEST = "25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a"


class PersonaManageRollbackTests(unittest.TestCase):
    def test_activation_and_smoke_signals_hold_lock_restore_v1_and_fail(self) -> None:
        for command, injected in (
            ("persona-release", "signal_activation"),
            ("persona-smoke", "signal_smoke"),
        ):
            for signal_name in ("HUP", "INT", "TERM"):
                with self.subTest(command=command, signal=signal_name), self._harness() as harness:
                    result = harness.run(
                        command,
                        fail_stage=injected,
                        signal_name=signal_name,
                    )

                    self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                    self.assertNotIn("Persona release is running with lezhi-v2.0", result.stdout)
                    calls = harness.calls()
                    stage = f"signal_{signal_name.lower()}"
                    self.assertIn("lock_held_during_signal", calls)
                    self.assertNotIn("lock_reacquired_during_signal", calls)
                    self.assertIn("persona_release restore-pins", calls)
                    self.assertIn(f"--stage {stage} --rollback-status attempted", calls)
                    self.assertIn(f"--stage {stage} --rollback-status succeeded", calls)
                    self.assertFalse(harness.lock.exists())
                    self.assertIn("lezhi-v1.0", harness.environment_text())
                    self.assertIn(_V1_DIGEST, harness.environment_text())

    def test_every_post_pin_activation_failure_restores_v1_and_records_result(self) -> None:
        for stage in (
            "compose_down",
            "compose_up",
            "running_state",
            "identity",
            "chat_id",
            "database_path",
            "smoke_baseline",
            "record_baseline",
        ):
            with self.subTest(stage=stage), self._harness() as harness:
                result = harness.run("persona-release", fail_stage=stage)

                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                calls = harness.calls()
                self.assertIn("persona_release set-pins", calls)
                self.assertIn("persona_release restore-pins", calls)
                self.assertIn(
                    f"--stage {stage} --rollback-status attempted",
                    calls,
                )
                self.assertIn(
                    f"--stage {stage} --rollback-status succeeded",
                    calls,
                )

    def test_every_smoke_failure_restores_v1_and_records_result(self) -> None:
        scenarios = {
            "chat_id": "chat_id",
            "database_path": "database_path",
            "smoke_state": "smoke_state",
            "running_state_smoke": "running_state",
            "smoke_verify": "smoke_verify",
        }
        for injected, recorded in scenarios.items():
            with self.subTest(stage=injected), self._harness() as harness:
                result = harness.run("persona-smoke", fail_stage=injected)

                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                calls = harness.calls()
                self.assertIn("persona_release restore-pins", calls)
                self.assertIn(
                    f"--stage {recorded} --rollback-status attempted",
                    calls,
                )
                self.assertIn(
                    f"--stage {recorded} --rollback-status succeeded",
                    calls,
                )

    def test_failed_rollback_is_recorded_and_never_reported_as_success(self) -> None:
        with self._harness() as harness:
            result = harness.run(
                "persona-smoke",
                fail_stage="smoke_verify",
                fail_rollback=True,
            )

            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            calls = harness.calls()
            self.assertIn("--stage smoke_verify --rollback-status attempted", calls)
            self.assertIn("--stage smoke_verify --rollback-status failed", calls)
            self.assertNotIn("--stage smoke_verify --rollback-status succeeded", calls)

    def _harness(self) -> _ManageHarness:
        return _ManageHarness()


class _ManageHarness:
    def __init__(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.deploy = self.root / "deploy"
        self.bin = self.root / "bin"
        self.deploy.mkdir()
        self.bin.mkdir()
        shutil.copy2(_ROOT / "deploy/manage.sh", self.deploy / "manage.sh")
        (self.deploy / "manage.sh").chmod(0o755)
        (self.deploy / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        self.environment = self.deploy / ".env"
        self.environment.write_text(
            "PERSONA_BUNDLE_PATH=/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v1.0\n"
            f"PERSONA_EXPECTED_SHA256={_V1_DIGEST}\n",
            encoding="utf-8",
        )
        self.lock = self.deploy / "state/persona-release.lock"
        self.log = self.root / "calls.log"
        self._write_executable("docker", _FAKE_DOCKER)
        self._write_executable("python3", _FAKE_PYTHON)
        self._write_executable("sleep", "#!/bin/sh\nexit 0\n")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.temporary.cleanup()

    def run(
        self,
        command: str,
        *,
        fail_stage: str,
        fail_rollback: bool = False,
        signal_name: str = "TERM",
    ) -> subprocess.CompletedProcess[str]:
        arguments = [str(self.deploy / "manage.sh"), command]
        if command == "persona-release":
            report = self.root / "report.json"
            report.write_text("{}\n", encoding="utf-8")
            arguments.extend(
                [
                    "/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0",
                    _V2_DIGEST,
                    str(report),
                ]
            )
        environment = dict(os.environ)
        environment.update(
            {
                "PATH": f"{self.bin}:{environment['PATH']}",
                "CALL_LOG": str(self.log),
                "FAKE_STATE_DIR": str(self.root / "fake-state"),
                "FAIL_STAGE": fail_stage,
                "FAIL_ROLLBACK": "1" if fail_rollback else "0",
                "SIGNAL_NAME": signal_name,
                "EXPECTED_LOCK_DIR": str(self.lock),
            }
        )
        return subprocess.run(
            arguments,
            cwd=self.root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def calls(self) -> str:
        return self.log.read_text(encoding="utf-8")

    def environment_text(self) -> str:
        return self.environment.read_text(encoding="utf-8")

    def _write_executable(self, name: str, content: str) -> None:
        path = self.bin / name
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        path.chmod(0o755)


_FAKE_DOCKER = r"""
    #!/bin/sh
    set -eu
    echo "docker $*" >> "${CALL_LOG}"
    mkdir -p "${FAKE_STATE_DIR}"
    arguments=" $* "
    case "${arguments}" in
      *" config "*) exit 0 ;;
      *" ps --services --filter status=running "*)
        count_file="${FAKE_STATE_DIR}/ps-count"
        count=0
        [ ! -f "${count_file}" ] || count=$(cat "${count_file}")
        count=$((count + 1))
        echo "${count}" > "${count_file}"
        if [ "${FAIL_STAGE}" = "running_state" ] && [ "${count}" -ge 2 ]; then exit 8; fi
        if [ "${FAIL_STAGE}" = "running_state_smoke" ]; then exit 8; fi
        echo telegram-bot
        exit 0
        ;;
      *" logs --no-color --tail=200 telegram-bot "*)
        if [ "${FAIL_STAGE}" = "identity" ]; then
          echo "persona_bundle_loaded persona_id=lezhi persona_version=lezhi-v1.0 persona_digest=25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a"
        else
          echo "persona_bundle_loaded persona_id=lezhi persona_version=lezhi-v2.0 persona_digest=0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603"
          echo "persona_bundle_loaded persona_id=lezhi persona_version=lezhi-v1.0 persona_digest=25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a"
        fi
        exit 0
        ;;
      *" down "*)
        count_file="${FAKE_STATE_DIR}/down-count"
        count=0
        [ ! -f "${count_file}" ] || count=$(cat "${count_file}")
        count=$((count + 1))
        echo "${count}" > "${count_file}"
        if [ "${FAIL_STAGE}" = "compose_down" ] && [ "${count}" -eq 1 ]; then exit 8; fi
        exit 0
        ;;
      *" up --detach --build "*)
        count_file="${FAKE_STATE_DIR}/up-count"
        count=0
        [ ! -f "${count_file}" ] || count=$(cat "${count_file}")
        count=$((count + 1))
        echo "${count}" > "${count_file}"
        if [ "${FAIL_STAGE}" = "compose_up" ] && [ "${count}" -eq 1 ]; then exit 8; fi
        if [ "${FAIL_STAGE}" = "signal_activation" ] && [ "${count}" -eq 1 ]; then
          kill "-${SIGNAL_NAME}" "${PPID}"
          if mkdir "${EXPECTED_LOCK_DIR}" 2>/dev/null; then
            echo lock_reacquired_during_signal >> "${CALL_LOG}"
            rmdir "${EXPECTED_LOCK_DIR}"
          else
            echo lock_held_during_signal >> "${CALL_LOG}"
          fi
        fi
        exit 0
        ;;
      *" smoke-baseline "*)
        [ "${FAIL_STAGE}" != "smoke_baseline" ] || exit 9
        echo 31
        exit 0
        ;;
      *" smoke-verify "*)
        [ "${FAIL_STAGE}" != "smoke_verify" ] || exit 9
        if [ "${FAIL_STAGE}" = "signal_smoke" ]; then
          kill "-${SIGNAL_NAME}" "${PPID}"
          if mkdir "${EXPECTED_LOCK_DIR}" 2>/dev/null; then
            echo lock_reacquired_during_signal >> "${CALL_LOG}"
            rmdir "${EXPECTED_LOCK_DIR}"
          else
            echo lock_held_during_signal >> "${CALL_LOG}"
          fi
        fi
        echo "persona_smoke_passed outcome=sent external_effects=1"
        exit 0
        ;;
    esac
    exit 0
"""


_FAKE_PYTHON = r"""
    #!/bin/sh
    set -eu
    echo "python $*" >> "${CALL_LOG}"
    arguments=" $* "
    environment_file=""
    previous=""
    for argument in "$@"; do
      if [ "${previous}" = "--env-file" ]; then environment_file=${argument}; fi
      previous=${argument}
    done
    case "${arguments}" in
      *" group_llm_agent.persona_release environment-chat-id "*)
        [ "${FAIL_STAGE}" != "chat_id" ] || exit 9
        echo -1001
        ;;
      *" group_llm_agent.persona_release environment-database-path "*)
        [ "${FAIL_STAGE}" != "database_path" ] || exit 9
        echo /app/data/runtime.sqlite3
        ;;
      *" group_llm_agent.persona_release state-smoke-arguments "*)
        [ "${FAIL_STAGE}" != "smoke_state" ] || exit 9
        echo "31 0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603"
        ;;
      *" group_llm_agent.persona_release record-baseline "*)
        [ "${FAIL_STAGE}" != "record_baseline" ] || exit 9
        echo persona_smoke_baseline_recorded
        ;;
      *" group_llm_agent.persona_release preflight "*) echo persona_preflight_passed ;;
      *" group_llm_agent.persona_release set-pins "*)
        printf '%s\n' \
          'PERSONA_BUNDLE_PATH=/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0' \
          'PERSONA_EXPECTED_SHA256=0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603' \
          > "${environment_file}"
        echo persona_pins_updated
        ;;
      *" group_llm_agent.persona_release restore-pins "*)
        [ "${FAIL_ROLLBACK}" != "1" ] || exit 9
        printf '%s\n' \
          'PERSONA_BUNDLE_PATH=/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v1.0' \
          'PERSONA_EXPECTED_SHA256=25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a' \
          > "${environment_file}"
        echo persona_pins_restored
        ;;
      *" group_llm_agent.persona_release record-failure "*) echo persona_release_failure_recorded ;;
    esac
"""


if __name__ == "__main__":
    unittest.main()
