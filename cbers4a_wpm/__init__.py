# -*- coding: utf-8 -*-
"""Entrada do complemento CBERS-4A WPM para QGIS 4."""


def classFactory(iface):
    from .plugin import Cbers4aWpmPlugin
    return Cbers4aWpmPlugin(iface)
