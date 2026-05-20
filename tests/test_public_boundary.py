from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


def load_public_boundary_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "check-public-boundary.py"
    spec = importlib.util.spec_from_file_location("check_public_boundary", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PublicBoundaryCheckTests(unittest.TestCase):
    def test_candidate_files_skips_ignored_private_configs(self) -> None:
        checker = load_public_boundary_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config"
            config.mkdir()
            private_marker = "PRIVATE_" + "TERM\n"
            (config / "sources.example.yaml").write_text("name: example\n", encoding="utf-8")
            (config / "private-sources.yaml").write_text(private_marker, encoding="utf-8")
            (config / "service.local.yaml").write_text(private_marker, encoding="utf-8")

            with changed_directory(root):
                files = {checker.normalize_path(path) for path in checker.candidate_files(Path("."), ("config",))}

            self.assertIn("config/sources.example.yaml", files)
            self.assertNotIn("config/private-sources.yaml", files)
            self.assertNotIn("config/service.local.yaml", files)

    def test_private_config_markers_are_not_scanned(self) -> None:
        checker = load_public_boundary_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config"
            config.mkdir()
            (config / "sources.example.yaml").write_text("name: example\n", encoding="utf-8")
            (config / "private-sources.yaml").write_text("PRIVATE_" + "TERM\n", encoding="utf-8")

            with changed_directory(root):
                files = list(checker.candidate_files(Path("."), ("config",)))
                findings = list(checker.scan_files(files, checker.BUILT_IN_RULES, checker.ALLOWLIST))

            self.assertEqual(findings, [])


class changed_directory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.previous = Path.cwd()

    def __enter__(self) -> None:
        os.chdir(self.path)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        os.chdir(self.previous)
