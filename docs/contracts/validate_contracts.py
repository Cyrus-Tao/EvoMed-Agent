# -*- coding: utf-8 -*-
"""契约校验器：零第三方依赖的 JSON Schema 子集实现。

支持关键字：type / required / properties / additionalProperties / items /
enum / const / pattern / minimum / maximum / minItems / oneOf / $ref(#/$defs/x)

用法：python docs/contracts/validate_contracts.py
退出码 0 = 全部通过；1 = 存在违规。
"""
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
POC_OUT = os.path.join(ROOT, "poc", "out")

TYPE_MAP = {
    "object": dict, "array": list, "string": str,
    "boolean": bool, "null": type(None),
}


def type_ok(value, t):
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    return isinstance(value, TYPE_MAP.get(t, object))


def validate(value, schema, root, path="$"):
    errors = []
    if not isinstance(schema, dict) or not schema:
        return errors

    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            return ["%s: 不支持的 $ref %s" % (path, ref)]
        target = root.get("$defs", {}).get(ref.rsplit("/", 1)[-1])
        if target is None:
            return ["%s: 未找到 $defs 定义 %s" % (path, ref)]
        return validate(value, target, root, path)

    if "const" in schema and value != schema["const"]:
        errors.append("%s: 值应为 %r，实际 %r" % (path, schema["const"], value))
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s: 值 %r 不在允许集合 %r" % (path, value, schema["enum"]))
    if "oneOf" in schema:
        hits = sum(1 for sub in schema["oneOf"] if not validate(value, sub, root, path))
        if hits != 1:
            errors.append("%s: oneOf 命中 %d 个分支（应恰好 1 个）: %r" % (path, hits, value))

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(type_ok(value, t) for t in types):
            errors.append("%s: 类型应为 %s，实际 %s" % (path, "/".join(types), type(value).__name__))
            return errors

    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append("%s: %r 不匹配 %s" % (path, value, schema["pattern"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: %r < 最小值 %r" % (path, value, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: %r > 最大值 %r" % (path, value, schema["maximum"]))

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append("%s: 缺少必填字段 %s" % (path, key))
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, val in value.items():
            sub = "%s.%s" % (path, key)
            if key in props:
                errors += validate(val, props[key], root, sub)
            elif extra is False:
                errors.append("%s: 不允许的额外字段 %s" % (path, key))
            elif isinstance(extra, dict):
                errors += validate(val, extra, root, sub)

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append("%s: 数组长度 %d < minItems %d" % (path, len(value), schema["minItems"]))
        if "items" in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], root, "%s[%d]" % (path, i))
    return errors


def main():
    checks = [
        ("asset_card.schema.json", [os.path.join(POC_OUT, "asset_cards.json")]),
        ("ontology.schema.json", [
            os.path.join(POC_OUT, "ontology_v0.1.0.json"),
            os.path.join(POC_OUT, "ontology_0.2.0.json"),
        ]),
        ("trace.schema.json", [os.path.join(POC_OUT, "trace_sample.json")]
         + sorted(glob.glob(os.path.join(POC_OUT, "traces", "*.json")))),
    ]
    total, failed = 0, 0
    for schema_name, artifacts in checks:
        with open(os.path.join(HERE, schema_name), encoding="utf-8") as f:
            schema = json.load(f)
        for artifact in artifacts:
            if not os.path.exists(artifact):
                print("  MISS  %s（产物缺失）" % os.path.relpath(artifact, ROOT))
                total += 1
                failed += 1
                continue
            with open(artifact, encoding="utf-8") as f:
                data = json.load(f)
            errs = validate(data, schema, schema)
            total += 1
            label = "%s  <-  %s" % (schema_name, os.path.relpath(artifact, ROOT))
            if errs:
                failed += 1
                print("  FAIL  %s" % label)
                for e in errs[:6]:
                    print("        " + e)
                if len(errs) > 6:
                    print("        ... 另有 %d 条" % (len(errs) - 6))
            else:
                print("  PASS  %s" % label)

    with open(os.path.join(HERE, "eval_split.schema.json"), encoding="utf-8") as f:
        s = json.load(f)
    if s.get("x-no-artifact"):
        print("  SKIP  eval_split.schema.json（配置契约，W7 落盘后纳入校验）")

    print("\n%d 项校验，%d 项通过，%d 项失败" % (total, total - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
