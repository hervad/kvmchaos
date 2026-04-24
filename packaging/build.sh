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

# Generate bash completion from the uv venv (--show-completion unavailable in frozen binary)
uv run kvmchaos --show-completion bash > packaging/kvmchaos-bash-completion

# Set up rpmbuild directory tree
mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
cp dist/kvmchaos                       ~/rpmbuild/SOURCES/kvmchaos
cp packaging/kvmchaos-bash-completion  ~/rpmbuild/SOURCES/kvmchaos-bash-completion
cp packaging/kvmchaos.spec             ~/rpmbuild/SPECS/kvmchaos.spec

# Build RPM
rpmbuild -bb ~/rpmbuild/SPECS/kvmchaos.spec

RPM=$(ls ~/rpmbuild/RPMS/x86_64/kvmchaos-*.rpm)
echo "Built: $RPM"
