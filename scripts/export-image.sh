#!/bin/sh
# Construit l'image sur un PC connecté à Internet puis l'exporte dans un fichier .tar
# à copier sur le NAS (utile si le NAS n'a pas accès à Internet).
#   ./scripts/export-image.sh             -> scenario-comparateur-1.0.0.tar
# Sur le NAS :  docker load -i scenario-comparateur-1.0.0.tar && docker compose up -d
set -eu
cd "$(dirname "$0")/.."
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' app/__init__.py)
# Le NAS peut avoir un processeur différent du PC (ex. ARM) : PLATFORM=linux/arm64 ./scripts/export-image.sh
PLATFORM=${PLATFORM:-linux/amd64}
docker build --platform "$PLATFORM" -t "scenario-comparateur:$VERSION" .
docker save -o "scenario-comparateur-$VERSION.tar" "scenario-comparateur:$VERSION"
echo "Image exportée : scenario-comparateur-$VERSION.tar ($PLATFORM)"
