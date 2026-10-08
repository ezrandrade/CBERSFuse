# CBERSFuse — plugin para QGIS

Versão do plugin: **1.0.1**. Rotina incorporada: **2.2.0**.
Destinado ao QGIS **4.0.x / Qt6**, incluindo o QGIS 4.0.3.

**Desenvolvedor:** Esdras Andrade, do Instituto de Geografia, Desenvolvimento e Meio Ambiente da UFAL.

## Instalação

1. No QGIS, abra **Complementos → Gerenciar e Instalar Complementos**.
2. Escolha **Instalar a partir de ZIP**.
3. Selecione `CBERSFuse_QGIS4_v1.0.1.zip`, sem descompactar.
4. Clique em **Instalar Complemento** e ative **CBERSFuse**.

O acesso aparece em **Raster → CBERSFuse → Composição RGB + fusão PAN**,
no botão da barra de ferramentas e na Caixa de Ferramentas de Processamento.

A instalação é feita dentro do QGIS, inclusive quando instalado por Flatpak.
Nesse caso, escolha pastas às quais o aplicativo tenha acesso. Não instale
dependências no Python do sistema: a rotina usa as bibliotecas do QGIS.

O script independente pode ser mantido; ele aparece no provedor Scripts,
enquanto o plugin usa seu próprio provedor. Para evitar duas ferramentas
visíveis, você pode retirar o script anterior da pasta de scripts do Processing.

## Uso

Selecione a pasta com as cinco bandas descompactadas e uma nova pasta de saída.
Os nomes devem seguir o padrão `CBERS_4A_WPM_..._BAND0.tif` a `..._BAND4.tif`.
As bandas de uma cena devem estar na mesma pasta. A busca em subpastas é opcional.

Padrões: **R=B3, G=B2, B=B1**, reamostragem cúbica e carregamento da imagem
fusionada. Para falsa cor: **R=B4, G=B3, B=B2**.

| Produto | Salvo na pasta | Carregado no projeto |
|---|---|---|
| Empilhamento B1/B2/B3/B4 a 8 m | Sim | Não |
| Composição RGB a 8 m | Sim | Não |
| Composição RGB + PAN a 2 m | Sim | Sim, se a opção estiver marcada |

A aparência segue o padrão do QGIS, salvo em arquivos `.qml` junto aos rasters.
Não há camada de referência nem parâmetros de percentis de contraste.
Os GeoTIFFs existentes não são sobrescritos. Um registro JSON descreve a execução.
Pirâmides de visualização são opcionais e aumentam tempo e armazenamento.

## Método e requisitos

WPM: BAND0 pancromática, 2 m; BAND1 azul, BAND2 verde, BAND3 vermelho e BAND4 NIR,
8 m. A rotina usa Weighted Brovey do GDAL, com quatro bandas multiespectrais e
pesos iguais padrão do GDAL; seleciona os canais RGB após a fusão, como na
versão do script cujo resultado foi validado pelo usuário.

As MS devem estar na mesma grade; todas as bandas devem ter o mesmo SRC
projetado em metros, tipo de dados e NoData compatíveis. A ferramenta confere
esses metadados, mas não corrige nem comprova o corregistro. Recomenda-se L4.
Para índices e análises espectrais quantitativas, conserve os dados originais.
O produto de 2 m não fornece informação espacial equivalente a uma aquisição
de 0,5 m.

Dependências do QGIS: PyQGIS, osgeo.gdal/osr, Processing e os algoritmos
`gdal:pansharp` e `gdal:rearrange_bands`. Nenhum pacote Python externo adicional.

## Estrutura do código

| Arquivo | Função |
|---|---|
| `__init__.py` | Entrada `classFactory` do QGIS |
| `metadata.txt` | Identificação e compatibilidade do plugin |
| `plugin.py` | Botão, menu Raster, ajuda e ciclo de ativação |
| `processing_provider/provider.py` | Registro do provedor `cbers4awpm` |
| `processing_provider/algorithm.py` | Rotina de processamento 2.2.0 |
| `help.html` | Ajuda acessível pelo menu |
| `icon.png` e `icon.svg` | Ícone do plugin e fonte vetorial |
| `tests/smoke_qgis.py` | Verificação do registro em uma instalação real |

Identificador do algoritmo: `cbers4awpm:cbers4a_wpm_qgis4`.
O plugin também disponibiliza o algoritmo para execução em lote e modelos.

## Verificação

O pacote foi verificado quanto à sintaxe, estrutura ZIP, metadados, preservação
do algoritmo e ciclo de registro/remoção do provedor e ações em testes simulados.
O QGIS e o GDAL não estavam disponíveis no ambiente de empacotamento; a
instalação e a execução da versão 1.0.0 foram confirmadas pelo usuário no QGIS
local. A atualização 1.0.1 altera somente o nome e os textos de apresentação e ajuda.

Depois de instalar, uma verificação opcional pode ser executada no Console
Python do QGIS com o arquivo `tests/smoke_qgis.py`. Ela confere o registro,
os parâmetros e a presença dos algoritmos GDAL; não processa imagens.

## Manutenção

Para instalar uma atualização, use novamente **Instalar a partir de ZIP** e
reinicie o QGIS se necessário. Ao desativar o plugin, seu botão, menu e provedor
são removidos; os produtos raster salvos continuam disponíveis.

O pacote foi preparado para instalação local. Email e repositório de código
estão em branco nos metadados porque não foram informados; esses campos e
a licença deverão ser definidos antes de uma eventual publicação pública.

Referências oficiais:

- https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/plugins/plugins.html
- https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/processing.html
- https://gdal.org/en/stable/programs/gdal_pansharpen.html
- https://www.gov.br/inpe/pt-br/programas/cbers/sobre-o-cbers-1/cbers-04a/cameras-imageadoras
