"""Deterministic canonical identity for bounded AE-13 artifacts."""
import hashlib
import json


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), sort_keys=True,
                      allow_nan=False).encode('utf-8')


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def content_id(namespace, obj):
    return namespace + ':' + digest(obj)
