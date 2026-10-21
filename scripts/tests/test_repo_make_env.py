"""Keep direct Make builds independent of a foreign Kleaf environment script."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
BUILDERS = ("Build Kernel OnePlus.yml", "build-kernel-original-make.yml")
BASH = os.environ.get("BAKASU_TEST_BASH", "bash")


class RepoMakeEnvironmentTests(unittest.TestCase):
    def test_repo_toolchain_and_custom_timestamp_survive_direct_make_setup(self):
        for builder in BUILDERS:
            workflow = yaml.safe_load(
                (ROOT / ".github/workflows" / builder).read_text(encoding="utf-8"))
            steps = next(iter(workflow["jobs"].values()))["steps"]
            run = next(step["run"] for step in steps if step.get("id") == "fast_build")
            # Exercise the real setup before the first Make invocation.
            run = run[:re.search(r"^make ", run, flags=re.MULTILINE).start()]
            values = {"env.KERNEL_VERSION": "6.1", "env.KANDROID_VERSION": "android14",
                      "env.ENABLE_RUST": "false", "env.RUSTC_VERSION": "",
                      "inputs.FILE": "oneplus_ace5_race", "env.CPU": "mt6989",
                      "env.CPUD": "pineapple", "env.BUILD_METHOD": "gki",
                      "env.TKERNEL_VERSION": "6.1.115"}
            run = re.sub(r"\$\{\{\s*([^{}]*?)\s*\}\}",
                         lambda match: values[match[1]], run)
            with self.subTest(builder=builder), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                platform = root / "kernel_workspace/kernel_platform"
                common = platform / "common"
                common.mkdir(parents=True)
                (common / "build.config.common").write_text(
                    "CLANG_PREBUILT_BIN=prebuilts/clang/host/linux-x86/clang-r487747c/bin\n")
                clang = platform / "prebuilts/clang/host/linux-x86/clang-r487747c/bin"
                clang.mkdir(parents=True)
                (root / "foreign_setup").write_text(
                    'export KBUILD_BUILD_TIMESTAMP="foreign timestamp"\n'
                    'export SOURCE_DATE_EPOCH=0\n'
                    'export CLANG_PREBUILT_BIN="wrong-clang/bin"\n'
                    'export KERNEL_DIR="$PWD/$KERNEL_DIR"\n')
                prelude = '''
GITHUB_WORKSPACE=$(pwd)
export GITHUB_WORKSPACE
export KERNEL_DIR="$GITHUB_WORKSPACE/kernel_workspace/kernel-6.1"
original_kernel_dir="$KERNEL_DIR"
curl() {
    printf 'download attempted\n' >> "$GITHUB_WORKSPACE/downloads"
    cp "$GITHUB_WORKSPACE/foreign_setup" "${@: -1}"
}
clang() { :; }
'''
                checks = '''
test "$KBUILD_BUILD_TIMESTAMP" = 'Mon Aug 18 09:30:24 UTC 2024' || exit 71
test "$SOURCE_DATE_EPOCH" = 1723973424 || exit 72
test "$KERNEL_DIR" = "$original_kernel_dir" || exit 73
test ! -e "$GITHUB_WORKSPACE/downloads" || exit 74
test "$KBUILD_BUILD_HOST" = build-host || exit 76
test "$KBUILD_BUILD_USER" = build-user || exit 77
test "$KBUILD_GENDWARFKSYMS_STABLE" = 1 || exit 78
case "$PATH" in
    "$GITHUB_WORKSPACE/kernel_workspace/kernel_platform/prebuilts/clang/host/linux-x86/clang-r487747c/bin:"* | \
    "/usr/lib/ccache:$GITHUB_WORKSPACE/kernel_workspace/kernel_platform/prebuilts/clang/host/linux-x86/clang-r487747c/bin:"*) ;;
    *) exit 75 ;;
esac
'''
                result = subprocess.run([BASH, "-e", "-c", prelude + run + checks],
                    cwd=root, capture_output=True, encoding="utf-8",
                    env=dict(os.environ, KERNEL_REPOS="", ENABLE_RUST="false",
                             KBUILD_BUILD_TIMESTAMP="Mon Aug 18 09:30:24 UTC 2024",
                             SOURCE_DATE_EPOCH="1723973424"))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
