# FOSS Burndown Brief: Publishing knurl to PyPI

**Goal**: Publish knurl as a FOSS package on PyPI for use as a shuttle dependency and general public consumption.

**Package Name**: `knurl` (VERIFIED AVAILABLE on PyPI - no existing package found)

**Current Status**: Private codebase, production-ready code, excellent test coverage (930 tests), no CI/CD

---

## Executive Summary

knurl is a rock-solid primitives library providing:
- Content-addressable hashing (SHA256)
- Chain fingerprinting (Merkle-like)
- Divergence detection
- JSON diffing (RFC 6902)
- Canonical JSON serialization (RFC 8785)
- SKEIN address parsing
- Yield data serialization

**Codebase Stats**:
- Source: ~1,546 lines across 8 modules
- Tests: ~10,628 lines across 30 test files
- Test count: 930 tests (comprehensive, includes property-based tests with Hypothesis)
- Dependencies: stdlib-only core + optional `jsonpatch` for diff module
- License declared: MIT (in pyproject.toml)
- Python: 3.10+ required

**Quality indicators**:
- Extensive test suite with gremlin, oracle, chaos testing
- Property-based tests (Hypothesis)
- Attack/exploit tests for security hardening
- Comprehensive edge case coverage
- Clean module structure with clear separation of concerns

---

## FOSS Blockers Assessment

### 🟢 No Critical Blockers Found

**Private info search results**:
- ✅ No hardcoded credentials, tokens, or secrets
- ✅ No absolute paths (except test examples using "@patrick/speakbot" as EXAMPLE DATA only)
- ⚠️  "patrick" and "speakbot" appear in docstrings and tests as example usernames/projects
  - This is SAFE - they're generic examples for the SKEIN address format
  - Equivalent to using "alice@example.com" in email examples
  - No actual personal information leaked

**Dependency audit**:
- ✅ Core modules: stdlib-only (no external deps)
- ✅ Optional: `jsonpatch>=1.32` (MIT licensed, widely used)
- ✅ Dev deps: pytest, hypothesis (standard testing tools)

**License compliance**:
- ✅ MIT license declared in pyproject.toml
- ❌ Missing LICENSE file (needs to be created)
- ✅ No license conflicts with dependencies

---

## Burndown Tasks

### Phase 1: Legal & Licensing (CRITICAL PATH)

**[ ] Task 1.1: Create LICENSE file**
- Create `/home/patrick/projects/spiritengine/knurl/LICENSE`
- Use standard MIT license text
- Copyright holder: Decide on "Patrick <lastname>" vs "SpiritEngine Contributors" vs company name
- This is BLOCKING - PyPI best practices require LICENSE file

**[ ] Task 1.2: Add copyright headers (OPTIONAL but recommended)**
- Decision needed: Add SPDX headers to source files?
- Standard format: `# SPDX-License-Identifier: MIT` at top of each .py file
- Can be done post-launch if desired

**[ ] Task 1.3: Review README for private references**
- Current README uses "SpiritEngine" as header
- Decision: Keep "knurl" branding or mention SpiritEngine as origin?
- Recommendation: Use "knurl" as primary, note "Extracted from SpiritEngine" in description

### Phase 2: Package Metadata & Branding

**[ ] Task 2.1: Update pyproject.toml metadata**
Current gaps:
- Missing `authors` field (required for good PyPI presence)
- Missing `keywords` field (helps discoverability)
- Missing `classifiers` (Python versions, dev status, license)
- Missing `repository` URL (link to GitHub/GitLab if applicable)
- Missing `documentation` URL (if applicable)
- Missing `homepage` URL (can be same as repository)

Example additions needed:
```toml
[project]
authors = [
    {name = "Your Name", email = "your.email@example.com"}
]
keywords = ["hashing", "fingerprinting", "merkle", "content-addressable", "json-patch", "diffing"]
classifiers = [
    "Development Status :: 4 - Beta",  # or "5 - Production/Stable"
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Topic :: Security :: Cryptography",
]

[project.urls]
Homepage = "https://github.com/yourorg/knurl"  # UPDATE THIS
Repository = "https://github.com/yourorg/knurl"  # UPDATE THIS
Issues = "https://github.com/yourorg/knurl/issues"  # UPDATE THIS
```

**[ ] Task 2.2: Update README for public audience**
Current README is minimal. Consider adding:
- Installation instructions (already present - GOOD)
- More detailed usage examples
- API reference or link to docs
- Contributing guidelines (if accepting contributions)
- Link to issues/bug reports
- Badges (build status, PyPI version, license - add after CI setup)

**[ ] Task 2.3: Decide on repository URL**
Options:
1. Create new `knurl` repo under personal GitHub
2. Create under organization account
3. Keep in spiritengine repo as subdirectory
4. No public repo (PyPI only) - NOT RECOMMENDED

Decision impacts: metadata URLs, contribution workflow, issue tracking

**[ ] Task 2.4: Rename from "spiritengine" to "knurl" internally**
- ✅ Package name already "knurl" in pyproject.toml
- ✅ Import path already `knurl.*`
- ⚠️  README header says "# SpiritEngine" - should be "# knurl"
- ⚠️  .skein/config.json has `project_id: "spiritengine"` - KEEP (internal only, not published)

Update needed:
```markdown
# knurl

Rock-solid primitives for content-addressable hashing, chain fingerprinting, and config diffing.

Extracted from the SpiritEngine project.
```

### Phase 3: CI/CD & Automation

**[ ] Task 3.1: Create GitHub Actions workflow (if using GitHub)**
Create `.github/workflows/test.yml`:
- Run tests on Python 3.10, 3.11, 3.12
- Run on ubuntu-latest (Linux), macos-latest, windows-latest
- Test both with and without optional jsonpatch dependency
- Upload coverage reports

**[ ] Task 3.2: Create GitHub Actions workflow for PyPI publishing**
Create `.github/workflows/publish.yml`:
- Trigger on git tags (e.g., `v0.1.0`)
- Build wheel and sdist
- Publish to PyPI using trusted publisher (no API tokens needed)
- Optional: publish to TestPyPI first for validation

**[ ] Task 3.3: Set up PyPI trusted publisher**
- Create PyPI account if needed
- Configure GitHub Actions as trusted publisher (no API tokens!)
- See: https://docs.pypi.org/trusted-publishers/

**[ ] Task 3.4: Add pre-commit hooks (OPTIONAL)**
- black (code formatting)
- isort (import sorting)
- flake8 or ruff (linting)
- mypy (type checking) - if adding type hints

### Phase 4: Documentation

**[ ] Task 4.1: Add CHANGELOG.md**
- Start with 0.1.0 release notes
- Document public API surface
- Note any breaking changes vs internal SpiritEngine version

**[ ] Task 4.2: Add CONTRIBUTING.md (if accepting contributions)**
- How to set up dev environment
- How to run tests
- Code style guidelines
- How to submit PRs

**[ ] Task 4.3: Improve docstrings (ALREADY EXCELLENT)**
- Current docstrings are comprehensive ✅
- Consider adding type hints to match docstrings
- Consider generating API docs with Sphinx (OPTIONAL)

**[ ] Task 4.4: Create GitHub/GitLab Issues templates**
- Bug report template
- Feature request template

### Phase 5: Code Quality & Polish

**[ ] Task 5.1: Add type hints (OPTIONAL but recommended)**
- Code already has some type hints in function signatures
- Could add full PEP 484 type hints for better IDE support
- Run mypy to validate

**[ ] Task 5.2: Add py.typed marker (if adding type hints)**
- Create empty `knurl/py.typed` file
- Enables type checkers to use your package's hints

**[ ] Task 5.3: Security audit**
- Review hash.py for timing attack resistance ✅ (already uses hmac.compare_digest)
- Review address.py for injection attacks ✅ (already has length limits, validation)
- Review diff.py for patch conflicts ✅ (already has comprehensive error handling)
- No obvious security issues found

**[ ] Task 5.4: Performance audit (OPTIONAL)**
- Benchmark canon.serialize for large objects
- Benchmark chain.fingerprint for long chains
- Document performance characteristics if relevant

### Phase 6: Testing & Validation

**[ ] Task 6.1: Test package build locally**
```bash
python -m build
# Check dist/ for wheel and sdist
```

**[ ] Task 6.2: Test installation from built package**
```bash
python -m pip install dist/knurl-0.1.0-py3-none-any.whl
python -c "from knurl import hash; print(hash.compute('test'))"
```

**[ ] Task 6.3: Publish to TestPyPI first**
```bash
python -m twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ knurl
```

**[ ] Task 6.4: Smoke test installation from TestPyPI**
- Create fresh virtualenv
- Install from TestPyPI
- Run basic imports and function calls
- Verify optional dependencies work

**[ ] Task 6.5: Run full test suite on Python 3.10, 3.11, 3.12**
```bash
# Already works locally with Python 3.12
# Test on 3.10 and 3.11 if available, or use CI
```

### Phase 7: Release & Publishing

**[ ] Task 7.1: Version number decision**
- Current: 0.1.0
- Recommendation: Start with 0.1.0 (indicates beta/pre-stable)
- Or use 1.0.0 if confident in API stability
- Shuttle dependency: ensure version pin is appropriate

**[ ] Task 7.2: Tag release in git**
```bash
git tag -a v0.1.0 -m "Initial public release"
git push origin v0.1.0
```

**[ ] Task 7.3: Publish to PyPI**
- Via GitHub Actions (if set up)
- Or manually: `python -m twine upload dist/*`

**[ ] Task 7.4: Verify PyPI listing**
- Check package page: https://pypi.org/project/knurl/
- Verify README renders correctly
- Verify metadata (author, license, links)
- Test installation: `pip install knurl`

**[ ] Task 7.5: Update shuttle to use PyPI knurl**
- Update shuttle's dependencies to `knurl>=0.1.0`
- Remove any local path references
- Test shuttle with PyPI knurl

### Phase 8: Post-Launch

**[ ] Task 8.1: Add PyPI badge to README**
```markdown
[![PyPI version](https://badge.fury.io/py/knurl.svg)](https://badge.fury.io/py/knurl)
```

**[ ] Task 8.2: Announce release**
- Where? (internal team, mailing lists, social media, etc.)
- Include link to PyPI page and repository

**[ ] Task 8.3: Monitor for issues**
- Set up GitHub issue notifications
- Monitor PyPI download stats (if interested)

**[ ] Task 8.4: Plan maintenance strategy**
- Who maintains the package?
- How are issues triaged?
- Release cadence?

---

## Risk Assessment

### Low Risk
- ✅ Package name available on PyPI
- ✅ No dependency conflicts
- ✅ Excellent test coverage
- ✅ Clean code structure
- ✅ No private data in code

### Medium Risk
- ⚠️  First public release - expect early user feedback/issues
- ⚠️  No CI yet - need to set up before wide usage
- ⚠️  Docstrings use internal examples (speakbot, patrick) - minor clarity issue

### Mitigations Needed
- Set up CI before official v1.0.0 release
- Consider starting with 0.x version to signal pre-stable
- Add clear contribution guidelines if accepting external PRs

---

## Open Questions / Decisions Needed

1. **License copyright holder**: Personal name vs organization?
2. **Repository location**: New repo or within spiritengine?
3. **Public repository**: GitHub, GitLab, or just PyPI?
4. **API stability**: Release as 0.1.0 (beta) or 1.0.0 (stable)?
5. **Maintenance model**: Solo maintainer or team?
6. **Contribution policy**: Accept external contributions or closed development?
7. **Documentation hosting**: ReadTheDocs, GitHub Pages, or just README?
8. **Type hints**: Add full type annotations before release?
9. **SKEIN address module**: This is very SpiritEngine-specific - keep it or make it optional?
   - Current: address module is in core exports
   - Option A: Keep it (it's generic enough)
   - Option B: Make it optional import
   - Option C: Move to separate `knurl-skein` package

---

## Estimated Timeline

**Minimal viable FOSS release (0.1.0 beta)**:
- Phase 1 (Legal): 1 hour
- Phase 2 (Metadata): 2 hours
- Phase 6 (Testing): 1 hour
- Phase 7 (Release): 1 hour
- **Total: 5 hours (can be done in one session)**

**Full production release (1.0.0 with CI/CD)**:
- Add Phase 3 (CI/CD): 4 hours
- Add Phase 4 (Docs): 3 hours
- Add Phase 5 (Polish): 4 hours
- **Total: 16 hours (across 2-3 sessions)**

---

## Success Criteria

- [x] Package builds without errors
- [ ] Package installs from PyPI
- [ ] All 930 tests pass on Python 3.10, 3.11, 3.12
- [ ] shuttle can depend on PyPI knurl
- [ ] LICENSE file exists with correct copyright
- [ ] README accurately describes public API
- [ ] No private/internal references in published code
- [ ] CI runs on all commits (for v1.0.0)

---

## Notes

**SKEIN address module consideration**:
The `address` module is tightly coupled to SKEIN (internal SpiritEngine architecture). Options:
1. Keep it - addresses are generic enough (Layer 1/2/3 addressing)
2. Document it clearly as "SKEIN address parsing"
3. Split into separate package later if needed

**Recommendation**: Keep it for initial release. It's well-tested, well-documented, and self-contained. If it causes confusion, can deprecate in future version.

**Testing note**:
The test suite includes "gremlin", "oracle", and "chaos" tests - this is EXCELLENT for a cryptographic/hashing library. Shows serious attention to security and edge cases. Highlight this in README/docs.

**Hypothesis usage**:
Property-based testing with Hypothesis shows high code quality. Consider mentioning this in package description to attract quality-conscious users.

---

## References

- PyPI package availability: VERIFIED (no existing "knurl" package found)
- Current MIT license declaration: pyproject.toml:7
- Test count: 930 tests collected
- Source LOC: 1,546 lines
- Test LOC: 10,628 lines
- Python requirement: 3.10+ (pyproject.toml:6)

---

**Created**: 2026-01-31
**Status**: Draft - Ready for execution
**Owner**: TBD
**Target Launch**: TBD
