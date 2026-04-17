# GraalPy & Docling Compatibility Analysis

A comprehensive guide to integrating Docling document conversion within GraalVM/GraalPy, including technical blockers, proposed solutions, and architectural recommendations.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Section 1: GraalVM/GraalPy Team Action Items](#section-1-graalvmgraalpyteam-action-items)
3. [Section 2: Docling Team Solutions](#section-2-docling-team-solutions)
4. [Section 3: Rejected Approaches](#section-3-rejected-approaches)
5. [Section 4: Native JNI Callback Wrapper](#section-4-native-jni-callback-wrapper-workaround-solution)
6. [Implementation Guide](#implementation-guide)

---

## Executive Summary

This document outlines the challenges of embedding Docling (Python document conversion library) within GraalVM using GraalPy, along with specific technical fixes needed from both the GraalVM and Docling projects.

**Key Findings:**
- 5 blockers in GraalPy require fixes from the GraalVM team
- 5 improvements would dramatically enhance Docling's alternative-runtime compatibility
- The primary blocker (ctypes callbacks) is solvable with focused effort from either team
- A file-path-based PDF backend would unblock GraalPy usage immediately with minimal changes

---

## Section 1: GraalVM/GraalPy Team Action Items

### [G-1] Native C Function Pointer Callbacks from Python Callables

**Status:** 🔴 **Critical Blocker**

#### The Core Problem

GraalPy cannot convert a Python `CFUNCTYPE`-wrapped callable into a native C function pointer. This is the primary blocker for `pypdfium2` integration.

**Error:**
```
Cannot convert Object pointer to native
```

**Root Cause:** `pypdfium2` registers a `get_bufreader` callback (`m_GetBlock`) using `ctypes.CFUNCTYPE`. When it attempts to pass this callback to the underlying C library, GraalPy cannot create a native trampoline.

#### What GraalPy Needs to Implement

`ctypes.CFUNCTYPE.__call__` must produce a **real native trampoline**—a small native stub that:
1. Is called by C code
2. Re-enters the Python interpreter
3. Invokes the original Python callable

**How CPython does it:** via `libffi` closure allocation (`ffi_closure_alloc`)

**GraalPy's Challenge:** Running on the JVM means no direct equivalent to "allocate native code that calls back into a managed runtime." Requires either:
- Truffle NFI (Native Function Interface) closure support, or
- JNI-level trampoline factory

#### Suggested Path for the GraalVM Team

1. Use Truffle NFI's `@CEntryPoint` or closure mechanism to synthesize native stubs at runtime for `CFUNCTYPE` instances
2. Expose this through the existing `CTypesFunctionObject` in GraalPy's ctypes implementation
3. Ensure the trampoline holds a stable reference to the Python callable

**Effort Estimate:** Medium (2–3 weeks for experienced GraalVM contributor)

---

### [G-2] POINTER(None) Should Resolve to c_void_p

**Status:** 🟡 **Low-Hanging Fruit**

#### The Problem

`ctypes.POINTER(None)` is valid in CPython and resolves to a void pointer type. GraalPy raises a `TypeError` because it doesn't handle `None` as a special case.

#### The Fix

Add a check in GraalPy's `ctypes.POINTER()` implementation:

```python
def POINTER(type_):
    if type_ is None:
        return c_void_p
    # ... existing logic
```

**This is a one-line fix.**

#### Current Workaround

Patches `pypdfium2_raw/bindings.py` with `sed`—fragile and breaks on package upgrades.

#### Impact

✅ Unblocks the initial import of `pypdfium2` without requiring downstream patching

**Effort Estimate:** < 1 hour

---

### [G-3] Codec Enumeration at Import Time Crashes on Unimplemented Codecs

**Status:** 🟡 **Medium Priority**

#### The Problem

`charset_normalizer` 3.4+ iterates over all registered Python codecs at import time to build a lookup table. GraalPy does not implement `euc_jis_2004` (and several other CJK codecs), raising a hard `LookupError` that crashes the import.

#### What GraalPy Needs

Either:
1. Implement the missing codecs (large effort), or
2. Make `codecs.lookup()` return gracefully so calling code can catch the exception

#### Suggested Quick Fix

Ensure `codecs.lookup(name)` raises a **catchable Python-level `LookupError`** for unknown codecs, rather than a Java-level exception that bypasses Python exception handlers.

In CPython, this works:
```python
try:
    codecs.lookup('euc_jis_2004')
except LookupError:
    # Handle gracefully
    pass
```

GraalPy may be raising it at a lower level before the `try/except` can catch it.

#### Impact

✅ Allows `charset_normalizer` 3.4+ to work without pinning to older versions

**Effort Estimate:** Low–Medium (1–2 weeks)

---

### [G-4] pip install Compatibility and Package Metadata Resolution

**Status:** 🟡 **Medium Priority**

#### The Problem

Several packages must be installed with `--no-deps` to avoid cascading failures. GraalPy's pip integration sometimes fails mid-dependency-tree on packages with C extensions, causing the entire install to abort rather than skipping just the problematic package.

#### Suggested Improvement

Add a `--skip-c-extensions` flag (or equivalent) to GraalPy's bundled pip or `graalpy-maven-plugin` that:
- Installs pure-Python wheels
- Skips packages that require native compilation GraalPy cannot handle
- Reports them as **warnings** rather than hard errors

#### Impact

✅ Simplifies dependency resolution and makes GraalPy setups more robust

**Effort Estimate:** Medium (1–2 weeks)

---

### [G-5] graalpy-maven-plugin Virtual Environment Path Options

**Status:** 🟡 **Quality-of-Life Improvement**

#### The Problem

The Maven plugin auto-manages `python-resources/venv` and `python-resources/home`, but it doesn't expose options to:
- Point at a pre-built external venv that already has `docling` installed (with all patches applied)
- Skip venv creation and pip install if the target directory already exists

Every clean build re-runs `pip install docling`, which takes several minutes and loses all manual patches.

#### Requested Feature

Add an `<externalVenvPath>` configuration option to the plugin:

```xml
<plugin>
  <groupId>org.graalvm.buildtools</groupId>
  <artifactId>graalpy-maven-plugin</artifactId>
  <configuration>
    <externalVenvPath>/path/to/existing/venv</externalVenvPath>
    <skipVenvCreation>true</skipVenvCreation>
  </configuration>
</plugin>
```

#### Impact

✅ Dramatically reduces build times for iterative development

**Effort Estimate:** Low (< 1 week)

---

## Section 2: Docling Team Solutions

These are changes the Docling project itself could make to improve GraalPy (and general alternative-runtime) compatibility, **independent of GraalVM fixes**.

### [D-1] Offer a File-Path-Only PDF Backend Mode

**Status:** 🟢 **Highest Impact, Minimal Effort**

#### The Problem

`DoclingParseV2DocumentBackend` (and similar backends) pass the PDF to `pypdfium2` as a `BytesIO` stream. This triggers the `FPDF_LoadMemDocument` code path, which **requires a C-level read callback**—the exact thing GraalPy cannot do.

#### The Solution

If the input were passed as a **file path string** instead, `pypdfium2` would call `FPDF_LoadDocument`, which reads directly from disk using C stdio—**no callback, no Python-to-C trampoline needed**.

#### Suggested Implementation

In `docling_parse_backend.py`, when `path_or_stream` is a `Path` or `str`, pass it directly to `pdfium.PdfDocument(str(path))`:

```python
if isinstance(self.path_or_stream, (str, Path)):
    self._pdoc = pdfium.PdfDocument(str(self.path_or_stream))
else:
    self._pdoc = pdfium.PdfDocument(self.path_or_stream)  # existing stream path
```

**This is a one-line conditional.**

#### Impact

✅ **Unblocks GraalPy PDF conversion entirely without any GraalVM-side changes**  
✅ Works immediately once merged  
✅ Maintains backward compatibility with stream-based inputs

**Effort Estimate:** < 2 hours

---

### [D-2] Make ML/OCR Dependencies Fully Optional at Import Time

**Status:** 🟡 **High Value, Medium Effort**

#### The Problem

Even when using `DocumentConverter` without OCR, importing `docling` triggers imports deep in the dependency tree:
- `torch`
- `huggingface_hub`
- `transformers` metadata checks

On GraalPy, this causes version conflict warnings and occasional hard failures.

#### Suggested Change

Move all ML-heavy imports behind `TYPE_CHECKING` guards or lazy import blocks that only execute when those features are actually requested at runtime:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ocr_options import EasyOcrOptions, TesseractOcrOptions

def get_ocr_backend(backend_name: str):
    if backend_name == "easycr":
        from .ocr_options import EasyOcrOptions
        return EasyOcrOptions
    # ...
```

#### Impact

✅ Core Docling library is importable with **zero ML dependencies loaded**  
✅ Works immediately on constrained runtimes (GraalPy, PyPy, Wasm)  
✅ Users opt into heavyweight dependencies only when needed

**Effort Estimate:** 1–2 weeks

---

### [D-3] Expose a pypdfium2-Free Backend for Structural PDF Parsing

**Status:** 🟡 **Medium Value, Low Effort**

#### The Problem

All current PDF backends ultimately depend on `pypdfium2` or `pdfminer`:
- `pypdfium2` is blocked by the GraalPy ctypes issue
- `pdfminer` is pure Python but lacks layout analysis quality

#### Suggested Solution

Expose a backend option that uses `pdfminer.six` exclusively (already a dependency) with a clear accuracy trade-off warning:

```python
converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOptions(backend=PdfBackend.PDFMINER)
    }
)
```

#### Impact

✅ Gives GraalPy users a **working, if lower-fidelity, path** to PDF conversion today  
✅ Works on any Python runtime (CPython, PyPy, GraalPy, Wasm)  
✅ Pure-Python implementation, no compilation needed

**Effort Estimate:** 1 week

---

### [D-4] Ship a docling-lite Package

**Status:** 🟢 **Game-Changer for Embedded Scenarios**

#### The Problem

Docling's full dependency tree is enormous (~4GB installed):
- `torch`
- `torchvision`
- `huggingface_hub`
- `accelerate`
- `scipy`
- `rapidocr`
- `pypdfium2`

For embedding scenarios (GraalVM, serverless, CI), this is impractical.

#### Suggested Solution

Publish a **`docling-lite`** package that includes:
- Pure-Python conversion pipeline only
- Markdown export, DOCX/HTML/XLSX backends
- `pdfminer` as the sole PDF backend

**Installation:** Seconds (not minutes)  
**Embeddability:** Trivially embedable in any Python runtime including GraalPy

#### Example Installation

```bash
pip install docling-lite
# Instead of pip install docling (4GB)
```

#### Impact

✅ **Dramatic reduction in dependency size**  
✅ Viable for serverless, containerized, and embedded scenarios  
✅ Opens Docling to GraalPy, PyPy, WASM, and other constrained runtimes

**Effort Estimate:** 1–2 weeks (mostly packaging/CI work)

---

### [D-5] Document GraalPy / Alternative Runtime Compatibility

**Status:** 🟢 **Essential for User Guidance**

#### The Problem

There is **no documentation** on which Docling backends work on which Python runtimes. Developers targeting GraalPy or PyPy discover incompatibilities only after hours of debugging.

#### Suggested Addition

Add a **"Runtime Compatibility" table** to the Docling README:

| Backend | CPython | PyPy | GraalPy |
|---------|---------|------|---------|
| **DoclingParseV2** (pypdfium2) | ✅ | ⚠️ Partial | ❌ ctypes callback |
| **PDFMiner** | ✅ | ✅ | ✅ |
| **DOCX/HTML/MD** | ✅ | ✅ | ✅ |
| **OCR (EasyOCR)** | ✅ | ❌ | ❌ |
| **Layout Detection** | ✅ | ⚠️ Limited | ⚠️ Limited (PDFMiner) |

#### Impact

✅ **Saves users hours of debugging**  
✅ Sets clear expectations for alternative runtimes  
✅ Guides users to compatible backends

**Effort Estimate:** < 2 hours

---

## Section 3: Rejected Approaches

The following solutions were evaluated and rejected for the stated reasons.

### ❌ Inter-Process Communication (IPC) via Socket or Pipe

**Why it was considered:**
Run a CPython subprocess as a dedicated PDF-conversion server; the Java side sends file paths over a socket or stdin pipe and receives markdown back. Avoids GraalPy entirely.

**Why it was rejected:**
- ✗ Architecturally identical to the `ProcessBuilder` subprocess approach already in `PythonRunner.java` — adds socket/serialization complexity for zero functional gain
- ✗ **Completely abandons the goal of in-process GraalVM polyglot embedding**
- ✗ Requires managing a daemon process (lifecycle, crash recovery, port conflicts)
- ✗ No advantage over just calling `python -c` directly, which already works

---

### ❌ gRPC Microservice Wrapping Docling

**Why it was considered:**
Wrap Docling in a CPython gRPC server, expose a `ConvertPdf(path) -> markdown` RPC, call it from Java using the standard gRPC Java client.

**Why it was rejected:**
- ✗ Same fundamental objection: **abandons in-process embedding**
- ✗ Adds enormous operational overhead: gRPC server must be started, kept alive, secured, and versioned separately
- ✗ Introduces network latency for what should be a local library call
- ✗ **Overkill** for a problem that is one GraalPy ctypes patch away from being solved in-process
- ✅ *Appropriate only* if this were a multi-tenant conversion service — not for an embedded tool

---

### ❌ Rewrite PDF Parsing in Pure Java (Apache PDFBox)

**Why it was considered:**
Use Apache PDFBox or iText entirely on the Java side, bypassing Python and GraalPy altogether for PDF processing.

**Why it was rejected:**
- ✗ Docling's value is **not just text extraction** — it is AI-driven layout analysis, table structure detection, and semantic chunking
- ✗ PDFBox extracts raw text with **no layout understanding**
- ✗ Reproducing Docling's model pipeline in Java would require porting or re-training IBM layout models — **months-long effort**
- ✗ **Rejects the entire premise of the project** in favor of a much weaker tool
- ✅ *Acceptable only* as a last-resort fallback if GraalPy compatibility is permanently impossible

---

### ❌ Switch from GraalPy to Jython

**Why it was considered:**
Jython is a JVM-based Python implementation. It has no ctypes issues because it doesn't support native C extensions at all.

**Why it was rejected:**
- ✗ **Jython only supports Python 2.7.** Docling requires Python 3.10+. **Hard incompatibility with no path forward.**
- ✗ Jython has been **effectively unmaintained for years**
- ✗ Even if Jython supported Python 3, Docling's ML dependencies (`torch`, `numpy`) require **CPython C extensions** that Jython cannot run
- ✗ **Non-starter**

---

### ❌ Monkey-Patching pypdfium2 at Runtime from Java

**Why it was considered:**
Before the JVM starts the GraalPy context, inject Python code that replaces `pypdfium2`'s callback registration with a no-op or file-path-based alternative.

**Why it was rejected:**
- ✗ Patch must be applied before `pypdfium2` loads bindings — **fragile and order-dependent**
- ✗ **Any `pypdfium2` upgrade resets the problem**
- ✗ Correct fix belongs in **GraalPy** (fix ctypes) **or Docling** (use file path instead of stream)
- ✗ Much cleaner and more durable than runtime monkey-patching from Java
- ✗ **Debugging a monkey-patched polyglot context is extremely painful**

---

## Section 4: Native JNI Callback Wrapper (Workaround Solution)

**Status:** 🟠 **Viable Intermediate Solution**

### The Problem Reframed

The core issue is that GraalPy's ctypes implementation cannot synthesize a native trampoline that satisfies `pypdfium2`'s expectations. Rather than waiting for GraalVM to implement this capability, a **native JNI wrapper library** can bridge the gap by providing the callback mechanism that's missing.

### The Solution: JNI Callback Bridge Library

Create a lightweight native JNI library (`graalpy-ctypes-bridge` or similar) that:

1. **Intercepts the PDF stream read request** from pdfium
2. **Calls back into the JVM** to retrieve the next chunk of data from Python
3. **Returns the data to pdfium** without requiring GraalPy's ctypes to create the trampoline

**This solves the problem entirely outside of GraalPy or Docling—it's a third-party shim.**

#### Architecture

```
┌─────────────────────────────────────────┐
│         GraalVM/GraalPy Context         │
│  ┌─────────────────────────────────────┐│
│  │ Docling + pypdfium2 (with stream)   ││
│  │  - Creates BytesIO stream           ││
│  │  - Passes to pdfium.PdfDocument()   ││
│  └────────────┬────────────────────────┘│
│               │ (tries to register      │
│               │  callback, fails        │
│               │  in GraalPy)            │
│               │                          │
│  ┌────────────v────────────────────────┐│
│  │ JNI Callback Bridge Library          ││
│  │  - Receives callback registration    ││
│  │  - Provides native trampoline        ││
│  │  - Marshals data back/forth          ││
│  └────────────┬────────────────────────┘│
└───────────────┼──────────────────────────┘
                │ (JNI calls)
         ┌──────v──────┐
         │  pdfium C   │
         │  library    │
         └─────────────┘
```

#### Implementation Approach

1. **C/C++ component:** Thin native library that:
   - Registers itself as available to ctypes
   - Implements a `CFUNCTYPE`-compatible wrapper factory
   - Allocates native trampolines using system APIs (`mmap`, `execmem`)
   - Uses JNI to call back into Python when invoked

2. **Java component:** JNI binding class that:
   - Loads the native library
   - Exposes `registerCallback(pythonCallable)` → returns function pointer
   - Marshals arguments between C and Python

3. **Python integration:** Monkey-patch or monkey-patch-free injection that:
   - Makes ctypes aware of the JNI bridge
   - Transparently uses the bridge for callback creation instead of failing

#### Example Usage

```python
# No changes to user code needed
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
# When Docling tries to use pypdfium2 with a stream,
# the JNI bridge silently provides the missing trampoline
result = converter.convert_document("file.pdf")
```

**Or with explicit stream support:**

```python
from io import BytesIO
from jni_ctypes_bridge import enable_jni_callbacks

enable_jni_callbacks()  # One-time setup

with open("file.pdf", "rb") as f:
    stream = BytesIO(f.read())
    # This now works on GraalPy because callbacks are JNI-backed
    doc = pdfium.PdfDocument(stream)
```

#### Trade-offs

| Aspect | Impact |
|--------|--------|
| **Implementation complexity** | Medium (200–400 lines of C + JNI glue) |
| **Runtime overhead** | Minimal (one JNI call per PDF chunk read) |
| **GraalPy changes required** | **None** — completely external workaround |
| **Docling changes required** | **None** — works transparently with existing code |
| **Portability** | Requires compilation for each platform (Linux, macOS, Windows, ARM) |
| **Maintenance burden** | Low (isolated library, no core project dependencies) |
| **Long-term viability** | Temporary; obsolete once [G-1] is implemented in GraalVM |

#### Advantages Over Waiting for [G-1]

✅ **Works immediately** — no dependency on GraalVM roadmap  
✅ **Zero changes to Docling or user code** — drop-in library  
✅ **Can be packaged as a PyPI package** — users do `pip install graalpy-ctypes-bridge`  
✅ **Benefits the broader GraalPy ecosystem** — fixes ctypes callbacks for any use case  
✅ **Proves the concept** — provides a working implementation to inform [G-1] design

#### Disadvantages

⚠️ **Requires C/C++ expertise** — not a pure-Python solution  
⚠️ **Platform-specific** — must be compiled for each OS/architecture  
⚠️ **Extra dependency** — adds a native library to the GraalPy environment  
⚠️ **Security implications** — raw JNI code requires careful validation (buffer overflows, etc.)  
⚠️ **Temporary workaround** — should be superseded by [G-1] long-term

#### Suggested Implementation Path

1. **Phase 1:** Proof-of-concept for Linux x86_64 only
2. **Phase 2:** Multi-platform support (macOS, Windows ARM64)
3. **Phase 3:** Package on PyPI with pre-built wheels for common platforms
4. **Phase 4:** Deprecate once GraalVM implements native [G-1] support

#### Comparison: JNI Bridge vs. Alternatives

| Solution | Effort | Blocking Dependency | Time to Production |
|----------|--------|-------------------|-------------------|
| **JNI Bridge (Section 4)** | Medium | None | 2–3 weeks |
| **[D-1] File-path backend** | Low | Docling team | 1 week (if adopted) |
| **[G-1] GraalVM ctypes fix** | High | GraalVM team | 2–3 months |
| **[D-4] docling-lite** | Medium | Docling team | 3–4 weeks (if prioritized) |

**Recommendation:** Pursue **[D-1]** (lowest effort, highest compatibility gain) as the primary path. Use **JNI Bridge** as a stopgap if [D-1] is not adopted, while [G-1] is being developed.

---

## Implementation Guide

### For GraalVM Teams: Native Trampoline Architecture

If implementing **[G-1]** (native C function pointer callbacks), here's the actual architecture:

```
Python callable (movable JVM object)
        ↓
Create a stable JVM WeakReference or GlobalRef (JNI already does this)
        ↓
Allocate off-heap executable memory via Foreign Memory API
        ↓
Write a trampoline into that memory that holds the GlobalRef
        ↓
Hand pdfium the address of the trampoline
        ↓
pdfium calls trampoline → trampoline calls back into JVM via JNI
```

**Key Insight:** The JVM object itself never needs to be pinned. The trampoline lives in **off-heap memory that the GC never touches**.

### For Docling Teams: Priority Roadmap

#### Phase 1 (Immediate) — High Impact, Low Effort
1. **[D-1]** File-path-only PDF backend mode (1–2 hours)
2. **[D-5]** Runtime compatibility table in README (< 2 hours)

#### Phase 2 (Soon) — High Value
3. **[D-2]** Lazy ML/OCR imports (1–2 weeks)
4. **[D-3]** Pure-Python pdfminer backend option (1 week)

#### Phase 3 (Strategic)
5. **[D-4]** `docling-lite` package distribution (1–2 weeks)

---

## Quick Reference: What Unblocks GraalPy

| Fix | Effort | Impact | Owner |
|-----|--------|--------|-------|
| [G-2] `POINTER(None)` | ✅ < 1 hour | 🟡 Unblocks imports | GraalVM |
| [D-1] File-path PDF backend | ✅ < 2 hours | 🟢 **Complete solution** | Docling |
| [JNI Bridge] Native callback shim | ⏱️ 2–3 weeks | 🟢 **Complete solution** | Third-party |
| [G-1] Native callbacks | ⏱️ 2–3 weeks | 🟢 **Enables pypdfium2** | GraalVM |
| [D-2] Lazy ML imports | ⏱️ 1–2 weeks | 🟡 Reduces errors | Docling |

**TL;DR:** Implementing **[D-1]** (file-path PDF backend in Docling) unblocks GraalPy PDF conversion **immediately with minimal effort**. If [D-1] is not adopted, the **JNI Bridge** provides a working workaround **independent of Docling or GraalVM changes**. Implementing **[G-1]** and **[G-2]** in GraalVM enables full compatibility.

---

## Contact & Discussion

For questions or collaboration on these improvements:
- **GraalVM Issues:** Submit issues to [GraalVM GitHub](https://github.com/oracle/graal)
- **Docling Issues:** Submit to [Docling GitHub](https://github.com/DS4SD/docling)

---

**Last Updated:** 2025  
**Status:** Active Development  
**Priority:** High
