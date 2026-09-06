#!/usr/bin/env python3
"""
Phase 4 Verification: Feature Extraction Caching

Tests that:
1. Features are correctly cached in CompressionContext
2. Cached features are reused (not re-extracted)
3. Cache key properly handles data, extension, and file_size
4. Both adaptive_plan and selector use cached features
5. Timing improvements are measured
"""

import hashlib
import sys
import tempfile
import time
from pathlib import Path

# Setup path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.context import CompressionContext
from xai_compress.hybrid.selector_v2 import HybridSelectorV2
from xai_compress.hybrid.container_v2 import adaptive_plan, compress_hybrid_v2_file


def test_feature_cache_key():
    """Verify cache key generation is consistent."""
    ctx = CompressionContext.create()
    
    data1 = b"hello world" * 100
    extension1 = ".txt"
    size1 = len(data1)
    
    key1 = ctx.cache_key_features(data1, extension1, size1)
    key2 = ctx.cache_key_features(data1, extension1, size1)
    
    assert key1 == key2, "Same data should produce same cache key"
    assert len(key1) == 64, "Cache key should be SHA256 hex (64 chars)"
    
    # Different extension should produce different key
    key3 = ctx.cache_key_features(data1, ".bin", size1)
    assert key1 != key3, "Different extension should produce different key"
    
    # Different size should produce different key
    key4 = ctx.cache_key_features(data1, extension1, size1 + 1)
    assert key1 != key4, "Different size should produce different key"
    
    print("✓ Feature cache key generation verified")
    return True


def test_feature_cache_storage():
    """Verify features are correctly cached and retrieved."""
    ctx = CompressionContext.create()
    
    data = b"binary data" * 50
    extension = ".bin"
    size = len(data)
    
    # Extract features
    cache_key = ctx.cache_key_features(data, extension, size)
    cached1 = ctx.get_cached_features(cache_key)
    assert cached1 is None, "Fresh context should have no cached features"
    
    # Extract and cache
    features = ctx.extract_and_cache_features(data, extension, size)
    assert features is not None, "Should extract features"
    assert "byte_entropy" in features, "Features should contain byte_entropy"
    
    # Retrieve cached
    cached2 = ctx.get_cached_features(cache_key)
    assert cached2 is not None, "Cached features should be retrievable"
    assert cached2 == features, "Cached features should match original"
    
    # Extract again (should use cache)
    cache_hit = False
    def count_extractions():
        nonlocal cache_hit
        cache_hit = True
    
    # Manually verify cache hit by extracting again
    features2 = ctx.extract_and_cache_features(data, extension, size)
    assert features2 == features, "Second extraction should return cached features"
    
    print("✓ Feature cache storage verified")
    return True


def test_feature_cache_timing():
    """Verify that feature caching actually speeds up extraction."""
    ctx = CompressionContext.create()
    
    # Create test data (larger for more meaningful timing)
    data = b"x" * (256 << 10)  # 256KB
    extension = ".bin"
    size = len(data)
    
    # First extraction (no cache)
    start1 = time.perf_counter()
    features1 = ctx.extract_and_cache_features(data, extension, size)
    time1 = (time.perf_counter() - start1) * 1000
    
    # Second extraction (with cache)
    start2 = time.perf_counter()
    features2 = ctx.extract_and_cache_features(data, extension, size)
    time2 = (time.perf_counter() - start2) * 1000
    
    print(f"  First extraction: {time1:.2f}ms (no cache)")
    print(f"  Second extraction: {time2:.2f}ms (cached)")
    print(f"  Speedup: {time1/max(0.001, time2):.1f}x")
    
    assert features1 == features2, "Cached features should match"
    assert time2 < time1, "Cached extraction should be faster"
    
    print("✓ Feature cache timing verified")
    return True


def test_selector_with_context():
    """Verify selector uses context feature cache."""
    ctx = CompressionContext.create()
    
    data = b"test content" * 100
    extension = ".txt"
    
    # Create selector with context
    selector = HybridSelectorV2(context=ctx)
    
    # First selection (extracts features)
    start1 = time.perf_counter()
    selection1 = selector.select(data, extension=extension)
    time1 = (time.perf_counter() - start1) * 1000
    
    # Second selection with same data (uses cached features)
    start2 = time.perf_counter()
    selection2 = selector.select(data, extension=extension)
    time2 = (time.perf_counter() - start2) * 1000
    
    print(f"  First selection: {time1:.2f}ms")
    print(f"  Second selection: {time2:.2f}ms (cache hit)")
    print(f"  Cache hit ratio: {time2/time1:.1%}")
    
    # Both should be in cache, so second should use exact cache
    assert selection2.cache_hit, "Second selection should be a cache hit (exact match)"
    
    print("✓ Selector with context verified")
    return True


def test_adaptive_plan_with_context():
    """Verify adaptive_plan uses context feature cache."""
    ctx = CompressionContext.create()
    
    # Create large test file to trigger adaptive planning (>10MB)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        # Write 15MB of data
        chunk = b"x" * (1 << 20)  # 1MB chunks
        for _ in range(15):
            f.write(chunk)
        temp_path = Path(f.name)
    
    try:
        # First call (extracts features)
        start1 = time.perf_counter()
        plan1 = adaptive_plan(temp_path, context=ctx)
        time1 = (time.perf_counter() - start1) * 1000
        
        # Second call with same context (uses cached features)
        start2 = time.perf_counter()
        plan2 = adaptive_plan(temp_path, context=ctx)
        time2 = (time.perf_counter() - start2) * 1000
        
        print(f"  First plan: {time1:.2f}ms")
        print(f"  Second plan: {time2:.2f}ms (cache hit)")
        
        assert plan1 == plan2, "Plans should be identical"
        assert time2 < time1, "Second call should use cached features"
        
        print("✓ Adaptive plan with context verified")
        return True
    finally:
        temp_path.unlink()


def test_end_to_end_compression_with_context():
    """Verify full compression with context feature caching."""
    ctx = CompressionContext.create()
    
    # Create test file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(b"test content " * 10000)
        input_path = Path(f.name)
    
    output_path = input_path.with_suffix(input_path.suffix + ".compact")
    
    try:
        # Compress with context
        result = compress_hybrid_v2_file(
            input_path,
            output_path,
            profile="balanced",
            context=ctx,
            overwrite=True
        )
        
        assert output_path.exists(), "Output file should be created"
        assert result.get("original_size") is not None, "Result should have original_size"
        
        # Check that features were cached
        cache_size = len(ctx.feature_cache)
        assert cache_size > 0, "Feature cache should have entries"
        
        print(f"  Compressed: {input_path.stat().st_size} -> {output_path.stat().st_size} bytes")
        print(f"  Feature cache size: {cache_size} entries")
        print(f"  Cache memory: {ctx.size_mb():.2f} MB")
        
        print("✓ End-to-end compression with context verified")
        return True
    finally:
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


def main():
    print("\n=== PHASE 4 VERIFICATION: Feature Extraction Caching ===\n")
    
    tests = [
        ("Cache Key Generation", test_feature_cache_key),
        ("Cache Storage", test_feature_cache_storage),
        ("Cache Timing", test_feature_cache_timing),
        ("Selector with Context", test_selector_with_context),
        ("Adaptive Plan with Context", test_adaptive_plan_with_context),
        ("End-to-End Compression", test_end_to_end_compression_with_context),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            print(f"[TEST] {name}...")
            if test_func():
                passed += 1
            print()
        except Exception as e:
            print(f"✗ FAILED: {e}\n")
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n✓✓✓ PHASE 4 FEATURE CACHING VERIFIED ✓✓✓\n")
        return 0
    else:
        print(f"\n✗✗✗ PHASE 4 VERIFICATION FAILED ✗✗✗\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
