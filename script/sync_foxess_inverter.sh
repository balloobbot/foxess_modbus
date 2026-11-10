#!/bin/sh
# Copy the foxess-inverter library into the integration. It is vendored until
# it is published to PyPI.
set -e
cd "$(dirname "$0")/.."
rsync -a --delete --exclude __pycache__ "${1:-../foxess-inverter}/src/foxess_inverter/" custom_components/foxess_modbus/foxess_inverter/
