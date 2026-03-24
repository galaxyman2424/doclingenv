DoclingEnv – Java ↔ Python (GraalVM) Integration
Overview

This project demonstrates how to embed Python inside a Java 21 application using GraalVM’s Polyglot runtime (GraalPy). The system enables Java code to directly execute Python within the same process, eliminating the need for subprocess calls or external services.

The primary objective is to establish a lightweight, maintainable bridge between Java and Python for scripting, data processing, and AI-related workflows.

Motivation

Traditional Java–Python interoperability typically relies on:

Subprocess execution (ProcessBuilder)
REST APIs / microservices
JNI bindings

These approaches introduce overhead, latency, or complexity.

This project instead uses GraalVM Polyglot, allowing:

Native in-process execution
Lower latency
Simplified architecture
Shared memory space between Java and Python
Architecture
Core Components
Java 21 (JDK 21) — Primary runtime
GraalVM — Polyglot execution environment
GraalPy — Python implementation on GraalVM
Maven — Build and dependency management
Execution Flow
Java Application
        ↓
GraalVM Polyglot Context
        ↓
Embedded GraalPy Runtime
        ↓
Python Code Execution

Java creates a Context object that initializes the Python engine and evaluates Python code directly.

Project Structure
doclingenv/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── PythonRunner.java
Key Implementation
Python Execution from Java

The core functionality is implemented in PythonRunner.java:

import org.graalvm.polyglot.*;

public class PythonRunner {
    public static void main(String[] args) {
        Context context = Context.newBuilder("python")
                .allowAllAccess(true)
                .build();

        context.eval("python", "print('Hello from Python')");
    }
}
What This Does
Initializes a GraalVM polyglot context
Enables Python language support
Executes Python code inline within the JVM
Setup Instructions
Prerequisites
Java 21 JDK
GraalVM (Java 21 compatible)
Maven
GraalVM Setup
Install GraalVM (Java 21 distribution)
Set environment variables:
export JAVA_HOME=/path/to/graalvm
export PATH=$JAVA_HOME/bin:$PATH
Verify installation:
java -version
gu --version
Build and Run
Compile the project
mvn compile
Execute the program
mvn exec:java
Maven Configuration

The project uses Maven to manage:

GraalVM Polyglot dependencies
Python language support
Execution via exec-maven-plugin
Current Capabilities
Embedded Python execution inside Java
No dependency on system-installed CPython
In-process execution (no subprocess overhead)
Fully Maven-driven workflow
Design Decisions
Decision	Reason
Java 21	Course/environment constraint
GraalPy instead of CPython	Native JVM integration
Embedded runtime	Eliminates subprocess overhead
Maven	Standardized build system
Current State

The project currently provides:

Working GraalPy installation
Functional Java → Python execution
Maven build configuration
Simple proof-of-concept execution pipeline

Python code can now be executed directly from Java using GraalVM.
