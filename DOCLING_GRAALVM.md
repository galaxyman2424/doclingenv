# DoclingGraalVM — Project History & Effort Log
## Java Files Created / Modified

### `PythonRunner.java`
The original proof-of-concept. Used GraalVM's `Context.newBuilder("python")` to run a Python `print('Hello World')` inline, then pivoted to a subprocess approach — launching a native Python executable from a venv via `ProcessBuilder`. The subprocess ran a hardcoded Docling conversion script targeting a specific PDF path. This was a workaround because GraalPy could not handle Docling's C extension dependencies at the time.

### `EmbedPythonTest.java`
The more serious integration attempt. Uses GraalVM's polyglot API with explicit options pointing at a GraalPy-managed venv (`python-resources/venv`) and home directory. Sets `python.Executable`, `python.PythonHome`, `python.PythonPath`, and `python.ForceImportSite`. Tests three things in sequence: creating the Python context, importing `docling`, and importing `DocumentConverter`. This is the main test harness for the actual in-process embedding goal.

### `pom.xml`
Configured Maven to use GraalVM polyglot `24.1.2`. Added three dependencies: `polyglot`, `python` (POM-type runtime), and `python-embedding`. Configured the `graalpy-maven-plugin` to manage a `python-resources/` external directory (not embedded in the JAR — better for large packages) and pip-install `docling` at build time.

---

## Environment

| Property | Value |
|---|---|
| Platform | WSL2 Ubuntu (under Windows) |
| GraalPy version | 25.0.2 |
| GraalVM JDK | 21.0.10 |
| Venv location | `~/docling-env` |
| Java project location | `C:\Users\Connor\Desktop\GraalPolyglotProject\` |

---

## Dependencies Installed

All installed into the GraalPy venv (`~/docling-env`) via pip.

| Package | Notes |
|---|---|
| `docling` | Core package, initially installed with `--no-deps` |
| `docling-ibm-models` | Installed with `--no-deps` to satisfy docling's version metadata check at import time without pulling in PyTorch |
| `beautifulsoup4` | Pure Python, batch install |
| `marko` | Pure Python |
| `openpyxl` | Pure Python |
| `pluggy` | Pure Python |
| `pylatexenc` | Pure Python |
| `python-docx` | Pure Python |
| `python-pptx` | Pure Python |
| `requests` | Pure Python |
| `lxml` | Required compiling from source against system libxml2/libxslt; GraalPy produced a GraalPy-specific `.so` file |
| `polyfactory` | Pure Python |
| `pypdfium2` | Installed, then patched (see Patches section) |
| `rtree` | Pure Python |
| `filetype` | Installed separately after a `ModuleNotFoundError` |
| `charset_normalizer` | Pinned to `3.3.2` — see Bug Fixes |
| `libxml2-dev` + `libxslt1-dev` | System libraries installed via `apt-get`, required for lxml to compile |

**Intentionally skipped:** `torch`, `torchvision`, `accelerate`, `scipy`, `rapidocr` — heavy ML deps not needed for basic PDF conversion.

---

## Patches

### `pypdfium2_raw/bindings.py`

GraalPy's ctypes implementation does not accept `POINTER(None)` as a valid type and throws a `TypeError` at module load time. Every occurrence of `POINTER(None)` was replaced with `c_void_p` using `sed`. This is the semantically correct ctypes equivalent for a void pointer and fixed the import crash.

```bash
sed -i 's/POINTER(None)/c_void_p/g' ~/docling-env/lib/python3.11/site-packages/pypdfium2_raw/bindings.py
```

---

## Bug Fixes

| Bug | Root Cause | Fix |
|---|---|---|
| `POINTER(None)` TypeError | GraalPy ctypes rejects `POINTER(None)` at module load | Patched `pypdfium2_raw/bindings.py` — replaced all occurrences with `c_void_p` |
| `LookupError: euc_jis_2004` | `charset_normalizer` 3.4+ enumerates every Python codec at import; GraalPy does not implement `euc_jis_2004` | Pinned `charset_normalizer==3.3.2` |
| `PackageNotFoundError: docling-ibm-models` | Docling checks this package's version metadata at import time | Installed `docling-ibm-models --no-deps` |
| `libxml2`/`libxslt` missing | lxml requires system C headers to compile from source | `sudo apt-get install -y libxml2-dev libxslt1-dev` |
| `ModuleNotFoundError: filetype` | Not included during the batch `--no-deps` install | Installed `filetype` separately |

---

## Current Status

### Working
- `from docling.document_converter import DocumentConverter` imports successfully in GraalPy
- Full dependency chain installed and import chain verified
- Non-PDF backends (DOCX, HTML, Markdown) are likely functional

### Blocked
- PDF conversion fails at runtime — `pypdfium2`'s buffer-reader callback (`m_GetBlock` `CFUNCTYPE`) attempts to convert a Python callable into a native C function pointer, which GraalPy cannot do (`Cannot convert Object pointer to native`)
- `EmbedPythonTest.java` not yet tested end-to-end
- Version conflicts unresolved: `huggingface-hub 1.7.1` (needs `<1.0`) and `typer 0.24.1` (needs `<0.22.0`)

