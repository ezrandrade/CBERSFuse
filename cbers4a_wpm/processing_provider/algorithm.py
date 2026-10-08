# -*- coding: utf-8 -*-
"""CBERSFuse — composição RGB e fusão pancromática CBERS-4A/WPM

DESENVOLVEDOR
Esdras Andrade
Instituto de Geografia, Desenvolvimento e Meio Ambiente da UFAL.

USO
Abra Raster > CBERSFuse > Composição RGB + fusão PAN, ou procure
'CBERSFuse - RGB + PAN (QGIS 4)' na Caixa de Ferramentas de Processamento.
Selecione a pasta das bandas descompactadas e uma pasta de saída persistente.
Padrão: RGB 321, reamostragem cúbica, aparência padrão do QGIS (como no
primeiro script), carregar somente a imagem fusionada RGB + PAN no projeto.
Os três produtos continuam sendo salvos. Para falsa cor: R=B4, G=B3, B=B2.
A aparência e o contraste são definidos automaticamente pelo padrão do QGIS.
O estilo resultante é salvo em .qml e aplicado ao carregar a imagem fusionada.

ENTRADA
<CENA>_BAND0.tif = PAN; BAND1 = azul; BAND2 = verde; BAND3 = vermelho;
BAND4 = NIR. Somente nomes CBERS_4A_WPM_* (ou CBERS4A_WPM_*) são aceitos.
As bandas de uma cena devem estar na mesma pasta, com o mesmo prefixo.
As quatro MS devem ter a mesma grade e todas as bandas devem ter o mesmo
SRC projetado em metros, com pixels nominais de 8 m (MS) e 2 m (PAN).
Não reprojeta nem corrige erros de corregistro. Recomenda-se produto L4.

SAÍDAS POR CENA
STACK_B1_B2_B3_B4_8m.tif: quatro bandas, ordem B1/B2/B3/B4.
RGB_321_8m.tif: três bandas, ordem dos canais R/G/B escolhidos.
RGB_321_PAN_2m.tif: três bandas fusionadas, mesma ordem R/G/B.
Cada GeoTIFF recebe descrições de bandas e um estilo .qml ao lado.
Subpastas de entrada são reproduzidas na saída para evitar colisões.
Arquivos existentes nunca são sobrescritos. Um registro JSON lista sucessos,
avisos, falhas e parâmetros; cenas com falha não interrompem as restantes.

MÉTODO
GDAL Weighted Brovey, usando as QUATRO bandas MS na intensidade sintética,
com pesos iguais padrão do GDAL. Como no primeiro script, gera um produto
temporário de quatro bandas a 2 m e depois seleciona os canais RGB com
gdal:rearrange_bands. Preserva a interpretação de cor herdada do GDAL.
Esses pesos não são uma calibração da resposta espectral do sensor.
A extensão fusionada é a interseção PAN/MS. O contraste é somente um estilo
de visualização: não normaliza nem converte a radiometria para 8 bits.
Preserve os dados originais para índices e análises espectrais quantitativas.
Pirâmides de visualização opcionais acrescentam níveis reduzidos ao GeoTIFF.

DEPENDÊNCIAS
PyQGIS, osgeo.gdal/osr e algoritmo gdal:pansharp do ambiente do QGIS.
Não exige numpy, rasterio ou pacotes externos. Usa qgis.PyQt (Qt6).

VALIDAÇÃO
APIs conferidas na documentação QGIS 4.0 e GDAL; a execução real depende
da instalação local e do corregistro das cenas. Versão da rotina: 2.2.0.
Alteração 2.2.0: aparência exclusivamente definida pelo padrão do QGIS;
remove a camada de referência, os percentis e o modo de contraste personalizado.
Carrega automaticamente apenas a composição fusionada RGB + PAN.
Referências:
https://api.qgis.org/api/4.0/classQgsRasterLayer.html
https://api.qgis.org/api/4.0/classQgsProcessingContext_1_1LayerDetails.html
https://docs.qgis.org/testing/en/docs/user_manual/processing_algs/gdal/rastermiscellaneous.html
https://gdal.org/en/stable/programs/gdal_pansharpen.html
https://www.gov.br/inpe/pt-br/programas/cbers/sobre-o-cbers-1/cbers-04a/cameras-imageadoras
"""

import json
import math
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    Qgis, QgsApplication, QgsMultiBandColorRenderer,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingContext,
    QgsProcessingException, QgsProcessingLayerPostProcessorInterface,
    QgsProcessingOutputFile, QgsProcessingOutputMultipleLayers,
    QgsProcessingOutputNumber, QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum, QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingUtils, QgsRasterLayer,
)
from osgeo import gdal, osr
import processing


VERSION = "2.2.0"
CREATION_OPTIONS = ["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"]
BAND_NAMES = {1: "Azul", 2: "Verde", 3: "Vermelho", 4: "Infravermelho próximo (NIR)"}
RESAMPLING_NAMES = ["nearest", "bilinear", "cubic", "cubicspline", "lanczos", "average"]


def find_scenes(folder, recursive=True):
    """Mantém duplicatas explícitas: nunca escolhe silenciosamente um arquivo."""
    pattern = re.compile(r"^(CBERS_?4A_WPM_.+)_BAND([0-4])\.(?:tif|tiff)$", re.I)
    scenes = {}
    iterator = os.walk(folder) if recursive else [(folder, [], os.listdir(folder))]
    for root, dirs, files in iterator:
        dirs.sort()
        for filename in sorted(files):
            path = os.path.join(root, filename)
            match = pattern.fullmatch(filename)
            if not match or not os.path.isfile(path):
                continue
            key = (os.path.abspath(root), match.group(1).upper())
            scenes.setdefault(key, {}).setdefault(int(match.group(2)), []).append(path)
    return scenes


def _open(path, update=False):
    dataset = gdal.Open(path, gdal.GA_Update if update else gdal.GA_ReadOnly)
    if dataset is None:
        raise QgsProcessingException("GDAL não conseguiu abrir: " + path)
    return dataset


def _same_number(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-6)


def _nodata_equal(a, b):
    if a is None or b is None:
        return a is b
    return a == b or (math.isnan(a) and math.isnan(b))


def _extent(meta):
    gt = meta["gt"]
    return (gt[0], gt[3] + meta["height"] * gt[5],
            gt[0] + meta["width"] * gt[1], gt[3])


def validate_scene(bands):
    """Verifica metadados; não comprova precisão posicional/corregistro."""
    info = {}
    for number in range(5):
        ds = _open(bands[number])
        try:
            if ds.RasterCount != 1:
                raise QgsProcessingException(f"BAND{number}: esperado arquivo com uma banda.")
            srs = osr.SpatialReference()
            if not ds.GetProjection() or srs.ImportFromWkt(ds.GetProjection()) != 0:
                raise QgsProcessingException(f"BAND{number}: SRC ausente ou inválido.")
            if not srs.IsProjected() or not _same_number(srs.GetLinearUnits(), 1):
                raise QgsProcessingException(f"BAND{number}: use um SRC projetado em metros.")
            gt = ds.GetGeoTransform()
            resolution = 2 if number == 0 else 8
            if (not _same_number(gt[2], 0) or not _same_number(gt[4], 0)
                    or not _same_number(gt[1], resolution)
                    or not _same_number(gt[5], -resolution)):
                raise QgsProcessingException(
                    f"BAND{number}: grade deve estar orientada ao norte, com pixels de {resolution} m.")
            band = ds.GetRasterBand(1)
            info[number] = {"srs": srs, "gt": gt, "width": ds.RasterXSize,
                            "height": ds.RasterYSize, "dtype": band.DataType,
                            "nodata": band.GetNoDataValue()}
        finally:
            band = None
            ds = None
    ref = info[1]
    for number, meta in info.items():
        if not ref["srs"].IsSame(meta["srs"]):
            raise QgsProcessingException(f"BAND{number}: SRC diferente da BAND1. Reprojete antes.")
        if not _nodata_equal(ref["nodata"], meta["nodata"]):
            raise QgsProcessingException(f"BAND{number}: NoData diferente da BAND1. Harmonize antes.")
        if meta["dtype"] != ref["dtype"]:
            raise QgsProcessingException(f"BAND{number}: tipo de dados diferente da BAND1.")
        if number > 1 and (meta["width"] != ref["width"] or meta["height"] != ref["height"]
                or not all(_same_number(a, b) for a, b in zip(meta["gt"], ref["gt"]))):
            raise QgsProcessingException(f"BAND{number}: grade MS diferente da BAND1. Alinhe antes.")
    pan, ms = _extent(info[0]), _extent(ref)
    if min(pan[2], ms[2]) <= max(pan[0], ms[0]) or min(pan[3], ms[3]) <= max(pan[1], ms[1]):
        raise QgsProcessingException("PAN e multiespectral não possuem sobreposição espacial.")
    return info


def _check_cancel(feedback):
    if feedback.isCanceled():
        raise QgsProcessingException("Processamento cancelado pelo usuário.")


def _callback(feedback):
    return lambda fraction, message, data: 0 if feedback.isCanceled() else 1


def label_output(path, source_bands, rgb=False):
    ds = _open(path, update=True)
    try:
        if ds.RasterCount != len(source_bands):
            raise QgsProcessingException("Quantidade inesperada de bandas: " + path)
        for index, source_band in enumerate(source_bands, 1):
            band = ds.GetRasterBand(index)
            prefix = "RGB"[index - 1] + " = " if rgb else ""
            band.SetDescription(f"{prefix}B{source_band} - {BAND_NAMES[source_band]}")
            # Apenas nomes: preserva interpretação de cor e valores herdados do GDAL.
        ds.SetMetadataItem("CBERS_ROUTINE_VERSION", VERSION)
        ds.SetMetadataItem("SOURCE_BAND_ORDER", ",".join(map(str, source_bands)))
        ds.FlushCache()
    finally:
        band = None
        ds = None


def save_style(path, channels, feedback):
    """Camada local fora do projeto; salva estilo sem acessar a interface."""
    _check_cancel(feedback)
    style_path = os.path.splitext(path)[0] + ".qml"
    layer = QgsRasterLayer(path, os.path.basename(path), "gdal")
    if not layer.isValid():
        raise QgsProcessingException("QGIS não conseguiu abrir a saída: " + path)
    if layer.bandCount() == 4:
        # O empilhamento tem ordem B1/B2/B3/B4; exibe a composição escolhida.
        # Os RGB de três bandas mantêm integralmente o estilo inicial do QGIS.
        layer.setRenderer(QgsMultiBandColorRenderer(layer.dataProvider(), *channels))
        layer.setDefaultContrastEnhancement()
    message, ok = layer.saveNamedStyle(style_path)
    if not ok:
        raise QgsProcessingException("Falha ao salvar o estilo: " + message)
    return style_path


class _LoadStyle(QgsProcessingLayerPostProcessorInterface):
    """QGIS chama esta etapa ao carregar a camada, na thread principal."""
    def __init__(self, style):
        super().__init__()
        self.style = style

    def postProcessLayer(self, layer, context, feedback):
        message, ok = layer.loadNamedStyle(self.style)
        if not ok:
            feedback.pushWarning("Estilo não carregado: " + message)
        layer.triggerRepaint()


class Cbers4aWpmQgis4(QgsProcessingAlgorithm):
    INPUT_FOLDER, OUTPUT_FOLDER = "INPUT_FOLDER", "OUTPUT_FOLDER"
    RECURSIVE, RED, GREEN, BLUE = "RECURSIVE", "RED", "GREEN", "BLUE"
    RESAMPLING, LOAD_RESULTS, OVERVIEWS = "RESAMPLING", "LOAD_RESULTS", "OVERVIEWS"
    STACKS, RGB_RESULTS, PAN_RESULTS = "STACKS", "RGB_RESULTS", "PAN_RESULTS"
    SUCCESS_COUNT, REPORT = "SUCCESS_COUNT", "REPORT"

    def tr(self, text):
        return QCoreApplication.translate("Cbers4aWpmQgis4", text)

    def name(self):
        return "cbers4a_wpm_qgis4"

    def displayName(self):
        return self.tr("CBERSFuse - RGB + PAN (QGIS 4)")

    def group(self):
        return "CBERS-4A"

    def groupId(self):
        return "cbers4a"

    def createInstance(self):
        return Cbers4aWpmQgis4()

    def shortHelpString(self):
        return __doc__

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.INPUT_FOLDER, self.tr("Pasta das bandas CBERS-4A/WPM"),
            behavior=Qgis.ProcessingFileParameterBehavior.Folder))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_FOLDER, self.tr("Pasta de saída (selecione uma pasta persistente)")))
        self.addParameter(QgsProcessingParameterBoolean(
            self.RECURSIVE, self.tr("Procurar em subpastas"), defaultValue=True))
        options = [f"B{n} - {BAND_NAMES[n]}" for n in range(1, 5)]
        for name, title, default in [(self.RED, "Canal vermelho (R)", 2),
                                     (self.GREEN, "Canal verde (G)", 1),
                                     (self.BLUE, "Canal azul (B)", 0)]:
            self.addParameter(QgsProcessingParameterEnum(name, self.tr(title),
                                                         options=options, defaultValue=default))
        self.addParameter(QgsProcessingParameterEnum(
            self.RESAMPLING, self.tr("Reamostragem na fusão"),
            options=["Vizinho mais próximo", "Bilinear", "Cúbica", "Cubic spline", "Lanczos", "Média"],
            defaultValue=2))
        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_RESULTS, self.tr("Carregar somente a imagem fusionada RGB + PAN no projeto"), defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERVIEWS, self.tr("Criar pirâmides de visualização (mais tempo e espaço)"), defaultValue=False))
        for name, title in [(self.STACKS, "Empilhamentos 8 m"),
                             (self.RGB_RESULTS, "Composições RGB 8 m"),
                             (self.PAN_RESULTS, "Composições fusionadas 2 m")]:
            self.addOutput(QgsProcessingOutputMultipleLayers(name, self.tr(title)))
        self.addOutput(QgsProcessingOutputNumber(self.SUCCESS_COUNT, self.tr("Cenas concluídas")))
        self.addOutput(QgsProcessingOutputFile(self.REPORT, self.tr("Registro JSON da execução")))

    def processAlgorithm(self, parameters, context, feedback):
        input_folder = os.path.abspath(self.parameterAsFile(parameters, self.INPUT_FOLDER, context))
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not output_folder or output_folder == QgsProcessing.TEMPORARY_OUTPUT:
            output_folder = os.path.join(QgsProcessingUtils.tempFolder(), "cbers4a_" + uuid.uuid4().hex)
            feedback.pushWarning("Saída temporária: copie os produtos para uma pasta persistente.")
        output_folder = os.path.abspath(output_folder)
        if not os.path.isdir(input_folder):
            raise QgsProcessingException("A pasta de entrada não existe.")
        order = [self.parameterAsEnum(parameters, name, context) + 1
                 for name in (self.RED, self.GREEN, self.BLUE)]
        if len(set(order)) != 3:
            raise QgsProcessingException("Escolha três bandas distintas para os canais R/G/B.")
        resampling = self.parameterAsEnum(parameters, self.RESAMPLING, context)
        pan_algorithm = QgsApplication.processingRegistry().algorithmById("gdal:pansharp")
        if pan_algorithm is None:
            raise QgsProcessingException("Algoritmo gdal:pansharp indisponível. Ative o provedor GDAL.")
        rearrange_algorithm = QgsApplication.processingRegistry().algorithmById("gdal:rearrange_bands")
        if rearrange_algorithm is None:
            raise QgsProcessingException("Algoritmo gdal:rearrange_bands indisponível. Ative o provedor GDAL.")
        rearrange_parameters = {p.name() for p in rearrange_algorithm.parameterDefinitions()}
        rearrange_creation_key = "CREATION_OPTIONS" if "CREATION_OPTIONS" in rearrange_parameters else "OPTIONS"
        pan_parameters = {p.name() for p in pan_algorithm.parameterDefinitions()}
        creation_key = "CREATION_OPTIONS" if "CREATION_OPTIONS" in pan_parameters else "OPTIONS"
        if creation_key not in pan_parameters or "EXTRA" not in pan_parameters:
            raise QgsProcessingException("A interface gdal:pansharp desta instalação não é compatível.")
        scenes = find_scenes(input_folder, self.parameterAsBoolean(parameters, self.RECURSIVE, context))
        if not scenes:
            raise QgsProcessingException("Nenhum arquivo CBERS_4A_WPM_*_BAND0–4.tif encontrado.")
        os.makedirs(output_folder, exist_ok=True)
        load_results = self.parameterAsBoolean(parameters, self.LOAD_RESULTS, context)
        overviews = self.parameterAsBoolean(parameters, self.OVERVIEWS, context)
        if load_results and context.project() is None:
            feedback.pushWarning("Sem projeto de destino: produtos e estilos serão salvos, sem carregamento.")
        report = {"routine_version": VERSION, "qgis_version": Qgis.QGIS_VERSION,
                  "gdal_version": gdal.VersionInfo("RELEASE_NAME"),
                  "started_utc": datetime.now(timezone.utc).isoformat(),
                  "input_folder": input_folder, "output_folder": output_folder,
                  "rgb_source_bands": order, "resampling": RESAMPLING_NAMES[resampling],
                  "method": "Weighted Brovey; quatro MS, pesos iguais padrão GDAL",
                  "fusion_pipeline": "pansharp 4 bandas -> rearrange_bands RGB (como no primeiro script)",
                  "appearance": "qgis_default",
                  "overviews": overviews, "scenes": []}
        outputs = {self.OUTPUT_FOLDER: output_folder, self.STACKS: [], self.RGB_RESULTS: [],
                   self.PAN_RESULTS: [], self.SUCCESS_COUNT: 0}
        self._post_processors = []
        total = len(scenes)
        for index, ((root, scene), candidates) in enumerate(sorted(scenes.items()), 1):
            if feedback.isCanceled():
                break
            record = {"scene": scene, "folder": root, "status": "pending", "warnings": []}
            report["scenes"].append(record)
            feedback.pushInfo(f"[{index}/{total}] {scene}")
            try:
                missing = [n for n in range(5) if n not in candidates]
                duplicate = [n for n, paths in candidates.items() if len(paths) != 1]
                if missing or duplicate:
                    raise QgsProcessingException(f"Bandas ausentes: {missing}; bandas duplicadas: {duplicate}.")
                bands = {n: candidates[n][0] for n in range(5)}
                record["inputs"] = bands
                if not scene.endswith("_L4"):
                    warning = "Produto diferente de L4: confira ortorretificação e corregistro antes do uso."
                    record["warnings"].append(warning)
                    feedback.pushWarning(warning)
                validate_scene(bands)
                destination = os.path.join(output_folder, os.path.relpath(root, input_folder))
                os.makedirs(destination, exist_ok=True)
                rgb_order = "".join(map(str, order))
                filenames = [f"{scene}_STACK_B1_B2_B3_B4_8m.tif",
                             f"{scene}_RGB_{rgb_order}_8m.tif",
                             f"{scene}_RGB_{rgb_order}_PAN_2m.tif"]
                finals = [os.path.join(destination, name) for name in filenames]
                conflicts = [path for final in finals for path in
                             (final, os.path.splitext(final)[0] + ".qml", final + ".aux.xml", final + ".ovr")
                             if os.path.exists(path)]
                if conflicts:
                    raise QgsProcessingException("Saída já existente. Escolha outra pasta: " + conflicts[0])
                # Temporários no mesmo volume: não publica GeoTIFFs incompletos.
                with tempfile.TemporaryDirectory(prefix=".cbers4a_", dir=destination) as stage:
                    staged = [os.path.join(stage, name) for name in filenames]
                    vrt_path = os.path.join(stage, "stack.vrt")
                    vrt = gdal.BuildVRT(vrt_path, [bands[n] for n in range(1, 5)],
                                        options=gdal.BuildVRTOptions(separate=True, bandList=[1]))
                    if vrt is None or vrt.RasterCount != 4:
                        raise QgsProcessingException("Não foi possível empilhar as quatro bandas MS.")
                    vrt = None
                    _check_cancel(feedback)
                    ds = gdal.Translate(staged[0], vrt_path, options=gdal.TranslateOptions(
                        format="GTiff", creationOptions=CREATION_OPTIONS,
                        callback=_callback(feedback)))
                    if ds is None:
                        raise QgsProcessingException("Falha na gravação do empilhamento.")
                    ds = None
                    label_output(staged[0], [1, 2, 3, 4])
                    _check_cancel(feedback)
                    ds = gdal.Translate(staged[1], staged[0], options=gdal.TranslateOptions(
                        format="GTiff", bandList=order, creationOptions=CREATION_OPTIONS,
                        callback=_callback(feedback)))
                    if ds is None:
                        raise QgsProcessingException("Falha na gravação da composição RGB.")
                    ds = None
                    label_output(staged[1], order, rgb=True)
                    _check_cancel(feedback)
                    # Mesma sequência do primeiro script: fusão 4b e depois seleção RGB.
                    extra = "-threads ALL_CPUS -spat_adjust intersection"
                    pan_four_bands = os.path.join(stage, "pansharp_4b.tif")
                    # Contexto separado para liberar os rasters antes de renomeá-los.
                    # Isso também evita bloqueios de arquivo no Windows.
                    child_context = QgsProcessingContext()
                    child_context.setTransformContext(context.transformContext())
                    child_context.setFeedback(feedback)
                    try:
                        processing.run("gdal:pansharp", {
                            "SPECTRAL": staged[0], "PANCHROMATIC": bands[0],
                            "RESAMPLING": resampling, creation_key: "|".join(CREATION_OPTIONS),
                            "EXTRA": extra, "OUTPUT": pan_four_bands}, context=child_context,
                            feedback=feedback, is_child_algorithm=True)
                        _check_cancel(feedback)
                        processing.run("gdal:rearrange_bands", {
                            "INPUT": pan_four_bands, "BANDS": order,
                            rearrange_creation_key: "|".join(CREATION_OPTIONS),
                            "DATA_TYPE": 0, "OUTPUT": staged[2]}, context=child_context,
                            feedback=feedback, is_child_algorithm=True)
                    finally:
                        child_context.temporaryLayerStore().removeAllMapLayers()
                    _check_cancel(feedback)
                    label_output(staged[2], order, rgb=True)
                    for product, channels in zip(staged, [order, [1, 2, 3], [1, 2, 3]]):
                        _check_cancel(feedback)
                        if overviews:
                            ds = _open(product, update=True)
                            try:
                                levels = [n for n in (2, 4, 8, 16)
                                          if min(ds.RasterXSize, ds.RasterYSize) // n >= 1]
                                if levels and ds.BuildOverviews("AVERAGE", levels,
                                                               callback=_callback(feedback)) != 0:
                                    raise QgsProcessingException("Falha na criação de pirâmides.")
                            finally:
                                ds = None
                        save_style(product, channels, feedback)
                    _check_cancel(feedback)
                    published = []
                    try:
                        for product, final in zip(staged, finals):
                            for src, dst in [(product, final),
                                             (os.path.splitext(product)[0] + ".qml",
                                              os.path.splitext(final)[0] + ".qml"),
                                             (product + ".aux.xml", final + ".aux.xml"),
                                             (product + ".ovr", final + ".ovr")]:
                                if os.path.exists(src):
                                    if os.path.exists(dst):
                                        raise QgsProcessingException("Saída criada durante a execução: " + dst)
                                    os.rename(src, dst)
                                    published.append(dst)
                    except Exception:
                        for path in reversed(published):
                            os.remove(path)
                        raise
                record["status"] = "success"
                record["outputs"] = finals
                outputs[self.SUCCESS_COUNT] += 1
                for key, final, title, sort_key in zip(
                        [self.STACKS, self.RGB_RESULTS, self.PAN_RESULTS], finals,
                        ["MS B1/B2/B3/B4 — 8 m", f"RGB {rgb_order} — 8 m", f"RGB {rgb_order} + PAN — 2 m"],
                        [0, 1, 2]):
                    outputs[key].append(final)
                    if key == self.PAN_RESULTS and load_results and context.project() is not None:
                        details = QgsProcessingContext.LayerDetails(f"{scene} | {title}", context.project(), key)
                        details.forceName = True
                        relative = os.path.relpath(root, input_folder)
                        details.groupName = "CBERS-4A | " + scene + (" | " + relative if relative != "." else "")
                        details.layerSortKey = sort_key
                        processor = _LoadStyle(os.path.splitext(final)[0] + ".qml")
                        self._post_processors.append(processor)
                        details.setPostProcessor(processor)
                        context.addLayerToLoadOnCompletion(final, details)
                feedback.pushInfo("Cena concluída: três GeoTIFFs e respectivos estilos.")
            except Exception as error:
                if feedback.isCanceled():
                    record["status"] = "cancelled"
                    record["error"] = str(error)
                    break
                # Se a etapa de carregamento falhar, os arquivos já concluídos permanecem.
                record["status"] = "success_load_warning" if "outputs" in record else "failed"
                record["error"] = str(error)
                feedback.pushWarning(f"{scene}: {error}")
            feedback.setProgress(100.0 * index / total)
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["cancelled"] = feedback.isCanceled()
        report["success_count"] = outputs[self.SUCCESS_COUNT]
        report["unprocessed_count"] = total - len(report["scenes"])
        report_path = os.path.join(output_folder, "cbers4a_execucao_" + uuid.uuid4().hex + ".json")
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        outputs[self.REPORT] = report_path
        feedback.pushInfo(f"Cenas concluídas: {outputs[self.SUCCESS_COUNT]}/{total}. Registro: {report_path}")
        if outputs[self.SUCCESS_COUNT] == 0 and not feedback.isCanceled():
            raise QgsProcessingException("Nenhuma cena concluída. Consulte os avisos e " + report_path)
        return outputs