"""Check a Bedrock resource pack's JSON UI with Python 3 (standard library only)."""
import argparse
import json
import re
import sys
from pathlib import Path


def read_json(path):
    # Preserve comment-looking characters inside JSON strings and line numbers in errors.
    tokens = r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/'
    text = re.sub(tokens, lambda m: m[0] if m[0][0] == '"' else
                  re.sub(r'[^\n]', ' ', m[0]), path.read_text(encoding="utf-8-sig"))
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key " + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def validate(root, texture_roots=("textures/ui/ore_style/",), behavior_pack=None, binding_groups=()):
    root = Path(root)
    errors, templates, parents, origins, namespaces = [], {}, {}, {}, set()
    def fail(where, reason):
        errors.append("%s: %s" % (where, reason))
    def load(path):
        try:
            obj = read_json(path)
            if not isinstance(obj, dict):
                raise ValueError("expected object")
            return obj
        except (OSError, ValueError) as error:
            fail(path, str(error))
            return {}
    registry = load(root / "ui/_ui_defs.json").get("ui_defs")
    if not isinstance(registry, list) or not registry:
        return errors + ["ui/_ui_defs.json: missing ui_defs list"]
    requested_bindings = set()
    seen = set()
    for name in registry:
        if not isinstance(name, str) or not name.startswith("ui/") or ".." in Path(name).parts:
            fail("ui_defs", "invalid UI path %r" % name)
            continue
        if name in seen:
            fail("ui_defs", "duplicate " + name)
            continue
        seen.add(name)
        obj = load(root / name)
        ns = obj.get("namespace")
        if not isinstance(ns, str) or not ns:
            fail(name, "missing namespace")
            continue
        def bindings(value):
            if isinstance(value, dict):
                for child in value.values():
                    bindings(child)
            elif isinstance(value, list):
                for child in value:
                    bindings(child)
            elif isinstance(value, str) and re.fullmatch(r"#\w+\.\w+", value):
                requested_bindings.add(value)
        if behavior_pack:
            bindings(obj)
        namespaces.add(ns)
        for key, value in obj.items():
            if key == "namespace" or not isinstance(value, dict):
                continue
            local, _, parent = key.partition("@")
            address = ns + "." + local
            if address in templates:
                fail(name, "duplicate definition " + address)
            templates[address], parents[address], origins[address] = value, parent, name

    def resolve(base, node, where):
        chain = set()
        while base in templates:
            if base in chain:
                fail(where, "template cycle at " + base)
                break
            chain.add(base)
            node = dict(templates[base], **node)
            base = parents[base]
        if base and base.partition(".")[0] in namespaces and base not in templates:
            fail(where, "missing template " + base)
        return base, node

    def children(node, where):
        array = node.get("controls", [])
        if not isinstance(array, list):
            fail(where, "controls must be an array")
            return
        names = set()
        for item in array:
            if not isinstance(item, dict) or len(item) != 1:
                fail(where, "invalid child entry")
                continue
            key, child = next(iter(item.items()))
            if not isinstance(child, dict):
                fail(where, "invalid control " + key)
                continue
            name, _, base = key.partition("@")
            if name in names:
                fail(where, "duplicate child " + name)
            names.add(name)
            yield name, base, child

    def native_slider(node, where):
        # Only overridden native control trees need checking. Variables on each skin
        # determine the real background/progress IDs requested by the engine.
        parts = {k:(b,c) for k,b,c in children(node, where)}
        for control in ("slider_box", "slider_bar_default", "slider_bar_hover"):
            if control not in parts:
                fail(where, "native slider missing " + control)
        for state, suffix in (("slider_bar_default", ""), ("slider_bar_hover", "_hover")):
            if state not in parts:
                continue
            base, skin = resolve(*parts[state], where)
            if base.startswith("common.") and "controls" not in skin:
                continue
            if base and base not in templates:
                continue  # External skin definition belongs to another pack.
            ids = set()
            def descend(tree, env, trail):
                variables = dict(env)
                variables.update({k.split("|")[0]:v for k,v in tree.items()
                                  if k.endswith("|default") and k.split("|")[0] not in variables})
                variables.update({k:v for k,v in tree.items() if k.startswith("$") and "|" not in k})
                for k,b,c in children(tree, where):
                    _, sub = resolve(b,c,where)
                    ignored = sub.get("ignored", False)
                    if ignored is True or (isinstance(ignored, str) and variables.get(ignored) is True):
                        continue
                    ids.add(str(variables.get(k,k)))
                    if b and b in trail:
                        fail(where, "recursive control tree " + b)
                        continue
                    descend(sub, variables, trail | {b} if b else trail)
            descend(skin, node, set())
            for field in ("slider_background", "slider_progress"):
                expected = node.get(("background" if field.endswith("background") else "progress") +
                                    ("_hover" if suffix else "") + "_control", field + suffix)
                if not isinstance(expected, str) or expected not in ids:
                    fail(where, state + " missing " + str(expected))

    def inspect(node, where):
        for k,v in node.items():
            if isinstance(v,str):
                if v.startswith(tuple(texture_roots)) and not any(
                        (root/(v+ext)).is_file() for ext in ("", ".png", ".tga")):
                    fail(where, "missing texture " + v)
                if k.startswith("$") and v.lstrip("@").partition(".")[0] in namespaces:
                    resolve(v.lstrip("@"),{},where)
        for k,b,c in children(node, where):
            path = where + "/" + k
            base, effective = resolve(b,c,path)
            if base == "common.slider" and "controls" in c:
                native_slider(effective,path)
            inspect(c,path)

    for key,node in templates.items():
        where = origins[key] + " " + key
        parent,effective = resolve(parents[key],node,where)
        if parent == "common.slider" and "controls" in node:
            native_slider(effective,where)
        inspect(node,where)
    if behavior_pack:
        calls = set()
        sources = list(Path(behavior_pack).rglob("*.py"))
        if not sources:
            fail(behavior_pack, "no Python sources")
        for source in sources:
            try:
                text = source.read_text(encoding="utf-8-sig")
            except (OSError, ValueError) as error:
                fail(source, str(error))
                continue
            calls.update(re.findall(r"""@[^()\n]+\.binding(?:_collection)?\([^)]*?["'](#\w+\.\w+)["']""", text))
        groups = set(binding_groups) or {c.split(".")[0][1:] for c in calls}
        for call in sorted(requested_bindings - calls):
            if call.split(".")[0][1:] in groups:
                fail(behavior_pack, "missing literal ViewBinder callback " + call)
    return list(dict.fromkeys(errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource_pack", type=Path)
    parser.add_argument("--texture-prefix", action="append", help="Additional owned texture path prefix")
    parser.add_argument("--behavior-pack", type=Path, help="Check literal ViewBinder decorators in this behavior pack")
    parser.add_argument("--binding-group", action="append", default=[], help="Owned #group.Action prefix without #")
    args = parser.parse_args()
    issues = validate(args.resource_pack, ["textures/ui/ore_style/"] + (args.texture_prefix or []),
                      args.behavior_pack, args.binding_group)
    print("\n".join(issues) if issues else "OK: UI definitions, local templates, owned textures and native slider nodes")
    sys.exit(int(bool(issues)))
