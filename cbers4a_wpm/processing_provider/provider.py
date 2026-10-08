# -*- coding: utf-8 -*-
from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .algorithm import Cbers4aWpmQgis4


PROVIDER_ID = "cbers4awpm"
ALGORITHM_ID = PROVIDER_ID + ":cbers4a_wpm_qgis4"


class Cbers4aWpmProvider(QgsProcessingProvider):
    def id(self):
        return PROVIDER_ID

    def name(self):
        return "CBERSFuse"

    def longName(self):
        return "CBERSFuse — composição RGB e fusão pancromática"

    def icon(self):
        return QIcon(str(Path(__file__).resolve().parents[1] / "icon.png"))

    def loadAlgorithms(self):
        self.addAlgorithm(Cbers4aWpmQgis4())
