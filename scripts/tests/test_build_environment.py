"""Keep kernel builders independent of ubuntu-latest host migrations."""
from pathlib import Path
import unittest

import yaml


WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"
BUILDERS = ("Build Kernel OnePlus.yml", "build-kernel-original-make.yml")


def read_builder(filename):
    workflow = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
    return workflow["jobs"]["load"]


class BuildEnvironmentTests(unittest.TestCase):
    def test_checkout_follows_workspace_mount_before_repository_use(self):
        for filename in BUILDERS:
            with self.subTest(workflow=filename):
                steps = read_builder(filename)["steps"]
                mounts = [index for index, step in enumerate(steps)
                          if step.get("uses", "").startswith("easimon/maximize-build-space@")]
                checkouts = [index for index, step in enumerate(steps)
                             if step.get("uses", "").startswith("actions/checkout@")]
                self.assertEqual(len(mounts), 1)
                self.assertEqual(len(checkouts), 1)
                self.assertLess(mounts[0], checkouts[0])
                manifest = next(index for index, step in enumerate(steps)
                                if step.get("name") == "Extract OnePlus Manifest Info")
                self.assertLess(checkouts[0], manifest)
                check = steps[checkouts[0] + 1]
                self.assertEqual(check["name"], "Verify build helpers")
                self.assertIn('test -s "$GITHUB_WORKSPACE/scripts/read_kmi_generation.py"',
                              check["run"])

    def test_kernel_builders_pin_ubuntu_2404(self):
        for filename in BUILDERS:
            with self.subTest(workflow=filename):
                self.assertEqual(read_builder(filename)["runs-on"], "ubuntu-24.04")

    def test_both_dependency_installers_use_lz4(self):
        for filename in BUILDERS:
            steps = {step.get("name"): step for step in read_builder(filename)["steps"]}
            installers = {
                "cache": steps["Install Dependencies + APTC"]["with"]["packages"],
                "apt": steps["Install Dependencies"]["run"],
            }
            for installer, text in installers.items():
                with self.subTest(workflow=filename, installer=installer):
                    self.assertIn("lz4", text.split())
                    self.assertNotIn("liblz4-tool", text.split())
                    self.assertIn("libdw-dev", text.split())


if __name__ == "__main__":
    unittest.main()
