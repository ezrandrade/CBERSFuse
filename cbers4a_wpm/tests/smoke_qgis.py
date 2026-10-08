# -*- coding: utf-8 -*-
"""Execute no Console Python do QGIS após instalar e ativar o plugin."""
from qgis.core import QgsApplication

registry = QgsApplication.processingRegistry()
provider = registry.providerById("cbers4awpm")
assert provider is not None, "Ative o plugin CBERS-4A WPM."
algorithm = registry.algorithmById("cbers4awpm:cbers4a_wpm_qgis4")
assert algorithm is not None, "Algoritmo do plugin não registrado."
names = {parameter.name() for parameter in algorithm.parameterDefinitions()}
assert {"INPUT_FOLDER", "OUTPUT_FOLDER", "RED", "GREEN", "BLUE"}.issubset(names)
assert not {"REFERENCE_LAYER", "APPEARANCE", "CUT_LOWER", "CUT_UPPER"}.intersection(names)
for identifier in ("gdal:pansharp", "gdal:rearrange_bands"):
    assert registry.algorithmById(identifier) is not None, "Ative o provedor GDAL: " + identifier
print("CBERS-4A WPM: provedor, algoritmo, parâmetros e GDAL disponíveis.")
