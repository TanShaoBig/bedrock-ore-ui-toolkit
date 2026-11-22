# -*- coding: utf-8 -*-
from mod.common.mod import Mod


@Mod.Binding(name="OreLab", version="1.1.0")
class OreLabMod(object):
    @Mod.InitClient()
    def init_client(self):
        import mod.client.extraClientApi as clientApi
        clientApi.RegisterSystem("OreLab", "client", "OreLabScripts.client.LabClient")

    @Mod.DestroyClient()
    def destroy_client(self):
        pass
