# -*- coding: utf-8 -*-
"""Integração com menus, barra de ferramentas e registro do Processing."""
from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication, QUrl
from qgis.PyQt.QtGui import QAction, QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsApplication

from .processing_provider.provider import (
    ALGORITHM_ID, PROVIDER_ID, Cbers4aWpmProvider,
)


class Cbers4aWpmPlugin:
    MENU = "CBERSFuse"

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.actions = []
        self._directory = Path(__file__).resolve().parent

    @staticmethod
    def tr(text):
        return QCoreApplication.translate("Cbers4aWpmPlugin", text)

    def initProcessing(self):
        """Pode ser chamado pelo QGIS sem interface gráfica (qgis_process)."""
        if self.provider is not None:
            return
        registry = QgsApplication.processingRegistry()
        if registry.providerById(PROVIDER_ID) is not None:
            raise RuntimeError("O provedor CBERSFuse já está registrado. Reinicie o QGIS.")
        provider = Cbers4aWpmProvider()
        if not registry.addProvider(provider):
            raise RuntimeError("Não foi possível registrar o provedor CBERSFuse.")
        self.provider = provider

    def initGui(self):
        self.initProcessing()
        if self.iface is None or self.actions:
            return
        run_action = QAction(
            QIcon(str(self._directory / "icon.png")),
            self.tr("Composição RGB + fusão PAN…"), self.iface.mainWindow())
        run_action.setObjectName("cbers4a_wpm_run")
        run_action.setToolTip(self.tr("Processar cenas CBERS-4A/WPM em lote"))
        run_action.triggered.connect(self.run)
        help_action = QAction(self.tr("Ajuda e instalação…"), self.iface.mainWindow())
        help_action.setObjectName("cbers4a_wpm_help")
        help_action.triggered.connect(self.show_help)
        self.actions = [run_action, help_action]
        self.iface.addToolBarIcon(run_action)
        for action in self.actions:
            self.iface.addPluginToRasterMenu(self.MENU, action)

    def run(self, checked=False):
        registry = QgsApplication.processingRegistry()
        required = (ALGORITHM_ID, "gdal:pansharp", "gdal:rearrange_bands")
        missing = [algorithm for algorithm in required
                   if registry.algorithmById(algorithm) is None]
        if missing:
            QMessageBox.warning(
                self.iface.mainWindow(), self.MENU,
                self.tr("Ative o complemento Processamento e o provedor GDAL antes de executar.\n\n")
                + self.tr("Algoritmos indisponíveis: ") + ", ".join(missing))
            return
        import processing
        processing.execAlgorithmDialog(ALGORITHM_ID)

    def show_help(self, checked=False):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._directory / "help.html")))

    def unload(self):
        if self.iface is not None:
            if self.actions:
                self.iface.removeToolBarIcon(self.actions[0])
            for action in self.actions:
                self.iface.removePluginRasterMenu(self.MENU, action)
                action.deleteLater()
        self.actions = []
        if self.provider is not None:
            # Remove apenas o provedor desta instância; não afeta o provedor Scripts.
            registry = QgsApplication.processingRegistry()
            if registry.providerById(PROVIDER_ID) is self.provider:
                registry.removeProvider(self.provider)
            self.provider = None
