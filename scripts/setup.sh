#!/usr/bin/env bash
# Install the pinned toolchain into .tools/ (gitignored) and the Python environment into .venv/.
# Nothing is installed outside the repository except what the tools cache themselves
# (Zener toolchain under ~/Library/Application Support/pcb, uv cache).
# Requires: macOS on Apple Silicon, KiCad 10 in /Applications, uv, curl.
set -euo pipefail
cd "$(dirname "$0")/.."

ZENER_LAUNCHER=0.2.8
ZENER_SHA=7d0ac570e356df2ff57c1c0ee7d7abbaf4fd88d1a96d801c0e7dcf27ed090e8c
FREEROUTING=2.5.0
FREEROUTING_SHA=f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7
JRE_RELEASE=jdk-25.0.5%2B8
JRE_FILE=25.0.5_8
JRE_SHA=72ebd76b502c849e88dea39afae51baf5f82f2b5b1b6389c28ea707b20451bce
KONNECT=0.13.0
KONNECT_SHA=0052ab18add3c3014bcedd327131c2bff79dbac5a1d96e45ca9f6bc2822c93c9

[ "$(uname -s)-$(uname -m)" = "Darwin-arm64" ] || { echo "setup.sh pins macOS arm64 binaries; adapt the pins for $(uname -sm)" >&2; exit 1; }

fetch() { # url sha256 dest
  if [ -f "$3" ] && echo "$2  $3" | shasum -a 256 -c - >/dev/null 2>&1; then return; fi
  mkdir -p "$(dirname "$3")"
  curl -fsSL "$1" -o "$3.part"
  echo "$2  $3.part" | shasum -a 256 -c - >/dev/null || { echo "checksum mismatch: $1" >&2; rm -f "$3.part"; exit 1; }
  mv "$3.part" "$3"
}

mkdir -p .tools/bin .tools/dl

# Zener (`pcb`): launcher only. No shell-profile edits, no URL handler (the upstream installer does both).
fetch "https://pcb.api.diode.computer/pcb/pcb/v$ZENER_LAUNCHER/pcb-aarch64-apple-darwin" "$ZENER_SHA" .tools/dl/pcb-$ZENER_LAUNCHER
install -m 755 .tools/dl/pcb-$ZENER_LAUNCHER .tools/bin/pcb

# Freerouting: the jar plus a private Java runtime. The native "freerouting-cli" build of 2.5.0 crashes
# on every board (GraalVM serialization error, then hangs), so it is not used.
fetch "https://github.com/freerouting/freerouting/releases/download/v$FREEROUTING/freerouting-$FREEROUTING.jar" "$FREEROUTING_SHA" .tools/freerouting.jar
fetch "https://github.com/adoptium/temurin25-binaries/releases/download/$JRE_RELEASE/OpenJDK25U-jre_aarch64_mac_hotspot_$JRE_FILE.tar.gz" "$JRE_SHA" .tools/dl/jre.tar.gz
rm -rf .tools/jre && mkdir -p .tools/jre && tar xzf .tools/dl/jre.tar.gz -C .tools/jre --strip-components 1
cat > .tools/bin/freerouting <<'WRAP'
#!/usr/bin/env bash
t="$(cd "$(dirname "$0")/.." && pwd)"
exec "$t/jre/Contents/Home/bin/java" -Djava.awt.headless=true -jar "$t/freerouting.jar" "$@"
WRAP
chmod +x .tools/bin/freerouting

# Konnect (KiCad MCP server): last AGPL-3.0 release before the project went closed source.
fetch "https://github.com/mixelpixx/Konnect/releases/download/v$KONNECT/konnect-v$KONNECT-aarch64-apple-darwin.tar.gz" "$KONNECT_SHA" .tools/dl/konnect-$KONNECT.tar.gz
mkdir -p .tools/konnect && tar xzf .tools/dl/konnect-$KONNECT.tar.gz -C .tools/konnect
find .tools/konnect -type f -name konnect -exec install -m 755 {} .tools/bin/konnect \;

uv sync --quiet

.tools/bin/pcb --version
.tools/bin/freerouting -h 2>&1 | head -1
.tools/bin/konnect --version
uv run python -c "import build123d; print('build123d', build123d.__version__)"
