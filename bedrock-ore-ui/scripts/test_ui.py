"""Offline regressions for the shipped controls. Run with Python 3."""
import copy
import json
import importlib.util
from types import ModuleType
from unittest.mock import Mock, patch
import sys
import tempfile
import unittest
from pathlib import Path

from validate_ui import validate

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "assets/layout"))
import hud_layout as model


class LayoutTests(unittest.TestCase):
    def test_first_launch_and_partial_records(self):
        self.assertEqual(model.normalize({}), model.defaults())
        self.assertEqual(model.normalize(None), model.defaults())
        state = model.normalize({"version": 1, "buttons": {"entry": {"x": 0, "y": "nan", "scale": -3}}})
        self.assertEqual(state["layout"], model.defaults()["layout"])
        self.assertEqual(state["entry"]["x"], 0)
        self.assertEqual(state["entry"]["y"], model.defaults()["entry"]["y"])
        self.assertEqual(state["entry"]["scale"], model.LIMITS["scale"][0])

    def test_future_version_is_not_a_new_save(self):
        with self.assertRaises(ValueError):
            model.normalize({"version": 2, "buttons": {}})

    def test_share_roundtrip_and_invalid_import(self):
        state = model.defaults()
        state["layout"].update(x=0.26, y=0.68, scale=1.4, alpha=0.5)
        self.assertEqual(state, model.decode(model.encode(state)))
        for raw in ("", model.PREFIX + "{}", model.PREFIX + "x" * 17000,
                    model.encode(state).replace("0.26", "NaN"), model.encode(state).replace("1.4", "900")):
            with self.subTest(raw=raw[:35]), self.assertRaises(ValueError):
                model.decode(raw)

    def test_drag_edges_and_resize(self):
        key = "entry"
        item = model.defaults()[key]
        origin, size, travel = model.geometry(key, item, (320, 180))
        model.drag_position(item, origin, (-999, 999), travel)
        self.assertEqual((item["x"], item["y"]), (0, 1))
        for area in ((320, 180), (720, 300), (120, 400), (18, 10)):
            pos, size, travel = model.geometry(key, item, area)
            self.assertEqual(pos, (0, travel[1]))
            self.assertTrue(all(0 <= p and p + n <= limit for p,n,limit in zip(pos,size,area)))
        before = dict(item)
        model.drag_position(item, (0,0), (100,100), (0,0))
        self.assertEqual(item, before)


class EditorTests(unittest.TestCase):
    def setUp(self):
        modules = {name: ModuleType(name) for name in
                   ("mod", "mod.client", "mod.client.extraClientApi", "layout_fixture")}
        self.api = modules["mod.client.extraClientApi"]
        modules["mod"].client = modules["mod.client"]
        modules["mod.client"].extraClientApi = self.api
        modules["layout_fixture"].hud_layout = model
        binder = Mock()
        binder.binding.side_effect = lambda *args: lambda fn: fn
        self.api.GetScreenNodeCls = lambda: object
        self.api.GetViewBinderCls = lambda: binder
        self.api.GetViewViewRequestCls = Mock()
        self.api.GetUI = Mock()
        self.api.PopScreen = Mock()
        spec = importlib.util.spec_from_file_location("layout_fixture.hud_editor", SKILL / "assets/layout/hud_editor.py")
        self.runtime = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.runtime)
        self.storage = Mock()
        self.runtime.config = lambda: self.storage
        self.storage.GetConfigData.return_value = {}
        self.editor = self.runtime.LayoutEditor()
        self.editor.GetBaseUIControl = Mock(return_value=None)
        self.editor.mouse_mode = Mock()
        self.editor.Create()

    def test_failed_save_keeps_draft_cancel_leaves_original(self):
        self.editor.Larger({})
        self.storage.SetConfigData.return_value = False
        self.editor.Save({})
        self.assertEqual(self.editor.draft["entry"]["scale"], 1.1)
        self.api.PopScreen.assert_not_called()
        self.api.GetUI.assert_not_called()
        self.editor.Close({})
        self.storage.SetConfigData.assert_called_once()
        self.api.PopScreen.assert_called_once()

    def test_unknown_record_cannot_be_overwritten(self):
        self.storage.GetConfigData.return_value = {"version": 7, "buttons": {}}
        self.editor.Create()
        self.editor.Reset({})
        self.editor.Save({})
        self.storage.SetConfigData.assert_not_called()
        self.api.PopScreen.assert_not_called()

    def test_share_invalid_paste_and_save(self):
        codes = {}
        def clipboard(method, *args):
            if args:
                codes["value"] = args[0]
            return codes["value"]
        self.editor.clipboard = clipboard
        self.editor.Larger({})
        edited = copy.deepcopy(self.editor.draft)
        self.editor.Copy({})
        self.editor.Reset({})
        self.editor.Paste({})
        self.assertEqual(self.editor.draft, edited)
        codes["value"] = "invalid"
        self.editor.Paste({})
        self.assertEqual(self.editor.draft, edited)
        self.storage.SetConfigData.assert_not_called()
        self.storage.SetConfigData.return_value = True
        self.editor.Save({})
        self.storage.SetConfigData.assert_called_once_with(model.CONFIG_KEY, model.payload(edited), True)
        self.api.GetUI.return_value.apply_layout.assert_called_once_with(edited)

    def test_touch_capture_release_and_cancel(self):
        def touch(x, y, finger):
            return dict(TouchPosX=x, TouchPosY=y, TouchId=finger)
        control = Mock()
        self.editor.GetBaseUIControl = lambda path: control if path == "/canvas/entry" else None
        self.editor.bind_handles()
        cancel = control.asButton.return_value.SetButtonTouchCancelCallback.call_args[0][0]
        self.editor.area = (320, 180)
        self.editor.down("entry", touch(60, 84, 1))
        self.editor.up("entry", touch(5, 6, 2))
        self.assertTrue(self.editor.drag)
        self.editor.up("entry", touch(20, 30, 1))
        self.assertIsNone(self.editor.drag)
        item = self.editor.draft["entry"]
        self.assertLess(item["x"], model.defaults()["entry"]["x"])
        self.assertEqual(item["y"], 0)
        self.editor.down("entry", touch(20, 30, 1))
        self.editor.move("entry", touch(50, 60, 1))
        last = dict(item)
        cancel(touch(70, 80, 1))
        self.assertGreater(item["x"], last["x"])
        self.assertGreater(item["y"], last["y"])
        self.assertIsNone(self.editor.drag)

    def test_hud_retries_late_children(self):
        hud = self.runtime.LayoutHud()
        canvas = Mock()
        canvas.GetSize.return_value = (320, 180)
        nodes = {"/canvas": canvas, "/canvas/entry": Mock()}
        hud.GetBaseUIControl = nodes.get
        hud.Create()
        self.assertIsNone(hud.area)
        nodes["/canvas/layout"] = Mock()
        hud.Update()
        self.assertEqual(hud.area, (320, 180))
        nodes["/canvas/layout"].SetSize.assert_called_once_with((54, 18))


class UiValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rp = Path(self.temp.name)
        self.ui = self.rp / "ui"
        self.ui.mkdir()
        self.registry = self.ui / "_ui_defs.json"
        self.registry.write_text('{"ui_defs":["ui/style.json","ui/layout.json"]}', encoding="utf-8")
        self.style = json.loads((SKILL / "assets/ui/ore_style.json").read_text(encoding="utf-8-sig"))
        self.layout = json.loads((SKILL / "assets/layout/ore_layout.json").read_text(encoding="utf-8-sig"))
        self.save()

    def save(self):
        for name, data in (("style", self.style), ("layout", self.layout)):
            (self.ui/(name+".json")).write_text(json.dumps(data), encoding="utf-8")

    def problems(self):
        return validate(self.rp, ())  # These fixtures intentionally omit textures.

    def test_clean_templates(self):
        self.assertEqual(self.problems(), [])

    def test_native_slider_contract(self):
        for target in ("$native_slider_background", "$native_slider_progress"):
            original = copy.deepcopy(self.style)
            controls = self.style["slider_view"]["controls"]
            controls[:] = [c for c in controls if not next(iter(c)).startswith(target + "@")]
            self.save()
            issues = self.problems()
            for state in ("slider_bar_default", "slider_bar_hover"):
                self.assertTrue(any(state in err and "missing" in err for err in issues), issues)
            self.style = original

    def test_ignored_native_progress_is_missing(self):
        children = self.style["slider_view"]["controls"]
        entry = next(c for c in children if next(iter(c)).startswith("$native_slider_progress@"))
        next(iter(entry.values()))["ignored"] = True
        self.save()
        self.assertTrue(any("missing slider_progress" in err for err in self.problems()))

    def test_missing_texture_and_template(self):
        self.layout["broken@ore_style.not_found"] = {"texture":"textures/custom/absent"}
        self.save()
        result = validate(self.rp, ("textures/custom/",))
        self.assertTrue(any("missing texture" in e for e in result))
        self.assertTrue(any("missing template" in e for e in result))

    def test_duplicates_and_cycle(self):
        self.layout["a@ore_layout.b"] = {}
        self.layout["b@ore_layout.a"] = {}
        self.save()
        self.assertTrue(any("cycle" in e for e in self.problems()))
        self.registry.write_text('{"ui_defs":[],"ui_defs":[]}', encoding="utf-8")
        self.assertTrue(any("duplicate key" in e for e in self.problems()))

    def test_callback_typo(self):
        bp = self.rp / "bp"
        bp.mkdir()
        (bp / "screen.py").write_text('@Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Save")\ndef Save(self,args): pass\n')
        issues = validate(self.rp, (), bp, ["ore_editor"])
        self.assertFalse(any(e.endswith("#ore_editor.Save") for e in issues))
        self.assertTrue(any(e.endswith("#ore_editor.Close") for e in issues))


if __name__ == "__main__":
    unittest.main()
