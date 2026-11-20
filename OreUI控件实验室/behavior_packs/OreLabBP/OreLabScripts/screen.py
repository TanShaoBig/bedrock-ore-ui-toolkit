# -*- coding: utf-8 -*-
import math
import time

import mod.client.extraClientApi as clientApi

Screen = clientApi.GetScreenNodeCls()
Bind = clientApi.GetViewBinderCls()
Request = clientApi.GetViewViewRequestCls()


class LabLauncher(Screen):
    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_launcher.Open")
    def Open(self, args):
        clientApi.PushScreen("OreLab", "gallery")
        return Request.Nothing


class LabGallery(Screen):
    def __init__(self, namespace, name, param):
        super(LabGallery, self).__init__(namespace, name, param)
        self.switch_motion = None
        self.category = "selection"
        self.slider_motion = {}
        self.slider_positions = {"amount": 0.5, "quality": 0.5}
        self.defaults()

    def defaults(self):
        self.enabled = True
        self.detailed = True
        self.step = 1
        self.count = 0
        self.amount = 0.5
        self.level_index = 2
        self.sample_name = ""
        self.message = "就绪"

    def feedback(self, message):
        self.message = message
        return Request.Refresh

    def change_count(self, delta):
        self.count = max(0, min(9999, self.count + delta))
        return self.feedback("已调整计数")

    def select_category(self, category):
        if category != self.category:
            self.category = category
            if category == "numbers":
                self.sync_sliders()
            else:
                self.slider_motion.clear()
        return Request.Refresh

    def list_control(self, section, relative):
        viewport = self.GetBaseUIControl("/body_" + section).asScrollView()
        return self.GetBaseUIControl(viewport.GetScrollViewContentPath() + relative)

    def switch_position(self, now):
        start, end, since, duration, panel, image = self.switch_motion
        t = min(1.0, max(0.0, (now - since) / duration))
        return end + (start - end) * (1.0 - t) ** 2

    def animate_switch(self, enabled):
        now = time.time()
        start = self.switch_position(now) if self.switch_motion else float(self.enabled)
        end = float(enabled)
        panel = self.list_control("selection", "/allow/field/transition")
        frame = panel.GetChildByName("frame").asImage()
        self.switch_motion = (start, end, now, max(0.04, 0.14 * abs(end - start)), panel, frame)
        frame.SetSpriteUV((30 * int(round(14 * start)), 0))
        panel.SetVisible(True)

    # The native slider owns input and values. Only the two rendered skins follow.
    def slider_parts(self, row):
        slider = self.list_control("numbers", "/" + row + "/field/slider")
        skins = [slider.GetChildByName(name) for name in ("slider_bar_default", "slider_bar_hover")]
        return [(skin.GetChildByName("thumb"), skin.GetChildByName("fill")) for skin in skins]

    def place_thumb(self, row, parts, position):
        self.slider_positions[row] = position
        offset = {"followType": "parent", "relativeValue": position}
        for thumb, fill in parts:
            thumb.SetFullPosition("x", offset)
            fill.SetFullSize("x", offset)

    def sync_sliders(self):
        self.slider_motion.clear()
        for row, position in (("amount", self.amount), ("quality", self.level_index / 4.0)):
            self.place_thumb(row, self.slider_parts(row), position)

    def follow_input(self, row, target):
        if self.category != "numbers":
            return
        now = time.time()
        motion = self.slider_motion.get(row)
        if motion:
            if motion["target"] == target:
                return
            self.advance_thumb(row, motion, now)
        if self.slider_positions[row] == target:
            self.slider_motion.pop(row, None)
            return
        parts = motion["parts"] if motion else self.slider_parts(row)
        self.slider_motion[row] = {"target": target, "last": now, "parts": parts}

    def advance_thumb(self, row, motion, now):
        # 65 ms time constant. Reversing changes the target, never the drawn position.
        dt = max(0.0, now - motion["last"])
        target = motion["target"]
        delta = (self.slider_positions[row] - target) * math.exp(-dt / 0.065)
        position = target if abs(delta) < 0.0003 else target + delta
        self.place_thumb(row, motion["parts"], position)
        motion["last"] = now
        if position == target:
            self.slider_motion.pop(row, None)

    def Update(self):
        if not (self.switch_motion or self.slider_motion):
            return
        now = time.time()
        if self.switch_motion:
            start, end, since, duration, panel, image = self.switch_motion
            image.SetSpriteUV((30 * int(round(14 * self.switch_position(now))), 0))
            if now >= since + duration:
                panel.SetVisible(False)
                self.switch_motion = None
        for row, motion in list(self.slider_motion.items()):
            self.advance_thumb(row, motion, now)

    @Bind.binding(Bind.BF_BindBool, "#orelab_gallery.ShowSelection")
    def ShowSelection(self):
        return self.category == "selection"

    @Bind.binding(Bind.BF_BindBool, "#orelab_gallery.ShowNumbers")
    def ShowNumbers(self):
        return self.category == "numbers"

    @Bind.binding(Bind.BF_BindBool, "#orelab_gallery.ShowActions")
    def ShowActions(self):
        return self.category == "actions"

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.JumpSelect")
    def JumpSelect(self, args):
        return self.select_category("selection")

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.JumpNumber")
    def JumpNumber(self, args):
        return self.select_category("numbers")

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.JumpAction")
    def JumpAction(self, args):
        return self.select_category("actions")

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.Back")
    def Back(self, args):
        clientApi.PopScreen()
        return Request.Nothing

    @Bind.binding(Bind.BF_ToggleChanged, "#orelab_gallery.ToggleEnabled")
    def ToggleEnabled(self, args):
        enabled = bool(args["state"])
        if self.enabled == enabled:
            return Request.Nothing
        self.animate_switch(enabled)
        self.enabled = enabled
        return self.feedback("测试按钮已启用" if self.enabled else "测试按钮已禁用")

    @Bind.binding(Bind.BF_BindBool, "#orelab_gallery.Enabled")
    def Enabled(self):
        return self.enabled

    @Bind.binding(Bind.BF_ToggleChanged, "#orelab_gallery.ToggleDetail")
    def ToggleDetail(self, args):
        self.detailed = bool(args["state"])
        return self.feedback("已切换反馈模式")

    @Bind.binding(Bind.BF_BindBool, "#orelab_gallery.Detailed")
    def Detailed(self):
        return self.detailed

    def set_step(self, value):
        self.step = value
        return self.feedback("步长已设为 %d" % value)

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.One")
    def One(self, args):
        return self.set_step(1)

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.Five")
    def Five(self, args):
        return self.set_step(5)

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.Ten")
    def Ten(self, args):
        return self.set_step(10)

    @Bind.binding(Bind.BF_BindBool, "#orelab_gallery.IsOne")
    def IsOne(self):
        return self.step == 1

    @Bind.binding(Bind.BF_BindBool, "#orelab_gallery.IsFive")
    def IsFive(self):
        return self.step == 5

    @Bind.binding(Bind.BF_BindBool, "#orelab_gallery.IsTen")
    def IsTen(self):
        return self.step == 10

    @Bind.binding(Bind.BF_SliderChanged | Bind.BF_SliderFinished, "#orelab_gallery.Slide")
    def Slide(self, value, finished, unused):
        self.amount = max(0.0, min(1.0, float(value)))
        self.follow_input("amount", self.amount)
        if finished:
            self.message = "填充比例已调整"
        return Request.Refresh

    @Bind.binding(Bind.BF_BindFloat, "#orelab_gallery.Amount")
    def Amount(self):
        return self.amount

    @Bind.binding(Bind.BF_BindFloat, "#orelab_gallery.Unfilled")
    def Unfilled(self):
        return 1.0 - self.amount

    @Bind.binding(Bind.BF_BindInt, "#orelab_gallery.Steps")
    def Steps(self):
        return 1

    @Bind.binding(Bind.BF_SliderChanged | Bind.BF_SliderFinished, "#orelab_gallery.ChooseLevel")
    def ChooseLevel(self, value, finished, unused):
        self.level_index = max(0, min(4, int(round(value))))
        self.follow_input("quality", self.level_index / 4.0)
        if finished:
            self.message = "已选择 %s 档" % self.LevelLabel()
        return Request.Refresh

    @Bind.binding(Bind.BF_BindInt, "#orelab_gallery.LevelSteps")
    def LevelSteps(self):
        return 5

    @Bind.binding(Bind.BF_BindFloat, "#orelab_gallery.LevelIndex")
    def LevelIndex(self):
        return float(self.level_index)

    @Bind.binding(Bind.BF_BindString, "#orelab_gallery.LevelLabel")
    def LevelLabel(self):
        return str(1 << self.level_index)

    @Bind.binding(Bind.BF_BindString, "#orelab_gallery.Percent")
    def Percent(self):
        return "%d％" % int(round(self.amount * 100))

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.Minus")
    def Minus(self, args):
        return self.change_count(-self.step)

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.Plus")
    def Plus(self, args):
        return self.change_count(self.step)

    @Bind.binding(Bind.BF_BindString, "#orelab_gallery.Count")
    def Count(self):
        return str(self.count)

    @Bind.binding(Bind.BF_EditChanged | Bind.BF_EditFinished, "#orelab_gallery.Edit")
    def Edit(self, args):
        self.sample_name = args.get("Text", "")
        return Request.Refresh

    @Bind.binding(Bind.BF_BindString, "#orelab_gallery.Name")
    def Name(self):
        return self.sample_name

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.Try")
    def Try(self, args):
        if not self.enabled:
            return Request.Nothing
        self.change_count(self.step)
        return self.feedback("点击成功")

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.Inspect")
    def Inspect(self, args):
        return self.feedback("填充 %s · 计数 %d" % (self.Percent(), self.count))

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.Reset")
    def Reset(self, args):
        self.defaults()
        return self.feedback("已恢复默认")

    @Bind.binding(Bind.BF_ButtonClickUp, "#orelab_gallery.Clear")
    def Clear(self, args):
        self.count = 0
        return self.feedback("已清零")

    @Bind.binding(Bind.BF_BindString, "#orelab_gallery.Status")
    def Status(self):
        name = self.sample_name
        if isinstance(name, unicode):
            name = name.encode("utf-8")
        parts = [name, self.message]
        if self.detailed and self.message != "就绪" and not self.message.startswith("填充 "):
            parts.append("计数 %d" % self.count)
        return " · ".join(part for part in parts if part)
