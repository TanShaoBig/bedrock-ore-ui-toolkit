# -*- coding: utf-8 -*-
import mod.client.extraClientApi as clientApi


class LabClient(clientApi.GetClientSystemCls()):
    def __init__(self, namespace, name):
        super(LabClient, self).__init__(namespace, name)
        self.ListenForEvent(clientApi.GetEngineNamespace(), clientApi.GetEngineSystemName(),
                            "UiInitFinished", self, self.on_ui_ready)
        self.ListenForEvent(clientApi.GetEngineNamespace(), clientApi.GetEngineSystemName(),
                            "OnKeyPressInGame", self, self.on_key)
        self.ready = False

    def on_ui_ready(self, args):
        for name, cls in (("launcher", "LabLauncher"), ("gallery", "LabGallery")):
            clientApi.RegisterUI("OreLab", name, "OreLabScripts.screen." + cls, "orelab." + name)
        clientApi.CreateUI("OreLab", "launcher", {"isHud": 1})
        self.ready = True

    def on_key(self, args):
        if self.ready and str(args.get("key")) == "79" and args.get("isDown") in (1, "1"):
            if clientApi.GetTopScreen() is None:
                clientApi.PushScreen("OreLab", "gallery")
