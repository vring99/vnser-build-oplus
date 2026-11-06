"""The supplemental build must only cover the existing 6.12 devices."""
from pathlib import Path
import unittest

import yaml


WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"
TARGETS = {
    "oneplus_ace_6t_Canary",
    "oneplus_15_Canary",
    "oneplus_15t_Canary",
    "oneplus_pad_4_Canary",
    "oneplus_pad_3_pro_Canary",
    "oneplus_ace6_ultra_vring",
}


def read(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


class Kernel612WorkflowTests(unittest.TestCase):
    def test_only_requested_devices_and_version(self):
        workflow = read("Build Kernel OnePlus-6.12.yml")
        inputs = workflow.get("on", workflow.get(True))["workflow_dispatch"]["inputs"]
        self.assertEqual(inputs["BAKASU_VERSION"]["default"], "35270")
        self.assertEqual(inputs["BAKASU_VERSION"]["options"], ["35270"])
        self.assertTrue(inputs["UNI"]["default"])
        self.assertEqual(len(workflow["jobs"]), 1)
        job = next(iter(workflow["jobs"].values()))
        targets = job["strategy"]["matrix"]["include"]
        self.assertEqual({item["file"] for item in targets}, TARGETS)
        self.assertEqual(len(targets), len(TARGETS))
        self.assertFalse(job["strategy"]["fail-fast"])

    def test_same_builder_and_options_as_full_builds(self):
        job = next(iter(read("Build Kernel OnePlus-6.12.yml")["jobs"].values()))
        for filename in ("Build Kernel OnePlus Snapdragon.yml", "Build Kernel OnePlus MTK.yml"):
            parent = next(iter(read(filename)["jobs"].values()))
            self.assertEqual(job["uses"], parent["uses"])
            self.assertEqual(job["secrets"], parent["secrets"])
            self.assertEqual(job["with"], parent["with"])
            for item in parent["strategy"]["matrix"]["include"]:
                if item["file"] in TARGETS:
                    self.assertIn(item, job["strategy"]["matrix"]["include"])


if __name__ == "__main__":
    unittest.main()
