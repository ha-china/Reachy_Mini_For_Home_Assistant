# 🔄 How to Split This Into a Separate Repository

This guide explains how to split the `ha/` directory into its own independent GitHub repository.

## 📋 Prerequisites

- Git installed locally
- Admin access to target repository (or create new one)
- All changes in this directory committed

## 🚀 Step-by-Step Guide

### Option 1: Create New Repository (Recommended)

#### 1. Create New Empty Repository

```bash
# On GitHub:
# 1. Go to https://github.com/new
# 2. Repository name: reachy-mini-3d-card
# 3. Description: 3D visualization card for Reachy Mini robot in Home Assistant
# 4. Visibility: Public
# 5. ⚠️ DO NOT initialize with README, .gitignore, or license
# 6. Click "Create repository"
```

#### 2. Push This Directory to New Repository

```bash
# Navigate to ha directory
cd ha/

# Initialize new git repository
git init

# Add all files
git add .

# Initial commit
git commit -m "feat: initial release of Reachy Mini 3D Card v1.0.0

- Real-time 3D visualization with Three.js
- Visual configuration editor (no YAML editing)
- HACS integration support
- Multiple display presets
- Interactive camera controls
- 20Hz real-time data synchronization
"

# Add remote (replace USERNAME with your GitHub username)
git remote add origin https://github.com/USERNAME/reachy-mini-3d-card.git

# Push to main branch
git push -u origin main
```

#### 3. Configure Repository Settings

```bash
# On GitHub repository page:
# 1. Settings → General
# 2. Set topics: home-assistant, hacs, custom-card, reachy-mini, 3d, robot
# 3. Enable: Discussions, Issues, Projects, Wiki
# 4. Set visibility to Public
```

#### 4. Create First Release

```bash
# Tag and push
git tag v1.0.0
git push origin v1.0.0

# GitHub Actions will automatically:
# - Build the package
# - Create release with ZIP file
# - Calculate checksums
```

#### 5. Submit to HACS

```bash
# Go to: https://hacs.xyz/docs/publish/include#submitting-your-project
# 1. Fill out the form:
#    - Repository: https://github.com/USERNAME/reachy-mini-3d-card
#    - Category: Lovelace
# 2. Submit
```

### Option 2: Use Git Subtree (Keep History)

If you want to preserve the commit history:

```bash
# 1. Extract ha directory as a separate branch
git subtree split --prefix=ha -b ha-only

# 2. Create new repository on GitHub (as in Option 1)

# 3. Push the extracted branch
git remote add ha-repo https://github.com/USERNAME/reachy-mini-3d-card.git
git push ha-repo ha-only:main

# 4. In the new repository, rename branch
git branch -M main
git push origin main --force
```

### Option 3: Git Filter-Repo (Clean Split)

For a complete, clean split:

```bash
# Install git-filter-repo
pip install git-filter-repo

# 1. Clone current repository to a temporary location
git clone https://github.com/djhui5710/reachy_mini_ha_voice.git reachy-mini-3d-card-temp
cd reachy-mini-3d-card-temp

# 2. Use git-filter-repo to extract only ha/ directory
git filter-repo --subdirectory-filter ha --force

# 3. Update remote to new repository
git remote set-url origin https://github.com/USERNAME/reachy-mini-3d-card.git

# 4. Push all branches
git push origin --all
git push origin --tags

# 5. Clean up
cd ..
rm -rf reachy-mini-3d-card-temp
```

## 📝 Post-Split Tasks

### 1. Update Parent Repository

After splitting, update the parent repository:

```bash
cd reachy_mini_ha_voice

# Remove ha directory
git rm -r ha/

# Add submodule reference (optional)
git submodule add https://github.com/USERNAME/reachy-mini-3d-card.git ha

# Commit
git commit -m "refactor: move 3D card to separate repository

- Moved ha/ to standalone repository: reachy-mini-3d-card
- Added as git submodule for easier management
- See: https://github.com/USERNAME/reachy-mini-3d-card
"

git push
```

### 2. Update CI/CD Workflows

Update parent repository workflows to exclude ha directory:

```yaml
# .github/workflows/main.yml
on:
  push:
    paths-ignore:
      - 'ha/**'
      - 'docs/**'
```

### 3. Update Documentation

Update README.md in parent repository:

```markdown
## 3D Visualization Card

The 3D visualization card has been moved to its own repository:
**[reachy-mini-3d-card](https://github.com/USERNAME/reachy-mini-3d-card)**

Installation and usage instructions are available there.
```

### 4. Add Badges to New Repository

Add to new repository README.md:

```markdown
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz/)
[![Release](https://img.shields.io/github/v/release/USERNAME/reachy-mini-3d-card)](https://github.com/USERNAME/reachy-mini-3d-card/releases)
[![License](https://img.shields.io/github/license/USERNAME/reachy-mini-3d-card)](LICENSE)
```

## 🔗 Cross-Repository References

### In Parent Repository

Keep a reference to the card repository:

```markdown
<!-- README.md -->

## 🎨 3D Visualization (Separate Repository)

The Home Assistant 3D visualization card is now maintained separately:
- **Repository**: [reachy-mini-3d-card](https://github.com/USERNAME/reachy-mini-3d-card)
- **HACS**: Search for "Reachy Mini 3D Card" in HACS
- **Installation**: One-click install via HACS

### In Card Repository

Reference the parent project:

```markdown
<!-- ha/README.md -->

## 📦 Integration with Reachy Mini HA Voice

This card is designed to work with the [reachy_mini_ha_voice](https://github.com/djhui5710/reachy_mini_ha_voice) project.

It automatically connects to ESPHome entities exposed by the voice assistant application.
```

## ✅ Verification Checklist

After splitting, verify:

- [ ] New repository builds successfully (GitHub Actions passes)
- [ ] All files are present in new repository
- [ ] Release is created automatically
- [ ] HACS submission is accepted
- [ ] Documentation is updated in both repositories
- [ ] CI/CD workflows work independently
- [ ] Links between repositories are correct

## 🔄 Maintenance

### Keep Both Repositories in Sync

If you need to make changes that affect both:

```bash
# In card repository
cd ha/
git checkout -b feature/new-feature
# Make changes
git commit -m "feat: add new feature"
git push
# Create PR and merge

# Update parent if needed
cd ../reachy_mini_ha_voice
git submodule update --remote ha
git commit -m "chore: update 3d card submodule"
git push
```

### Release Coordination

When releasing new versions:

1. **Card Repository First**: Release new version
2. **Update Parent**: Update submodule reference
3. **Tag Parent**: Create tag if needed
4. **Document**: Update both READMEs

## 📞 Support

- **Card Issues**: Report in [reachy-mini-3d-card](https://github.com/USERNAME/reachy-mini-3d-card/issues)
- **Integration Issues**: Report in [reachy_mini_ha_voice](https://github.com/djhui5710/reachy_mini_ha_voice/issues)

## 🎯 Benefits of Splitting

✅ **Independent Release Cycle** - Card can be updated without touching main project
✅ **Focused Repository** - Only card-specific code and issues
✅ **Clear Separation of Concerns** - Voice assistant vs visualization
✅ **Easier HACS Integration** - Smaller, focused repository
✅ **Better Discoverability** - Users can find card directly
✅ **Independent Versioning** - Card versions don't affect main project

## 📚 Additional Resources

- [GitHub: Splitting a subfolder into a new repository](https://github.com/new)
- [Git Filter-Repo Documentation](https://github.com/newren/git-filter-repo/wiki)
- [HACS: Building a Custom Card](https://hacs.xyz/docs/development/basics/custom-card/)
- [Semantic Versioning](https://semver.org/)

---

**Ready to split? Choose Option 1 for the cleanest start! 🚀**
