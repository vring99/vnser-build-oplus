"""Exercise the OnePlus SUSFS header repairs by running both workflow scripts."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
BUILDERS = ("Build Kernel OnePlus.yml", "build-kernel-original-make.yml")
BASH = os.environ.get("BAKASU_TEST_BASH", "bash")
CLANG = os.environ.get("SUSFS_TEST_CLANG") or shutil.which("clang")
HEADER = "#include <linux/susfs_def.h>"
TASK = """#include <linux/sched/mm.h>
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
int redirect(int inode) { return SUSFS_IS_INODE_OPEN_REDIRECT(inode); }
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MAP
int mapped(int inode) { return SUSFS_IS_INODE_SUS_MAP(inode); }
#endif
"""
NAMESPACE = """#include <linux/mnt_idmapping.h>
#include "internal.h"
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
int mount_check(void) { return susfs_is_current_ksu_domain() + DEFAULT_KSU_MNT_ID; }
#endif
"""
DECLARATIONS = (
    "extern bool susfs_is_current_ksu_domain(void);",
    "extern struct static_key_true susfs_is_sdcard_android_data_not_decrypted;",
    "#define CL_COPY_MNT_NS BIT(25)",
)
EXEC = """#include <linux/ksm.h>
#ifdef CONFIG_KSU_SUSFS
int exec_check(void) { return susfs_is_current_proc_no_su(); }
#endif
"""


class SusfsHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {}
        for name in BUILDERS:
            workflow = yaml.safe_load(
                (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
            steps = next(iter(workflow["jobs"].values()))["steps"]
            run = next(step["run"] for step in steps
                       if "# Android 16 - 6.12" in step.get("run", ""))
            start = run.index('if [[ "$GKI_V" == "android13-5.15" ]]')
            cls.runs[name, "5.15"] = run[start:run.index("# Android 14 - 6.1")]
            start = run.index("# Android 16 - 6.12")
            cls.runs[name, "6.12"] = run[start:]

    def repair(self, root, builder, family="5.15", sublevel=167, gki=None, sources=None):
        (root / "kernel").mkdir(exist_ok=True)
        source_files = {"fs/proc/task_mmu.c": TASK, "fs/namespace.c": NAMESPACE} if family == "5.15" else {"fs/exec.c": EXEC}
        source_files.update(sources or {})
        source_files["mm/memory.c"] = "#include <linux/vmalloc.h>\nint mem(int inode) { return SUSFS_IS_INODE_SUS_MAP(inode); }\n"
        source_files["include/linux/susfs_def.h"] = "#define SUSFS_IS_INODE_SUS_MAP(inode) (inode)\n"
        for name, source in source_files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [BASH, "-e", "-c", self.runs[builder, family]], cwd=root,
            env=dict(os.environ, CURRENT_SUB=str(sublevel),
                     GKI_V=gki or ("android13-5.15" if family == "5.15" else "android16-6.12")),
            capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return {name: (root / name).read_text(encoding="utf-8") for name in source_files}

    def test_515_repairs_task_and_namespace_across_supported_range(self):
        for builder in BUILDERS:
            for sublevel in (74, 123, 149, 167, 194, 197, 206):
                with self.subTest(builder=builder, sublevel=sublevel), tempfile.TemporaryDirectory() as directory:
                    result = self.repair(Path(directory), builder, sublevel=sublevel)
                    self.assertEqual(result["fs/proc/task_mmu.c"].count(HEADER), 1)
                    namespace = result["fs/namespace.c"]
                    self.assertEqual(namespace.count(HEADER), 1)
                    for declaration in DECLARATIONS:
                        self.assertEqual(namespace.count(declaration), 1)
                    self.assertNotIn("\\n", namespace)

    def test_612_repairs_23_30_38_and_preserves_later_coverage(self):
        for builder in BUILDERS:
            for sublevel in (23, 30, 38, 57, 58, 69):
                with self.subTest(builder=builder, sublevel=sublevel), tempfile.TemporaryDirectory() as directory:
                    result = self.repair(Path(directory), builder, "6.12", sublevel)
                    self.assertEqual(result["fs/exec.c"].count(HEADER), 1)

    def test_other_families_sublevels_and_sources_are_unchanged(self):
        for builder in BUILDERS:
            cases = (("5.15", 73, None), ("5.15", 207, None),
                     ("5.15", 167, "android12-5.10"),
                     ("6.12", 22, None), ("6.12", 23, "android15-6.6"))
            for family, sublevel, gki in cases:
                with self.subTest(builder=builder, family=family, sublevel=sublevel, gki=gki), tempfile.TemporaryDirectory() as directory:
                    result = self.repair(Path(directory), builder, family, sublevel, gki)
                    expected = {"fs/proc/task_mmu.c": TASK, "fs/namespace.c": NAMESPACE} if family == "5.15" else {"fs/exec.c": EXEC}
                    for name, source in expected.items():
                        self.assertEqual(result[name], source)

    def test_alternate_anchors_and_repeated_runs_do_not_duplicate_headers(self):
        for builder in BUILDERS:
            for family, path, source in (("5.15", "fs/proc/task_mmu.c", TASK.replace("sched/mm.h", "sched/sysctl.h")),
                                         ("6.12", "fs/exec.c", EXEC.replace("linux/ksm.h", "linux/dma-buf.h"))):
                with self.subTest(builder=builder, family=family), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    result = self.repair(root, builder, family, 167 if family == "5.15" else 23, sources={path: source})
                    self.assertEqual(result[path].count(HEADER), 1)
                    repeated = self.repair(root, builder, family, 167 if family == "5.15" else 23, sources=result)
                    self.assertEqual(repeated[path], result[path])

    def test_existing_namespace_header_does_not_skip_missing_declarations(self):
        for builder in BUILDERS:
            with self.subTest(builder=builder), tempfile.TemporaryDirectory() as directory:
                result = self.repair(Path(directory), builder, sources={"fs/namespace.c": HEADER + "\n" + NAMESPACE})
                for declaration in DECLARATIONS:
                    self.assertEqual(result["fs/namespace.c"].count(declaration), 1)

    @unittest.skipUnless(CLANG, "Clang not supplied")
    def test_reported_515_and_612_compiler_errors_are_resolved(self):
        for builder in BUILDERS:
            for family, source, relative, defines in (
                ("5.15", TASK, "fs/proc/task_mmu.c", ["CONFIG_KSU_SUSFS_OPEN_REDIRECT", "CONFIG_KSU_SUSFS_SUS_MAP"]),
                ("6.12", EXEC, "fs/exec.c", ["CONFIG_KSU_SUSFS"])):
                with self.subTest(builder=builder, family=family), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    include = root / "include"
                    (include / "linux/sched").mkdir(parents=True)
                    (include / "linux/sched/mm.h").touch()
                    (include / "linux/ksm.h").touch()
                    target = root / relative
                    target.parent.mkdir(parents=True)
                    target.write_text(source, encoding="utf-8")
                    command = [CLANG, "-fsyntax-only", "-std=gnu11", "-Werror", "-I", str(include), str(target)]
                    enabled = ["-D" + define for define in defines]
                    before = subprocess.run(command + enabled, capture_output=True, text=True)
                    self.assertNotEqual(before.returncode, 0)
                    self.assertIn("undeclared", before.stderr)
                    self.repair(root, builder, family, 167 if family == "5.15" else 23)
                    (include / "linux/susfs_def.h").write_text(
                        "#define SUSFS_IS_INODE_SUS_MAP(inode) (inode)\n"
                        "#define SUSFS_IS_INODE_OPEN_REDIRECT(inode) (inode)\n"
                        "static inline int susfs_is_current_proc_no_su(void) { return 0; }\n")
                    for flags in ([], enabled):
                        after = subprocess.run(command + flags, capture_output=True, text=True)
                        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)


if __name__ == "__main__":
    unittest.main()
