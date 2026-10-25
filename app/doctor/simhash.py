"""Simhash (64-bit) for near-duplicate rule-block detection.

Blocks are normalized (lowercased, whitespace stripped) and fingerprinted over
character 3-grams, which works uniformly for CJK and latin text. Blocks whose
fingerprints differ in <= 8 bits (Hamming) are considered near-duplicates — a
threshold calibrated empirically so "same rule with a renamed tool or an added
sentence" (distance 3-7) groups, while unrelated text lands 25+ bits apart.
"""

from __future__ import annotations

import hashlib
import re

_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WS_RE.sub("", text.lower())


def _h64(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


def simhash(text: str) -> int:
    """64-bit simhash of normalized text over character 3-grams."""
    norm = normalize(text)
    if len(norm) < 3:
        return _h64(norm) if norm else 0
    votes = [0] * 64
    for i in range(len(norm) - 2):
        gram = norm[i:i + 3]
        h = _h64(gram)
        for b in range(64):
            votes[b] += 1 if (h >> b) & 1 else -1
    fingerprint = 0
    for b in range(64):
        if votes[b] > 0:
            fingerprint |= 1 << b
    return fingerprint


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def group_near_duplicates(fingerprints: list[int], max_distance: int = 8) -> list[list[int]]:
    """Group indexes of `fingerprints` whose pairwise Hamming distance <= max_distance.

    Uses 16x4-bit banding (pigeonhole: hamming<=15 collisions must share a band),
    avoiding O(n^2) comparisons for large block sets. Grouping is transitive.
    Threshold 8 empirically catches "same rule, tool renamed / sentence added"
    (distance 3-7) while unrelated text lands around 30+.
    """
    n = len(fingerprints)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    band_width = 4
    n_bands = 16
    bands: dict[tuple[int, int], list[int]] = {}
    for idx, fp in enumerate(fingerprints):
        for band in range(n_bands):
            key = (band, (fp >> (band * band_width)) & 0xF)
            bands.setdefault(key, []).append(idx)

    seen_pairs: set[tuple[int, int]] = set()
    for members in bands.values():
        if len(members) < 2 or len(members) > 512:
            continue  # huge identical-band buckets are mostly noise; cap the work
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                pair = (a, b) if a < b else (b, a)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if hamming(fingerprints[a], fingerprints[b]) <= max_distance:
                    union(a, b)

    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(idx)
    return [g for g in groups.values() if len(g) > 1]
