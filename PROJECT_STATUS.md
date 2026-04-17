# DoclingGraalvm — Project Status Report

## 1. High-Level Summary

This project aims to embed IBM's Docling PDF processing library into a Java application via GraalVM's polyglot API, allowing PDF-to-markdown conversion to run in-process without subprocess calls. The current session focused entirely on installing Docling and its dependency chain into a GraalPy 25.0.2 virtual environment on WSL2 Ubuntu. The DocumentConverter class now imports successfully, but actual PDF conversion is blocked by a GraalPy ctypes limitation in pypdfium2's buffer-reading callback mechanism.

---

## 2. Key Changes / Additions

- Successfully installed the full docling dependency chain into `~/docling-env`
- Patched `pypdfium2_raw/bindings.py` to replace all `POINTER(None)` with `c_void_p` (correct ctypes void pointer type)
- Pinned `charset_normalizer==3.3.2` to avoid GraalPy codec enumeration crash on `euc_jis_2004`
- Installed `docling-ibm-models` (no-deps) to satisfy docling's version metadata check at import time
- Installed all pure-Python deps in one batch: `beautifulsoup4`, `marko`, `openpyxl`, `pluggy`, `pylatexenc`, `python-docx`, `python-pptx`, `requests`, `lxml`, `polyfactory`, `pypdfium2`, `rtree`
- Installed system libraries `libxml2-dev` and `libxslt1-dev` required to compile lxml from source

---

## 3. Technical Details

**Environment:**
- WSL2 Ubuntu
- GraalPy 25.0.2
- GraalVM JDK 21.0.10
- venv at `~/docling-env`

**Java project:**
- Maven project at `C:\Users\Connor\Desktop\GraalPolyglotProject\`
- Using GraalVM polyglot API 24.1.2

**Key Patches:**
- **pypdfium2_raw/bindings.py** — GraalPy's ctypes does not support `POINTER(None)` as a type; replaced with `c_void_p` which is the semantically correct equivalent
- **charset_normalizer** — Version 3.4+ enumerates all Python codec modules at import time; GraalPy doesn't implement `euc_jis_2004`, causing a hard `LookupError`. Pinned to 3.3.2 which doesn't do this scan
- **lxml** — Required Cython compilation against system libxml2/libxslt; GraalPy auto-patches C API usages and produces a GraalPy-specific .so (`lxml.etree.graalpy250-312-native-x86_64-linux.so`)

**Dependencies Intentionally Skipped:**
- `torch`, `torchvision`, `accelerate`, `scipy`, `rapidocr` — heavy ML deps not needed for basic PDF conversion

---

## 4. Bug Fixes / Improvements

| Issue | Solution |
|-------|----------|
| `POINTER(None)` TypeError | Fixed by replacing all occurrences with `c_void_p` in `pypdfium2_raw/bindings.py` via sed |
| `euc_jis_2004` LookupError | Fixed by pinning `charset_normalizer` to 3.3.2 |
| `PackageNotFoundError: docling-ibm-models` | Fixed by installing the package with `--no-deps` to satisfy metadata lookup without pulling in torch |
| `libxml2`/`libxslt` missing | Fixed by running `sudo apt-get install -y libxml2-dev libxslt1-dev` before retrying lxml build |
| `filetype` ModuleNotFoundError | Fixed by installing filetype separately |

---

## 5. Challenges & Solutions

### GraalPy ctypes POINTER(None) Incompatibility
**Problem:** GraalPy's ctypes implementation rejects `POINTER(None)` as a type at module load time.

**Solution:** Patched the bindings file to use `c_void_p` instead, which is the semantically correct ctypes void pointer.

### Codec Enumeration Crash
**Problem:** `charset_normalizer` 3.4+ proactively loads every Python codec at import time; GraalPy doesn't implement all of them.

**Solution:** Pinned to 3.3.2.

### Whack-a-Mole Dependency Resolution
**Problem:** Docling was installed with `--no-deps` earlier in the project, leaving ~15 transitive dependencies uninstalled.

**Solution:** Identified them from pip's conflict report and installed in batches grouped by complexity.

### pypdfium2 ctypes Callback Failure (Current Blocker)
**Problem:** Even after the `POINTER(None)` patch, pypdfium2's `get_bufreader` function tries to convert a Python callable into a native C function pointer via `set_callback`. GraalPy cannot do this (`Cannot convert Object pointer to native`). All docling PDF backends (v2, v4, default) ultimately call this code path.

**Status:** Awaiting patch to docling backend or alternative PDF processing approach.

---

## 6. Current State of the Project

### ✅ Working

- `from docling.document_converter import DocumentConverter` imports successfully in GraalPy
- All non-PDF docling backends (DOCX, HTML, Markdown, etc.) are likely functional
- Full dependency chain installed and import chain verified

### ⚠️ Incomplete / Blocked

- **PDF conversion fails at runtime** — pypdfium2's buffer-reader callback (`m_GetBlock` CFUNCTYPE) cannot be converted to a native pointer in GraalPy
- `EmbedPythonTest.java` polyglot integration not yet tested end-to-end
- Version conflicts still present: `huggingface-hub 1.7.1` (needs `<1.0`) and `typer 0.24.1` (needs `<0.22.0`) — not yet downgraded

---

## 7. Next Steps

### Priority 1: Resolve PDF Conversion
1. Patch `docling_parse_backend.py` to pass the PDF file path as a string directly to `pdfium.PdfDocument()` instead of as a BytesIO buffer
   - This would use `FPDF_LoadDocument` (no callbacks) instead of `FPDF_LoadMemDocument` (requires the broken buffer-reader callback)
2. Confirm input type by inspecting `docling_parse_backend.py` lines around `self._pdoc = pdfium.PdfDocument(self.path_or_stream)`
   - If `path_or_stream` is already a path, the issue is inside pypdfium2's path-opening code and needs a different fix

### Priority 2: Dependency Management
1. Downgrade `huggingface-hub` to `<1.0` and `typer` to `<0.22.0` to clear remaining version conflicts

### Priority 3: Integration Testing
1. Test `EmbedPythonTest.java` once PDF conversion works
2. Validate the GraalVM polyglot context can call `DocumentConverter` in-process

### Priority 4: Documentation & Reproducibility
1. Document all patches in a reproducible shell script
2. Allow the environment to be rebuilt without repeating each fix manually
3. Update only when prompted

---

## 8. Appendix: Why LLVM Bitcode Approach Won't Work

### Overview
Attempting to run PDFium as LLVM bitcode inside GraalVM's Sulong engine is not viable in practice due to mismatches in build systems, dependency requirements, runtime semantics, and instruction set support.

### Critical Blockers

**1. Build System Incompatibility**
- PDFium uses Chromium's `gn` + `ninja` infrastructure
- Assumes native compilation targets (ELF/Mach-O/PE)
- Injecting `-flto -femit-llvm` breaks GN toolchain definitions and static linking stages

**2. Dependency Graph Cannot Be Fully Converted**
- PDFium depends on: Skia, zlib, libpng, libjpeg, libtiff, FreeType, OpenJPEG, lcms2
- Many include assembly or platform-specific optimizations
- LLVM bitcode requires a fully homogeneous IR graph; even one native `.a` or `.o` breaks linking/execution

**3. SIMD Instructions Are Unsupported in Sulong**
- PDFium and Skia rely on SSE2, AVX, and platform-specific vector intrinsics
- Sulong does not support lowering x86 SIMD intrinsics
- Disabling SIMD requires modifying large portions of Skia/PDFium and degrades performance severely

**4. C++ Runtime Features Don't Map Cleanly**
- PDFium uses exceptions, RTTI (`dynamic_cast`), custom allocators, threading
- Sulong's support is partial and incomplete under complex workloads
- Leads to semantic incompatibility even if compilation succeeds

**5. GraalPy ctypes Bridge Is Experimental**
- Complex callback patterns are not well supported
- Likely to encounter callback invocation failures, memory ownership mismatches, and crashes

**6. ABI and API Compatibility Constraints**
- pypdfium2 expects exact symbol names, signatures, and matching ABI behavior
- Even small mismatches break bindings; symbol-level debugging is extremely difficult

### Conclusion
Running PDFium as LLVM bitcode inside GraalVM is not just an engineering challenge—it is a **fundamental mismatch** between system design assumptions. You are attempting to execute a performance-critical, SIMD-heavy native rendering engine inside an environment that does not support its instruction set or runtime model.

---

## 📝 Notes

- This status reflects work as of the latest build attempt
- Please update this document as progress is made on blocking issues
- Maintain the appendix for future reference on architectural decisions

