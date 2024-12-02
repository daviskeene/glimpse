# Glimpse Lambda Layers

This directory contains Lambda layers used to optimize the performance of specific language runtimes in Glimpse.

## Java/Kotlin Layer

The `java-kotlin` layer provides optimized JVM environment for Java and Kotlin execution.

### Structure
```
java-kotlin/
├── Dockerfile          # Builds minimal JVM environment
└── build.sh           # Packages layer for AWS Lambda
```

### What's Included
- Amazon Corretto 11 (minimal JRE)
- Kotlin Runtime (essential components)
- Optimized JVM settings
  - Fixed heap size (`-Xms256m -Xmx256m`)
  - Tiered compilation optimizations
  - Lambda-specific JVM flags

### Building the Layer

1. Build the layer package:
```bash
make build-layer
```
This will:
- Build a Docker image with JVM components
- Extract required files to `/opt`
- Create a ZIP archive for Lambda

2. Publish to AWS:
```bash
make publish-layer
```

### Size Constraints
- AWS Lambda layers must be < 50MB unzipped
- Current optimizations:
  - Using JRE instead of JDK
  - Including only essential Kotlin components
  - Removing unnecessary tools/docs

### Usage
Once deployed, the layer provides:
- Pre-warmed JVM environment
- Optimized memory settings
- Faster cold starts for Java/Kotlin

### Environment Variables
The layer sets up:
```bash
JAVA_HOME=/opt/java
PATH=/opt/java/bin:/opt/kotlin/bin:${PATH}
```

### Current Status
- [x] Basic layer structure
- [x] JVM optimization flags
- [x] Minimal runtime components
- [ ] Layer size optimization
- [ ] SSL certification issues
- [ ] Production deployment

### Next Steps
1. Resolve SSL issues in layer deployment
2. Further reduce layer size
3. Add performance benchmarking
4. Document performance improvements

### Notes
- Layer must be deployed to the same region as Lambda function
- Consider using specific version tags for stability
- Monitor cold start improvements after deployment 