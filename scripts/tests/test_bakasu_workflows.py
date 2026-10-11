import os
from pathlib import Path
import subprocess
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import bakasu_selinux as upstream


class WorkflowTests(unittest.TestCase):
    def test_both_build_paths_validate_before_compiling(self):
        commands = []
        for name in ("build-kernel-original-make.yml", "Build Kernel OnePlus.yml"):
            with self.subTest(workflow=name):
                workflow = yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
                job = workflow["jobs"]["load"]
                self.assertEqual(job["env"]["BAKASU_COMMIT"], upstream.load_config()["commit"])
                steps = job["steps"]
                setup = next(s for s in steps if s["name"] == "Add BakaSU 35226")
                patch = next(s for s in steps if s["name"] == "Apply Patches SukiSU Ultra")
                verify = next(s for s in steps if s["name"] == "Validate BakaSU SUSFS integration")
                build = next(s for s in steps if s.get("id") == "fast_build")
                self.assertLess(steps.index(setup), steps.index(patch))
                self.assertLess(steps.index(patch), steps.index(verify))
                self.assertLess(steps.index(verify), steps.index(build))
                self.assertNotIn("if", verify)
                self.assertIn("Baka-SU/BakaSU/$BAKASU_COMMIT/kernel/setup.sh", setup["run"])
                self.assertIn('bash "$RUNNER_TEMP/bakasu-setup.sh" "$BAKASU_COMMIT"', setup["run"])
                self.assertIn('git -C KernelSU rev-parse HEAD', setup["run"])
                self.assertIn('git rev-list --count HEAD', setup["run"])
                self.assertIn('check-source', setup["run"])
                self.assertNotIn('|| true', setup["run"] + verify["run"])
                self.assertIn('filter-susfs', patch["run"])
                self.assertIn('--output "${SUSFS_PATCH}.bakasu"', patch["run"])
                self.assertIn('patch -p1 < "${SUSFS_PATCH}.bakasu"', patch["run"])
                self.assertIn('--enable KALLSYMS --enable KALLSYMS_ALL', verify["run"])
                self.assertIn('--susfs true', verify["run"])
                self.assertIn('$GITHUB_WORKSPACE/scripts/bakasu_selinux.py', verify["run"])
                runs = "\n".join(s.get("run", "") for s in steps)
                self.assertNotIn('bakasu_35188_selinux.py', runs)
                self.assertIn('CONFIG_CMDLINE_EXTEND=y', runs)
                self.assertIn('module_blacklist=inte', runs)
                commands.append((setup["run"], verify["run"]))
        self.assertEqual(commands[0], commands[1])

    def test_snapdragon_mtk_and_test_use_updated_builder(self):
        for name in ("Build Kernel OnePlus Snapdragon.yml", "Build Kernel OnePlus MTK.yml",
                     "Build Kernel OnePlus-TEST.yml"):
            with self.subTest(workflow=name):
                workflow = yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
                builders = [job["uses"] for job in workflow["jobs"].values() if "uses" in job]
                self.assertIn("./.github/workflows/build-kernel-original-make.yml", builders)

    @unittest.skipUnless(os.environ.get("BAKASU_TEST_SOURCE"), "real BakaSU source not supplied")
    def test_checkout_contains_all_cli_dependencies(self):
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/bakasu_selinux.py"), "check-source",
            "--ksu", os.environ["BAKASU_TEST_SOURCE"],
        ], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(upstream.load_config()["version_code"]), result.stdout)


@unittest.skipUnless(os.environ.get("SUSFS_TEST_SOURCE"), "real SUSFS sources not supplied")
class RealSusfsTests(unittest.TestCase):
    def test_all_five_families_preserve_every_other_block(self):
        families = upstream.integration.load_config()["families"]
        self.assertEqual(set(families), {
            "android12-5.10", "android13-5.15", "android14-6.1", "android15-6.6", "android16-6.12",
        })
        for family, info in families.items():
            with self.subTest(family=family):
                data = subprocess.check_output([
                    "git", "-C", os.environ["SUSFS_TEST_SOURCE"], "show",
                    f"{info['susfs_commit']}:kernel_patches/50_add_susfs_in_gki-{family}.patch",
                ])
                result = upstream.integration.filter_patch(data, info["legacy_blocks"])
                chunks = data.split(b"diff --git ")
                expected = [chunks[0]]
                for chunk in chunks[1:]:
                    header = chunk.splitlines()[0]
                    if not any(header.startswith(f"a/{name} b/{name}".encode())
                               for name in upstream.integration.LEGACY_PATHS):
                        expected.append(b"diff --git " + chunk)
                self.assertEqual(result, b"".join(expected))
                self.assertIn(b"diff --git a/security/selinux/avc.c", result)
                changed = data.replace(b"diff --git a/security/selinux/hooks.c", b"diff --git a/unknown.c")
                with self.assertRaises(ValueError):
                    upstream.integration.filter_patch(changed, info["legacy_blocks"])


if __name__ == "__main__":
    unittest.main()
