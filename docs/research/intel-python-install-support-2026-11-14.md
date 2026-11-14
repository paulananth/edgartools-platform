# Intel x86_64 Python installation support

**Research date:** 2026-11-14  
**Scope:** Intel means x86_64 / AMD64. This is a static audit of repository configuration, lockfile artifacts, official documentation, and the active local toolchain selection. No package installation or platform build was run.

## Finding

The project declares CPython `>=3.12`, pins the development interpreter family to 3.12, and uses `uv`. The lockfile contains CPython 3.12 wheels for x86_64 Linux, Intel macOS, and Windows AMD64 across the compiled dependencies reviewed below. The MDM and engine extras also build two local Rust/PyO3 extensions from source. Those extensions use PyO3's stable ABI beginning at Python 3.12, but each wheel remains OS/architecture specific.

**Strongest verified path:** Linux x86_64 with CPython 3.12. CI installs MDM extras on `ubuntu-latest`; the runner image is x64; CI also builds and tests the Rust-backed engine. The deploy image script defaults to `linux/amd64`.

**Intel macOS and Windows:** the Python/uv toolchain and inspected lockfile wheels cover these targets, but this repository has no macOS or Windows CI matrix. Therefore the project-level `uv sync` plus local Rust extension build is plausible from configuration, not verified support. Windows is additionally outside the repository's Unix/Bash-oriented operational workflow.

**Local machine observation:** this machine reports an `arm64` host (`uname -m`), but the selected `uv`, managed Python 3.12 interpreter, and Rust compiler all report `x86_64-apple-darwin`; Python reports `platform.machine() == "x86_64"`. The interpreter/toolchain are internally consistent with each other but do not match the host architecture. This is an x86_64 execution path on an ARM64 host; the checks did not establish which virtualization/emulation mechanism is providing it. To use native Apple Silicon, select/install arm64 builds of both uv and Python, then ensure Rust and installed wheels also target arm64. uv documents `UV_PYTHON_ARCH` for deliberate x86_64 emulation, where all packages must match the interpreter architecture.

## Evidence and concrete matrix

| Intel target | Python 3.12 acquisition / dependency evidence | Local Rust extension build | Repository evidence and conclusion |
|---|---|---|---|
| Linux x86_64 (glibc) | uv supports CPython 3.12 and x86_64 Linux. `uv.lock` contains `pyarrow` `cp312` `manylinux_2_28_x86_64` and `psycopg2-binary` `cp312` `manylinux2014_x86_64` wheels. | `uv sync --frozen --extra mdm` / `--extra mdm-runtime` builds the two local path packages with maturin. CI executes this on Ubuntu. Requires Rust/Cargo and a native C linker/compiler for extension builds. | **Verified in CI** for Ubuntu x64 / Python 3.12. The publishing script defaults to `linux/amd64`. The Arrow wheel requires glibc 2.28 or newer; older Linux needs a compatible alternative/build path. |
| macOS Intel x86_64 | uv Tier 1 supports macOS x86_64 and manages CPython 3.12. Lock includes Intel macOS wheels for compiled dependencies including `pyarrow`, `psycopg2-binary`, `numpy`, `pandas`, and `cryptography`. Python.org's Python 3.12 release offers a universal2 macOS installer. | Local maturin/PyO3 build is supported by upstream toolchains in principle. The project has no macOS build/test job, so this exact extras build has **not** been qualified here. | **Dependency and interpreter artifacts confirmed; project build unverified.** Need macOS 12+ for the locked Arrow wheel. Use a native x86_64 Python on Intel Mac; on Apple Silicon emulation is possible but all native packages must match x86_64. |
| Windows x86_64 / AMD64 | uv Tier 1 supports Windows x86_64 and manages CPython 3.12. Lock includes `win_amd64` wheels for compiled dependencies including `pyarrow`, `psycopg2-binary`, `numpy`, `pandas`, and `cryptography`. Python 3.12 official docs list 64-bit Windows installers. | Maturin/PyO3 supports Windows, but this repo does not build/test its local extensions on Windows. A Windows Rust/MSVC toolchain may be needed for source builds. | **Dependency and interpreter artifacts confirmed; project build unverified.** CI and operational scripts use Ubuntu and Bash; Windows user workflows are not established by this evidence. |

### Reproduction commands (not run)

From the repository root, the configured interpreter is 3.12 (`.python-version`) and `pyproject.toml` requires Python `>=3.12`. For a normal local MDM runtime install, the repository's documented setup is:

```sh
uv sync --extra s3 --extra mdm-runtime
```

On an x86_64 Python host, uv selects that host's compatible dependencies and builds the local Maturin projects. To explicitly request uv-managed x86_64 Python in an emulated environment, set `UV_PYTHON_ARCH=x86_64`; uv documents this for macOS/Windows-on-ARM emulation and requires all installed packages to match the interpreter architecture. This variable is unnecessary on a native Intel host.

For the deployable Linux image, the repository's script defaults to `--platform linux/amd64`; its dependency Dockerfiles compile the Rust extension wheels in a Rust builder stage and install those wheels into Python 3.12 Debian Bookworm. That image path is specifically Linux/AMD64, not an Intel macOS or Windows deployment image.

## Confirmed repository facts

- [`pyproject.toml`](../../pyproject.toml): `requires-python = ">=3.12"`; runtime extras `mdm`, `mdm-runtime`, and `engine` include local path packages `source-contract` and `edgartools-control-core`; `.python-version` is `3.12`.
- [`crates/source-contract/pyproject.toml`](../../crates/source-contract/pyproject.toml) and [`crates/control-contract/pyproject.toml`](../../crates/control-contract/pyproject.toml): Maturin/PyO3 build backends and Python `>=3.12`.
- Both Rust crate manifests select PyO3 `abi3-py312`. This gives Python ABI compatibility from 3.12 upward for a compatible built wheel; it does **not** make a Linux wheel usable on macOS/Windows or make x86_64 binaries usable on ARM.
- [`uv.lock`](../../uv.lock): locked x86_64 CPython 3.12 wheels are present for compiled dependencies including `pyarrow`, `psycopg2-binary`, `numpy`, `pandas`, `cryptography`, `cffi`, `greenlet`, `duckdb`, `lxml`, `pymssql`, and PyYAML on the relevant Intel platforms. Wheel metadata is dependency artifact evidence; it does not prove the local project extensions or complete environment install on those targets.
- [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml): all jobs use `ubuntu-latest`; Python setup specifies 3.12; MDM and engine jobs run `uv sync` with the corresponding extras. There is no macOS/Windows matrix or declared `required-environments` list in `pyproject.toml`.
- [`infra/scripts/publish-warehouse-image.sh`](../../infra/scripts/publish-warehouse-image.sh): the default target is `linux/amd64`. [`Dockerfile.mdm-deps`](../../Dockerfile.mdm-deps) builds the local Rust wheels in a Linux builder stage.

## Gaps and assumptions

1. **No local installation/build verification:** the matrix is based on repository metadata and artifact tags, not an executed install. It does not prove that the whole dependency graph or local Rust crates build on macOS/Windows.
2. **Lockfile artifact audit is metadata-only:** the review identified Intel wheel tags for compiled dependencies in the lockfile, but did not install each extra or prove every package selected in each environment will install and run successfully.
3. **No declared platform coverage contract:** `pyproject.toml` does not set `tool.uv.required-environments`. Adding it would make uv enforce that resolved dependencies have distributions for specified targets, but it cannot validate this repository's local Rust build and should follow a deliberate platform-support decision.
4. **CI label moves over time:** current GitHub runner documentation identifies `ubuntu-latest` as x64, but `-latest` can move to a new OS release. Pin a specific runner label if OS-version reproducibility becomes a requirement.
5. **Python minor-version ceiling is not pinned:** `requires-python >=3.12` permits later Python minors. CI currently validates 3.12 only. The PyO3 `abi3-py312` setting is not proof that all other dependencies and project code support every future Python release.
6. **Host/interpreter architecture mismatch:** on the inspected ARM64 Mac, uv, Python, and Rust are x86_64. A native Apple Silicon installation should use matching ARM64 toolchain components; mixing x86_64 and ARM64 extension modules or wheels is not a valid native environment.

## Primary sources

- uv platform support (Tier 1 includes Linux x86_64, macOS x86_64 and Windows x86_64; Linux libc requirements): <https://docs.astral.sh/uv/reference/policies/platforms/>
- uv Python support (CPython and Python 3.12 Tier 1): <https://docs.astral.sh/uv/reference/policies/python/>
- uv managed interpreters, architecture selection, and x86_64 emulation/package architecture matching: <https://docs.astral.sh/uv/concepts/python-versions/>
- uv `UV_PYTHON_ARCH` environment variable: <https://docs.astral.sh/uv/reference/environment/#uv_python_arch>
- uv `required-environments` project configuration: <https://docs.astral.sh/uv/concepts/projects/config/#required-environments>
- PyO3 stable ABI and `abi3` minimum-version features: <https://pyo3.rs/v0.25.0/building-and-distribution> and <https://pyo3.rs/v0.25.0/features>
- Maturin supported platforms and wheel architecture/platform tagging: <https://www.maturin.rs/platform_support> and <https://www.maturin.rs/tutorial.html>
- Python Packaging User Guide, platform compatibility tags and architecture matching: <https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/>
- Official Python 3.12.0 release artifacts (macOS universal2 and Windows 64-bit): <https://www.python.org/downloads/release/python-3120/>
- Python 3.12 Windows install documentation: <https://docs.python.org/3.12/using/windows.html>
- GitHub Actions runner architecture table (current runner labels): <https://github.com/actions/runner-images>

