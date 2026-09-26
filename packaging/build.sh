#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Build self-contained binary
uv run pyinstaller \
  --onefile \
  --name kvmchaos \
  --collect-all kvmchaos \
  --hidden-import=libvirt \
  --distpath dist/ \
  packaging/entrypoint.py

# Set up rpmbuild directory tree
mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
cp dist/kvmchaos        ~/rpmbuild/SOURCES/kvmchaos
cp packaging/kvmchaos.spec ~/rpmbuild/SPECS/kvmchaos.spec

# Build RPM
VERSION="$(uv run python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
rpmbuild -bb --define "pkg_version ${VERSION}" ~/rpmbuild/SPECS/kvmchaos.spec

RPM=$(ls ~/rpmbuild/RPMS/x86_64/kvmchaos-*.rpm)
echo "Built: $RPM"
