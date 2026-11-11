import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "managed_hermes_skills", ROOT / "services/hermes/install-managed-skills.py"
)
assert SPEC is not None and SPEC.loader is not None
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class ManagedSkillsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        shutil.copytree(ROOT / "services/hermes/skills/promotion", self.source)
        self.manifest = self.root / "manifest.json"
        shutil.copyfile(ROOT / "services/hermes/skills/promotion-manifest.json", self.manifest)
        self.destination = self.root / "private" / "skills"

    def install(self):
        return INSTALLER.install(self.source, self.manifest, self.destination)

    def revise(self):
        path = self.source / "promotion-brief/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nA reviewed package revision.\n")
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["files"]["promotion-brief/SKILL.md"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")

    def test_install_and_repeat_preserve_unmanaged_private_state(self):
        sibling = self.destination / "my-private-skill" / "SKILL.md"
        sibling.parent.mkdir(parents=True)
        sibling.write_bytes(b"private unrelated skill")
        memory = self.destination.parent / "memory.md"
        memory.write_bytes(b"private agent memory")
        self.assertEqual(self.install(), "installed")
        installed = self.destination / INSTALLER.PACK_ID
        self.assertEqual(len(list(installed.rglob("SKILL.md"))), 8)
        self.assertEqual(self.install(), "unchanged")
        self.assertEqual(sibling.read_bytes(), b"private unrelated skill")
        self.assertEqual(memory.read_bytes(), b"private agent memory")
        self.assertFalse(list(self.destination.parent.glob(".*.stage-*")))

    def test_corrupt_source_never_creates_or_changes_the_destination(self):
        self.install()
        original = self.destination / INSTALLER.PACK_ID / "promotion-brief/SKILL.md"
        before = original.read_bytes()
        (self.source / "promotion-brief/SKILL.md").write_bytes(b"unreviewed replacement")
        with self.assertRaisesRegex(INSTALLER.PackError, "digest mismatch"):
            self.install()
        self.assertEqual(original.read_bytes(), before)

    def test_manifest_path_traversal_is_refused(self):
        outside = self.root / "keep.md"
        outside.write_bytes(b"keep")
        for name in (".", "../keep.md", "/keep.md", "C:/keep.md", "a//b", "a/./b", "a\\b"):
            with self.subTest(name=name):
                data = {"schema_version": 1, "pack_id": INSTALLER.PACK_ID,
                        "files": {name: hashlib.sha256(b"keep").hexdigest()}}
                self.manifest.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(INSTALLER.PackError):
                    self.install()
                self.assertEqual(outside.read_bytes(), b"keep")
                self.assertFalse(self.destination.exists())

    def test_symlinked_source_file_is_refused(self):
        original = self.source / "promotion-brief/SKILL.md"
        outside = self.root / "outside.md"
        original.rename(outside)
        try:
            original.symlink_to(outside)
        except OSError:
            self.skipTest("Host cannot create symlinks")
        with self.assertRaisesRegex(INSTALLER.PackError, "Symlinks"):
            self.install()
        self.assertFalse(self.destination.exists())

    def test_symlinked_destination_never_changes_another_directory(self):
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_bytes(b"keep")
        self.destination.parent.mkdir(parents=True)
        try:
            self.destination.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Host cannot create symlinks")
        with self.assertRaisesRegex(INSTALLER.PackError, "Symlinked"):
            self.install()
        self.assertEqual(list(outside.iterdir()), [sentinel])

    def test_modified_owned_skill_is_preserved_and_requires_review(self):
        self.install()
        target = self.destination / INSTALLER.PACK_ID / "promotion-brief/SKILL.md"
        target.write_bytes(b"owner's private revision")
        self.revise()
        with self.assertRaisesRegex(INSTALLER.PackError, "digest mismatch"):
            self.install()
        self.assertEqual(target.read_bytes(), b"owner's private revision")

    def test_unmanaged_namespace_and_added_files_are_preserved(self):
        target = self.destination / INSTALLER.PACK_ID
        target.mkdir(parents=True)
        sentinel = target / "private.txt"
        sentinel.write_bytes(b"private")
        with self.assertRaises(INSTALLER.PackError):
            self.install()
        self.assertEqual(sentinel.read_bytes(), b"private")
        sentinel.unlink()
        target.rmdir()
        self.install()
        sentinel.write_bytes(b"private addition")
        with self.assertRaisesRegex(INSTALLER.PackError, "Unmanaged file"):
            self.install()
        self.assertEqual(sentinel.read_bytes(), b"private addition")

    def test_reviewed_revision_replaces_only_owned_files(self):
        self.install()
        self.revise()
        self.assertEqual(self.install(), "installed")
        target = self.destination / INSTALLER.PACK_ID
        self.assertEqual((target / "promotion-brief/SKILL.md").read_bytes(),
                         (self.source / "promotion-brief/SKILL.md").read_bytes())
        self.assertEqual(self.install(), "unchanged")
        self.assertFalse(list(self.destination.parent.glob(".*.previous-*")))

    def test_failed_commit_restores_the_previous_verified_package(self):
        self.install()
        target = self.destination / INSTALLER.PACK_ID / "promotion-brief/SKILL.md"
        before = target.read_bytes()
        self.revise()
        rename = Path.rename

        def fail_commit(path, destination):
            if path.name.startswith(f".{INSTALLER.PACK_ID}.stage-"):
                # Neither candidate nor rollback copy is discoverable as a skill.
                self.assertFalse(list(self.destination.rglob("SKILL.md")))
                raise OSError("simulated commit failure")
            return rename(path, destination)

        with patch.object(Path, "rename", fail_commit), self.assertRaises(OSError):
            self.install()
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(list(self.destination.parent.glob(".*.stage-*")))
        self.assertFalse((self.destination / f".{INSTALLER.PACK_ID}.lock").exists())

    def test_extra_source_files_and_empty_directories_are_refused(self):
        for is_directory in (False, True):
            with self.subTest(is_directory=is_directory):
                extra = self.source / "unreviewed"
                if is_directory:
                    extra.mkdir()
                else:
                    extra.write_bytes(b"not in reviewed package")
                with self.assertRaisesRegex(INSTALLER.PackError, "Unmanaged"):
                    self.install()
                if is_directory:
                    extra.rmdir()
                else:
                    extra.unlink()

    def test_pack_has_native_discoverable_names_and_no_external_requirements(self):
        manifest = INSTALLER._read_manifest(self.manifest)
        INSTALLER.verify_files(self.source, manifest)
        names = set()
        for path in self.source.rglob("SKILL.md"):
            metadata = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
            self.assertEqual(metadata["name"], path.parent.name)
            self.assertLessEqual(len(metadata["name"]), 64)
            self.assertTrue(0 < len(metadata["description"]) <= 1024)
            self.assertNotIn("required_environment_variables", metadata)
            self.assertNotIn("prerequisites", metadata)
            names.add(metadata["name"])
        self.assertEqual(len(names), 8)
        self.assertFalse(list(self.source.rglob("*.py")))
        self.assertFalse(list(self.source.rglob("*.sh")))
