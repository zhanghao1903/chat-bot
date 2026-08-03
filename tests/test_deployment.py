from __future__ import annotations

import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


class DockerfileTests(unittest.TestCase):
    def test_runtime_dependencies_are_installed(self) -> None:
        dockerfile = (_ROOT / "deploy/Dockerfile").read_text(encoding="utf-8")

        self.assertIn("python -m pip install --no-cache-dir .", dockerfile)
        self.assertNotIn("--no-deps", dockerfile)


if __name__ == "__main__":
    unittest.main()
