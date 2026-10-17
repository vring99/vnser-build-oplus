from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
BUILDERS = {"build-kernel-original-make.yml", "Build Kernel OnePlus.yml"}
FORWARD = "${{ inputs.UNI }}"


def events(workflow):
    return workflow.get("on", workflow.get(True, {}))


def callees(workflow):
    for job in workflow.get("jobs", {}).values():
        uses = job.get("uses", "")
        if uses.startswith("./.github/workflows/"):
            yield uses.removeprefix("./.github/workflows/"), job


class UnicodeToggleTests(unittest.TestCase):
    def test_pro_workflow_names_and_cleanup_choices_match(self):
        names = {workflow["name"] for workflow in self.workflows.values()}
        cleanup = events(self.workflows["delete.yml"])["workflow_dispatch"]["inputs"]
        choices = next(schema["options"] for schema in cleanup.values() if "options" in schema)
        for choice in choices:
            self.assertIn("bakasu-pro", choice)
            self.assertIn(choice, names)

    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in (ROOT / ".github/workflows").glob("*.yml")
        }
        cls.chain = set(BUILDERS)
        while True:
            callers = {
                name for name, workflow in cls.workflows.items()
                if any(target in cls.chain for target, _ in callees(workflow))
            }
            expanded = cls.chain | callers
            if expanded == cls.chain:
                break
            cls.chain = expanded

    def assert_toggle_schema(self, workflow, event):
        schema = (events(workflow)[event] or {}).get("inputs", {}).get("UNI")
        self.assertIsNotNone(schema, f"missing {event} Unicode toggle")
        self.assertEqual(schema["type"], "boolean")
        self.assertIs(schema.get("default"), True)
        self.assertFalse(schema.get("required", False))

    def test_both_builders_enable_unicode_by_default(self):
        for name in BUILDERS:
            with self.subTest(workflow=name):
                self.assert_toggle_schema(self.workflows[name], "workflow_call")

    def test_every_manual_build_entrypoint_exposes_toggle(self):
        for name in self.chain - BUILDERS:
            with self.subTest(workflow=name):
                self.assert_toggle_schema(self.workflows[name], "workflow_dispatch")

    def test_intermediate_reusable_workflows_accept_toggle(self):
        for name in self.chain - BUILDERS:
            if "workflow_call" in events(self.workflows[name]):
                with self.subTest(workflow=name):
                    self.assert_toggle_schema(self.workflows[name], "workflow_call")

    def test_all_callers_preserve_false_without_truthy_fallback(self):
        for name in self.chain:
            for target, job in callees(self.workflows[name]):
                if target in self.chain:
                    with self.subTest(workflow=name, target=target):
                        self.assertEqual(job.get("with", {}).get("UNI"), FORWARD)

    def test_only_unicode_patch_is_guarded_in_both_builders(self):
        runs = []
        for name in BUILDERS:
            steps = self.workflows[name]["jobs"]["load"]["steps"]
            guarded = [step for step in steps if "inputs.UNI" in step.get("if", "")]
            with self.subTest(workflow=name):
                self.assertEqual(len(guarded), 1)
                self.assertEqual(guarded[0]["if"], "inputs.UNI")
                self.assertIn("unicode_bypass_fix_6.1-.patch", guarded[0]["run"])
                self.assertIn("unicode_bypass_fix_6.1+.patch", guarded[0]["run"])
                runs.append(guarded[0]["run"])
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0], runs[1])

    def test_kpm_enablement_stays_disabled(self):
        for name in BUILDERS:
            steps = self.workflows[name]["jobs"]["load"]["steps"]
            active = "\n".join(line for step in steps for line in step.get("run", "").splitlines()
                               if not line.lstrip().startswith("#"))
            with self.subTest(workflow=name):
                self.assertNotIn('echo "CONFIG_KPM=y"', active)

    def test_build_summary_records_toggle(self):
        for name in BUILDERS:
            steps = self.workflows[name]["jobs"]["load"]["steps"]
            with self.subTest(workflow=name):
                self.assertTrue(any(FORWARD in step.get("run", "") for step in steps))


if __name__ == "__main__":
    unittest.main()
