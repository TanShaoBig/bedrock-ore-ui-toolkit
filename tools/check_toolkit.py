"""Validate the skill, demo and distributable with Python 3.8+. Run from any directory."""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "bedrock-ore-ui"
DEMO = ROOT / "OreUI控件实验室"
BP = DEMO / "behavior_packs/OreLabBP"
RP = DEMO / "resource_packs/OreLabRP"
ADDON = ROOT / "OreUI控件实验室.mcaddon"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_files(folder):
    files = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file() and (path.name == "LICENSE" or path.suffix in {".py", ".json", ".png"}):
            data = path.read_bytes()
            if path.suffix != ".png":
                data = data.replace(b"\r\n", b"\n")
            files[path.relative_to(folder).as_posix()] = data
    return files


def match_files(expected, actual, where):
    for name in sorted(set(expected) | set(actual)):
        require(name in expected and name in actual and expected[name] == actual[name],
                "{}: missing, unexpected or changed file {}".format(where, name))


def check_sources():
    manifests = [json.loads((p / "manifest.json").read_text(encoding="utf-8-sig")) for p in (BP, RP)]
    version = manifests[0]["header"]["version"]
    ids = set()
    for manifest in manifests:
        for section in [manifest["header"]] + manifest["modules"]:
            identifier = uuid.UUID(section["uuid"])
            require(identifier not in ids, "duplicate manifest UUID")
            ids.add(identifier)
            require(section["version"] == version, "manifest version mismatch")
    dependency = {"uuid": manifests[1]["header"]["uuid"], "version": version}
    require(dependency in manifests[0]["dependencies"], "BP must depend on this RP version")
    version_label = ".".join(map(str, version))
    require('version="' + version_label + '"' in (BP / "OreLabScripts/modMain.py").read_text("utf-8"),
            "Mod.Binding version differs from manifests")
    for name in ("hud_layout.py", "hud_editor.py"):
        require((SKILL / "assets/layout" / name).read_text("utf-8") ==
                (BP / "OreLabScripts" / name).read_text("utf-8"), "template drift: " + name)
    for src, dst in (("ui/ore_style.json", "orelab_style.json"), ("layout/ore_layout.json", "orelab_layout.json")):
        template = (SKILL / "assets" / src).read_text("utf-8-sig")
        demo = (RP / "ui" / dst).read_text("utf-8-sig")
        canonical = demo.replace("orelab_style.", "ore_style.").replace('"orelab_style"', '"ore_style"')
        require(json.loads(template) == json.loads(canonical), "template drift: " + dst)
    textures = source_files(RP / "textures")
    require(bool(textures), "empty texture collection")
    for folder in (SKILL / "assets/textures", ROOT / "素材库/textures"):
        match_files(textures, source_files(folder), folder)
    for path in BP.rglob("*.py"):
        compile(path.read_bytes(), str(path), "exec")
    subprocess.run([sys.executable, "-B", str(SKILL / "scripts/test_ui.py")], check=True)
    subprocess.run([sys.executable, "-B", str(SKILL / "scripts/validate_ui.py"), str(RP),
                    "--behavior-pack", str(BP), "--binding-group", "orelab_gallery",
                    "--binding-group", "ore_editor", "--binding-group", "orelab_launcher"], check=True)
    return version_label


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def verify_addon(data, sources):
    with zipfile.ZipFile(io.BytesIO(data)) as outer:
        require(sorted(outer.namelist()) == sorted(sources), "unexpected .mcaddon contents")
        for name, files in sources.items():
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                require(len(inner.namelist()) == len(set(inner.namelist())), "duplicate archive member in " + name)
                match_files(files, {n: inner.read(n) for n in inner.namelist()}, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="rebuild the .mcaddon after validation")
    args = parser.parse_args()
    version = check_sources()
    sources = {p.name + ".mcpack": source_files(p) for p in (BP, RP)}
    if args.build:
        data = zip_bytes({name: zip_bytes(files) for name, files in sources.items()})
        verify_addon(data, sources)
        with tempfile.NamedTemporaryFile(dir=str(ROOT), delete=False) as temp:
            temp.write(data)
        try:
            os.replace(temp.name, ADDON)
        finally:
            if os.path.exists(temp.name):
                os.unlink(temp.name)
    verify_addon(ADDON.read_bytes(), sources)
    print("OK: {} templates, textures, behavior/resource sources and installable add-on".format(version))


if __name__ == "__main__":
    main()
