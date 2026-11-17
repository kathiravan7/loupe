#!/bin/bash
# Installe Loupe sur macOS : ~/.loupe (environnement Python + script) et commande `loupe`.
set -e
DIR="$HOME/.loupe"
SRC="$(cd "$(dirname "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import sys; sys.exit(sys.version_info < (3,10))"; then
  echo "Python 3.10+ requis. Installez-le avec : brew install python   (ou xcode-select --install)"
  exit 1
fi

mkdir -p "$DIR"
cp "$SRC/loupe.py" "$DIR/loupe.py"
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --upgrade pip anthropic

# Lanceur appelé par le raccourci clavier
cat > "$DIR/loupe" <<EOF
#!/bin/bash
exec "$DIR/venv/bin/python" "$DIR/loupe.py"
EOF
chmod +x "$DIR/loupe"

# Clé API stockée dans le Trousseau macOS (jamais en clair sur le disque)
if security find-generic-password -s loupe-claude-api >/dev/null 2>&1; then
  read -r -p "Une clé API est déjà enregistrée. La remplacer ? [o/N] " R
else
  R=o
fi
if [[ "$R" =~ ^[oOyY] ]]; then
  read -r -s -p "Collez votre clé API Anthropic (sk-ant-...) : " KEY; echo
  security add-generic-password -U -s loupe-claude-api -a "$USER" -w "$KEY"
fi

echo
echo "✅ Loupe installée. Commande à utiliser dans le raccourci : $DIR/loupe"
