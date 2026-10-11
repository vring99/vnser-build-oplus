# BakaSU 35226 integration

Both `build-kernel-original-make.yml` and `Build Kernel OnePlus.yml` build
BakaSU at `59afa46b325126b12a48234063cd0c2a6b735b57`. The Snapdragon, MTK and
test workflows call the former. This is the same reviewed snapshot used by
GKI_KernelSU_SUSFS, with version calculated from the checked-out HEAD.

The integration scripts and JSON manifests are copied from
GKI_KernelSU_SUSFS. Keep these four files synchronized when updating:

- `scripts/bakasu_selinux.py`
- `scripts/resukisu_35188_selinux.py`
- `config/bakasu.json`
- `config/resukisu-35188-selinux.json`

The historical helper is imported only for its shared patch filter, source
validation and family manifest. These workflows do not invoke its old
`apply` command or apply the 35188 backport.

Before applying SUSFS, the helper verifies and removes only the reviewed
diff blocks for `security/selinux/hooks.c` and `security/selinux/selinuxfs.c`.
All other blocks, including `security/selinux/avc.c`, are preserved. The
upstream BakaSU implementation supplies the SELinux fixes instead.

Before compiling, the helper checks the pinned BakaSU revision and source
hashes, validates original SELinux hook targets and rejects conflicting
legacy hooks or SELinux patch rejections. Only then does it remove the exact
three-line SUSFS suspension notice from `kernel/tools/susfs_compat.mk`.
Other compatibility checks remain active. Unknown SUSFS SELinux changes
fail validation and need review before building.

Supported families: android12-5.10, android13-5.15, android14-6.1,
android15-6.6 and android16-6.12. Both workflows enable KALLSYMS_ALL.
SELinux enforcement and root authorization policy are unchanged. Use the
matching BakaSU manager and enable SELinux Hide when testing that feature.

Run `python -m unittest discover -s scripts/tests -v` (PyYAML required for
workflow tests). Real-source tests use `BAKASU_TEST_SOURCE`,
`SUSFS_TEST_SOURCE` and `AOSP_SELINUX_TEST_SOURCE`, as in GKI_KernelSU_SUSFS.
These checks do not replace full vendor kernel builds or device tests.
