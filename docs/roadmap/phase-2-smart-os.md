# Phase 2: Smart Operating System Roadmap

> **Status**: Planned | **Estimated Start**: After v2.6.0 release

## Overview

Phase 2 deepens OMG from a "wow flow generator" into a smart operating system that learns from usage, routes intelligently, and self-corrects.

## Features

### 1. TaskClassifier Enhancement (ML-based)

**Problem**: Rule-based classifier misses nuanced goals
**Solution**: Train lightweight ML model on classified examples; keep rule-based as fallback
**Effort**: M (2-3 weeks)
**Dependencies**: v2.6.0 rule-based classifier, labeled dataset

### 2. Model Router + Budget Brain

**Problem**: All tasks use same model regardless of complexity/cost
**Solution**: Route simple tasks to fast/cheap models, complex to powerful; track token budget
**Effort**: L (3-4 weeks)
**Dependencies**: TaskClassifier, model provider APIs

### 3. ProofScore Refinement

**Problem**: ProofScore dimensions are static; no learning from past runs
**Solution**: Adaptive weights based on project type; historical baseline comparison
**Effort**: M (2-3 weeks)
**Dependencies**: v2.6.0 ProofScore, run history storage

### 4. Loop Breaker Improvements

**Problem**: Reroute system is reactive; doesn't predict loops
**Solution**: Detect loop patterns early; suggest alternative strategies proactively
**Effort**: M (2-3 weeks)
**Dependencies**: Reroute system, execution history

### 5. Council Protocol Specification

**Problem**: Multi-agent coordination is ad-hoc
**Solution**: Formal council protocol: propose → debate → vote → execute
**Effort**: XL (4-6 weeks)
**Dependencies**: Multi-agent infrastructure

### 6. Memory Compactor Design

**Problem**: Session context grows unbounded; expensive to maintain
**Solution**: Compress old context into structured summaries; tiered memory (hot/warm/cold)
**Effort**: L (3-4 weeks)
**Dependencies**: CMMS memory tiers
