# -*- coding: utf-8 -*-
from functools import partial
import math
import mod.client.extraClientApi as api
from . import hud_layout as layout

Screen = api.GetScreenNodeCls()
Bind = api.GetViewBinderCls()
Request = api.GetViewViewRequestCls()
HUD_NAMESPACE = "OreLab"
HUD_NAME = "launcher"


def config():
    return api.GetEngineCompFactory().CreateConfigClient(api.GetLevelId())


def read_layout():
    return layout.normalize(config().GetConfigData(layout.CONFIG_KEY, True))


def usable_area(screen):
    canvas = screen.GetBaseUIControl("/canvas")
    if canvas:
        area = canvas.GetSize()
        if area and min(area) > 1:
            return tuple(area)
    return None


def draw_button(screen, key, item, area):
    button = screen.GetBaseUIControl("/canvas/" + key)
    if not button or not area:
        return False
    pos, size, travel = layout.geometry(key, item, area)
    button.SetSize(size)
    for axis, value in zip(("x", "y"), pos):
        button.SetFullPosition(axis, {"absoluteValue": value})
    button.SetAlpha(item["alpha"])
    return True


class LayoutHud(Screen):
    """Use as the HUD screen base. Gameplay callbacks stay on the HUD subclass."""
    def Create(self):
        self.area = None
        try:
            self.saved = read_layout()
        except Exception as error:
            print("HUD layout unavailable:", error)
            self.saved = layout.defaults()
        self.Update()

    def apply_layout(self, layout_data):
        self.saved = layout_data
        self.area = None
        self.Update()

    def Update(self):
        if not hasattr(self, "saved"):
            return
        area = usable_area(self)
        if area and area != self.area:
            ready = [draw_button(self, key, self.saved[key], area) for key in layout.BUTTONS]
            if all(ready):
                self.area = area


class LayoutEditor(Screen):
    def Create(self):
        self.drag = None
        self.area = None
        self.selected = sorted(layout.BUTTONS)[0]
        self.can_save = True
        self.mouse_enabled = False
        self.mouse_mode(True)
        self.bound = set()
        self.message = "拖动按钮调整位置"
        try:
            self.draft = read_layout()
        except Exception as error:
            print("HUD layout read failed:", error)
            self.draft = layout.defaults()
            self.can_save = False
            self.message = "布局读取失败，请返回后重试"
        self.Update()

    def bind_handles(self):
        for key in sorted(set(layout.BUTTONS) - self.bound):
            control = self.GetBaseUIControl("/canvas/" + key)
            button = control.asButton() if control else None
            if not button:
                continue
            button.AddTouchEventParams({"isSwallow": True, "is_handle_button_move_event": True})
            button.SetButtonTouchDownCallback(partial(self.down, key))
            button.SetButtonTouchMoveCallback(partial(self.move, key))
            button.SetButtonTouchUpCallback(partial(self.up, key))
            # A fast release outside the hit box can carry its only final position in Cancel.
            button.SetButtonTouchCancelCallback(partial(self.up, key))
            self.bound.add(key)
            self.area = None

    def Update(self):
        if not hasattr(self, "draft"):
            return
        if len(self.bound) < len(layout.BUTTONS):
            self.bind_handles()
        area = usable_area(self)
        if area != self.area:
            self.drag = None
            self.area = area
            self.draw()

    def draw(self):
        for key, item in self.draft.items():
            draw_button(self, key, item, self.area)
        self.status()

    def status(self):
        node = self.GetBaseUIControl("/status")
        if node:
            item = self.draft[self.selected]
            node.asLabel().SetText("%s  ·  %s  大小 %d％  不透明度 %d％" % (
                self.message, layout.BUTTONS[self.selected][0],
                round(item["scale"] * 100), round(item["alpha"] * 100)))

    def pointer(self, args):
        for prefix in ("TouchPos", "ScreenPos"):
            try:
                point = tuple(float(args[prefix + axis]) for axis in ("X", "Y"))
                if all(not math.isnan(v) and not math.isinf(v) for v in point):
                    return point
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        return None

    def down(self, key, args):
        if self.drag or not self.area:
            return
        self.selected = key
        self.status()
        point = self.pointer(args)
        if point is not None:
            origin, size, travel = layout.geometry(key, self.draft[key], self.area)
            self.drag = (key, args.get("TouchId"), point, origin, travel)

    def owns_drag(self, key, args):
        return self.drag and self.drag[:2] == (key, args.get("TouchId"))

    def move(self, key, args):
        if self.owns_drag(key, args):
            point = self.pointer(args)
            if point is not None:
                _, _, start, origin, travel = self.drag
                delta = (point[0] - start[0], point[1] - start[1])
                layout.drag_position(self.draft[key], origin, delta, travel)
                draw_button(self, key, self.draft[key], self.area)

    def up(self, key, args):
        if self.owns_drag(key, args):
            self.move(key, args)
            self.drag = None

    def edit(self, field, delta):
        item = self.draft[self.selected]
        lo, hi = layout.LIMITS[field]
        item[field] = layout.clamp(round(item[field] + delta, 2), lo, hi)
        self.drag = None
        self.draw()
        return Request.Nothing

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Smaller")
    def Smaller(self, args):
        return self.edit("scale", -0.1)

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Larger")
    def Larger(self, args):
        return self.edit("scale", 0.1)

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Dimmer")
    def Dimmer(self, args):
        return self.edit("alpha", -0.1)

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Brighter")
    def Brighter(self, args):
        return self.edit("alpha", 0.1)

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Next")
    def Next(self, args):
        keys = sorted(layout.BUTTONS)
        self.selected = keys[(keys.index(self.selected) + 1) % len(keys)]
        self.drag = None
        self.status()
        return Request.Nothing

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Reset")
    def Reset(self, args):
        self.drag = None
        self.draft = layout.defaults()
        self.message = "默认布局待保存"
        self.draw()
        return Request.Nothing

    def clipboard(self, method, *args):
        game = api.GetEngineCompFactory().CreateGame(api.GetLevelId())
        for target in (game, api):
            fn = getattr(target, method, None)
            if fn:
                try:
                    result = fn(*args)
                    if result is not False:
                        return result
                except Exception:
                    continue
        raise ValueError("clipboard unavailable")

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Copy")
    def Copy(self, args):
        try:
            self.clipboard("SetClipboardContent", layout.encode(self.draft))
            self.message = "布局码已复制"
        except Exception:
            self.message = "无法复制布局码"
        self.status()
        return Request.Nothing

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Paste")
    def Paste(self, args):
        try:
            self.draft = layout.decode(self.clipboard("GetClipboardContent"))
            self.message = "布局已导入，待保存"
            self.drag = None
        except Exception:
            self.message = "请复制有效的布局码"
        self.draw()
        return Request.Nothing

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Save")
    def Save(self, args):
        try:
            saved = self.can_save and config().SetConfigData(layout.CONFIG_KEY, layout.payload(self.draft), True)
        except Exception as error:
            print("HUD layout save failed:", error)
            saved = False
        if not saved:
            self.message = "保存失败，请重试" if self.can_save else "请重新打开编辑器，再保存"
            self.status()
            return Request.Nothing
        hud = api.GetUI(HUD_NAMESPACE, HUD_NAME)
        if hud:
            hud.apply_layout(self.draft)
        return self.Close(args)

    @Bind.binding(Bind.BF_ButtonClickUp, "#ore_editor.Close")
    def Close(self, args):
        self.drag = None
        self.mouse_mode(False)
        api.PopScreen()
        return Request.Nothing

    def mouse_mode(self, enable):
        if getattr(self, "mouse_enabled", False) == enable:
            return
        game = api.GetEngineCompFactory().CreateGame(api.GetLevelId())
        method = getattr(game, "SimulateTouchWithMouse", None)
        if method:
            try:
                if method(enable) is not False:
                    self.mouse_enabled = enable
            except Exception as error:
                print("HUD editor mouse simulation unavailable:", error)

    def OnActive(self):
        if hasattr(self, "draft"):
            self.mouse_mode(True)

    def OnDeactive(self):
        self.drag = None
        self.mouse_mode(False)

    def Destroy(self):
        self.drag = None
        self.mouse_mode(False)
