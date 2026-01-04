#!/bin/bash

# Build script for Reachy Mini 3D Card
# Creates a HACS-compatible release package

set -e

VERSION=$(node -p "require('./package.json').version")
DIST_DIR="dist"
BUILD_DIR="build"
ZIP_FILE="reachy-mini-3d-card.zip"

echo "🔨 Building Reachy Mini 3D Card v${VERSION}"

# Clean previous builds
rm -rf "$DIST_DIR" "$BUILD_DIR"
mkdir -p "$DIST_DIR"

# Install dependencies
echo "📦 Installing dependencies..."
npm install

# Build JavaScript bundle
echo "🔧 Building JavaScript bundle..."
npx rollup -c

# Create distribution structure
echo "📁 Creating distribution structure..."
mkdir -p "$BUILD_DIR"

# Copy main card file
cp reachy-mini-3d-card.js "$BUILD_DIR/"

# Copy assets
echo "📦 Copying assets..."
cp -r assets "$BUILD_DIR/"

# Create info file
cat > "$BUILD_DIR/info.md" << EOF
# Reachy Mini 3D Card

Version: ${VERSION}
Author: djhui5710
License: Apache-2.0

## Installation

1. Download this repository
2. Extract to your Home Assistant www directory
3. Add to Lovelace resources:

\`\`\`yaml
lovelace:
  resources:
    - url: /local/reachy-mini-3d-card/reachy-mini-3d-card.js
      type: module
\`\`\`

4. Add to dashboard:

\`\`\`yaml
type: custom:reachy-mini-3d-card
entity_prefix: reachy_mini
\`\`\`

## Configuration

Click the ⚙️ icon in the card to open the visual configuration editor.
No YAML editing required!
EOF

# Create ZIP archive
echo "📦 Creating ZIP archive..."
cd "$BUILD_DIR"
zip -r "../$DIST_DIR/$ZIP_FILE" *
cd ..

# Calculate checksums
echo "🔐 Calculating checksums..."
cd "$DIST_DIR"
sha256sum "$ZIP_FILE" > SHA256SUMS
md5sum "$ZIP_FILE" > MD5SUMS
cd ..

echo "✅ Build complete!"
echo ""
echo "Output files:"
echo "  - $DIST_DIR/$ZIP_FILE"
echo "  - $DIST_DIR/SHA256SUMS"
echo "  - $DIST_DIR/MD5SUMS"
echo ""
echo "To test locally:"
echo "  1. Copy $DIST_DIR/$ZIP_FILE to Home Assistant www directory"
echo "  2. Extract: unzip $ZIP_FILE"
echo "  3. Add resource: /local/reachy-mini-3d-card/reachy-mini-3d-card.js"
echo ""
echo "To release to GitHub:"
echo "  git tag v${VERSION}"
echo "  git push origin v${VERSION}"
echo "  GitHub Actions will automatically create the release"
