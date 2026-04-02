# ============================================================
# Plugin: BiblioMeta — Metadata Source for Calibre
# Version: 1.2.1
# Autor: Ludovico
# Fuentes: BNE · LoC · Wikidata · Open Library · Google Books
# ============================================================
# Changelog v1.2.0:
#   - FIX: alma.local_control_number para identificadores bimoBNE
#          (alma.identifier devuelve 0 — bug crítico en v1.0/v1.1)
#   - FIX: 653 $a — palabras clave libres BNE como tags adicionales
#   - FIX: comments añadido a touched_fields (Calibre lo ofrece en merge)
#   - NEW: Ranking por riqueza de metadatos (_score_metadata)
#          aplicado a resultados de BNE, LoC y Open Library
#   - NEW: Modo "both" paralelo — BNE y LoC en threads simultáneos,
#          gana el resultado con más metadatos
#   - NEW: Wikidata solo cuando el resultado no tiene tags
#   - NEW: maximumRecords dinámico — 1 con ID directo, 3 con título
#   - NEW: Cancelación temprana Google Books si BNE tiene 520 $a
#   - NEW: Abort temprano cuando resultado tiene todos los campos
#   - NEW: Timeout dinámico por servidor (aprende de la sesión)
#   - NEW: Validación ISBN antes de lanzar queries
#   - NEW: Logging reducido — solo warnings/errores en producción,
#          nivel DEBUG activable desde configuración
# ============================================================

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from queue import Queue, Empty
from threading import Event, Thread

from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.config import JSONConfig

try:
    from lxml import etree
except ImportError:
    import xml.etree.ElementTree as etree


NS = {
    "srw":  "http://www.loc.gov/zing/srw/",
    "marc": "http://www.loc.gov/MARC21/slim",
}

BNE_SRU_BASE       = "https://catalogo.bne.es/view/sru/34BNE_INST"
LOC_SRU_BASE       = "https://lx2.loc.gov/sru/lcdb"
WIKIDATA_SPARQL    = "https://query.wikidata.org/sparql"
SRU_VERSION        = "1.2"
GBOOKS_API         = "https://www.googleapis.com/books/v1/volumes"
OPENLIBRARY_API    = "https://openlibrary.org/api/books"
OPENLIBRARY_COVER  = "https://covers.openlibrary.org/b/isbn/%s-L.jpg?default=false"

# Timeouts iniciales — se ajustan dinámicamente durante la sesión
_DEFAULT_TIMEOUT_BNE    = 20
_DEFAULT_TIMEOUT_LOC    = 20
_DEFAULT_TIMEOUT_GBOOKS =  8
_DEFAULT_TIMEOUT_OL     = 10
_DEFAULT_TIMEOUT_WD     = 15

EXCLUDED_RELATORS = {
    "editor","edt","prologuista","prl","ilustrador","ill",
    "traductor","trl","compilador","com","director","drt",
    "coordinador","coo","anotador","adaptador",
    "fotografo","fotógrafo",
}

_NON_SPANISH_STOPWORDS = {
    'het','een','van','naar','aan','dat','zijn','voor','met',
    'niet','ook','maar','bij','wordt','zich','door','hun','hen',
    'die','der','und','das','ist','ein','eine','mit','auf',
    'dem','den','des','sich','nicht','auch','als','werden','wurde',
    'les','des','une','dans','est','qui','que','sur','pas',
    'par','avec','sont','mais','ils','tout','plus','cette','leur',
    'che','non','una','per','con','del','della','nel','sono',
    'come','loro','anche','quello','questo','alle','agli',
    'the','and','that','have','for','not','with','you',
    'this','but','from','they','will','would','there','their',
    'que','não','uma','para','com','por','mas','seu','sua',
    'isso','ele','ela','eles','elas','muito','pelo','pela',
}

# ═══════════════════════════════════════════════════════════════
# TRADUCTOR CDU (español)
# ═══════════════════════════════════════════════════════════════

_CDU_BASE = {
    "001":"Ciencia y conocimiento","002":"Documentación",
    "003":"Sistemas de escritura","004":"Informática",
    "005":"Gestión","006":"Tecnologías especiales",
    "007":"Actividad humana","008":"Civilización y cultura",
    "01":"Bibliografía","02":"Biblioteconomía",
    "030":"Enciclopedias","050":"Publicaciones periódicas",
    "06":"Organizaciones","070":"Periodismo y medios",
    "08":"Colecciones generales","09":"Manuscritos y libros raros",
    "087.4":"Literatura infantil","087.5":"Literatura juvenil",
    "087":"Publicaciones para grupos específicos",
    "088":"Publicaciones de divulgación",
    "101":"Naturaleza de la filosofía","111":"Ontología",
    "113":"Cosmología","12":"Teorías del conocimiento",
    "13":"Filosofía de la mente","14":"Sistemas filosóficos",
    "159.9":"Psicología","16":"Lógica","17":"Ética y moral",
    "1":"Filosofía",
    "21":"Teología natural","22":"Biblia",
    "23":"Teología dogmática","24":"Teología práctica",
    "246":"Devocionario y piedad","25":"Teología pastoral",
    "26":"Iglesia cristiana","27":"Religión cristiana",
    "273":"Herejías y cismas","28":"Islam",
    "29":"Otras religiones","2":"Religión",
    "301":"Sociología","304":"Problemas sociales",
    "304.9":"Problemas morales y sociales",
    "305":"Estudios de género","308":"Estructuras sociales",
    "31":"Estadística social","316":"Sociología",
    "316.3":"Estructura social","316.32":"Sociedad y cultura",
    "316.33":"Estratificación social","316.34":"Grupos sociales",
    "316.4":"Procesos sociales","316.42":"Cambio social",
    "316.43":"Integración social","316.44":"Movilidad social",
    "316.46":"Liderazgo y poder social",
    "316.47":"Relaciones interpersonales",
    "316.472":"Comunicación interpersonal",
    "316.472.4":"Comunicación y cognición social",
    "316.48":"Conflictos sociales","316.485":"Gestión de conflictos",
    "316.6":"Psicología social","316.61":"Socialización",
    "316.62":"Actitudes y valores sociales",
    "316.64":"Opinión pública",
    "316.7":"Sociología de la cultura",
    "316.72":"Sociología cultural e intercultural",
    "316.74":"Sociología de la comunicación",
    "316.75":"Ideología y sociedad",
    "316.77":"Comunicación de masas",
    "32":"Política","321":"Sistemas políticos",
    "323":"Política interior","324":"Elecciones",
    "325":"Migraciones","327":"Relaciones internacionales",
    "328":"Parlamentos","329":"Partidos políticos",
    "33":"Economía","330":"Economía general",
    "330.1":"Teoría económica","330.11":"Sistemas económicos",
    "330.12":"Propiedad y capital","330.13":"Valor y precio",
    "330.14":"Capital humano","330.15":"Economía ecológica",
    "330.16":"Economía del bienestar",
    "330.3":"Dinámica económica","330.34":"Crecimiento económico",
    "330.35":"Desarrollo económico",
    "330.4":"Métodos matemáticos en economía",
    "330.5":"Renta nacional y riqueza",
    "330.52":"Riqueza nacional","330.55":"Renta nacional",
    "330.56":"Nivel de vida","330.567":"Finanzas personales",
    "330.567.2":"Ahorro e inversión personal",
    "332":"Economía financiera",
    "334":"Cooperativas y formas asociativas",
    "336":"Finanzas públicas","338":"Situación económica",
    "338.1":"Coyuntura económica","338.12":"Ciclos económicos",
    "338.124":"Crisis económicas",
    "338.13":"Inflación y deflación",
    "338.14":"Estabilización económica",
    "339":"Comercio exterior",
    "34":"Derecho","341":"Derecho internacional",
    "342":"Derecho constitucional","343":"Derecho penal",
    "346":"Derecho mercantil","347":"Derecho civil",
    "348":"Derecho eclesiástico","349":"Derecho especial",
    "35":"Administración pública","351":"Funciones del Estado",
    "355":"Ciencias militares","358":"Fuerzas aéreas",
    "359":"Fuerzas navales","36":"Trabajo social y asistencia",
    "37":"Educación","371":"Organización escolar",
    "372":"Educación primaria","373":"Educación secundaria",
    "374":"Educación de adultos","376":"Educación especial",
    "377":"Formación profesional","378":"Educación superior",
    "38":"Comercio y comunicaciones","39":"Etnología y costumbres",
    "391":"Indumentaria y costumbres",
    "392":"Usos y costumbres sociales",
    "394":"Fiestas y ceremonias","396":"Feminismo",
    "398":"Folklore y tradición oral","3":"Ciencias sociales",
    "40":"Lingüística general","401":"Filosofía del lenguaje",
    "410":"Lingüística","411":"Escritura y ortografía",
    "412":"Etimología","413":"Diccionarios y lexicografía",
    "414":"Fonética y fonología","415":"Gramática",
    "416":"Dialectología","417":"Lenguas especiales",
    "418":"Aplicaciones lingüísticas","42":"Lengua inglesa",
    "43":"Lengua alemana","44":"Lengua francesa",
    "45":"Lengua italiana","46":"Lengua española",
    "461":"Español / Castellano","462":"Portugués",
    "463":"Catalán","464":"Gallego","465":"Vasco / Euskera",
    "466":"Aragonés","467":"Asturiano / Bable",
    "47":"Lengua rusa","48":"Lenguas clásicas",
    "481":"Griego clásico","482":"Latín",
    "49":"Otras lenguas","491":"Lenguas eslavas",
    "492":"Árabe","493":"Hebreo",
    "496":"Lenguas ibéricas no romances","4":"Lingüística y lenguas",
    "51":"Matemáticas","511":"Aritmética","512":"Álgebra",
    "512.1":"Álgebra general","512.2":"Teoría de grupos",
    "512.3":"Teoría de anillos","512.4":"Álgebra abstracta",
    "512.5":"Álgebra lineal y vectorial",
    "512.54":"Teoría de grupos y anillos",
    "512.6":"Álgebra lineal","512.62":"Matrices y determinantes",
    "512.64":"Álgebra lineal","512.7":"Teoría de números",
    "512.8":"Geometría algebraica","512.9":"Álgebra universal",
    "513":"Geometría analítica","514":"Geometría",
    "515":"Análisis matemático","516":"Geometría diferencial",
    "517":"Cálculo","519":"Probabilidad y estadística",
    "52":"Astronomía","521":"Mecánica celeste",
    "523":"Sistema solar","524":"Estrellas y galaxias",
    "525":"Tierra","527":"Navegación astronómica",
    "53":"Física","531":"Mecánica","532":"Mecánica de fluidos",
    "533":"Mecánica de gases","534":"Acústica","535":"Óptica",
    "536":"Calor y termodinámica",
    "537":"Electricidad y magnetismo",
    "538":"Física del estado sólido","539":"Física nuclear",
    "54":"Química","541":"Química física",
    "542":"Química práctica","543":"Química analítica",
    "546":"Química inorgánica","547":"Química orgánica",
    "548":"Cristalografía","549":"Mineralogía",
    "55":"Geología y ciencias de la tierra",
    "551":"Meteorología y climatología","552":"Petrología",
    "553":"Depósitos minerales","556":"Hidrología",
    "56":"Paleontología","57":"Biología",
    "570":"Biología general","572":"Antropología física",
    "574":"Ecología","575":"Genética y evolución",
    "576":"Biología celular y molecular","577":"Bioquímica",
    "578":"Virología","579":"Microbiología",
    "58":"Botánica","581":"Botánica general",
    "582":"Plantas vasculares","583":"Plantas con flores",
    "59":"Zoología","591":"Zoología general y etología",
    "592":"Invertebrados","594":"Moluscos",
    "595":"Artrópodos","596":"Vertebrados",
    "597":"Peces y anfibios","598":"Reptiles y aves",
    "599":"Mamíferos","5":"Ciencias naturales",
    "61":"Medicina y salud","611":"Anatomía","612":"Fisiología",
    "613":"Salud e higiene personal","614":"Salud pública",
    "615":"Farmacología y terapéutica",
    "616":"Patología",
    "616.1":"Enfermedades cardiovasculares",
    "616.2":"Enfermedades respiratorias",
    "616.3":"Enfermedades digestivas",
    "616.4":"Enfermedades endocrinas",
    "616.5":"Enfermedades de la piel",
    "616.6":"Enfermedades urológicas",
    "616.7":"Enfermedades del aparato locomotor",
    "616.8":"Neurología",
    "616.83":"Enfermedades cerebrovasculares",
    "616.85":"Trastornos neurológicos",
    "616.89":"Psiquiatría","616.891":"Psicoterapia",
    "616.892":"Psicosis","616.893":"Neurosis",
    "616.894":"Demencias y Alzheimer",
    "616.895":"Esquizofrenia",
    "616.896":"Trastornos del humor",
    "616.9":"Enfermedades infecciosas",
    "617":"Cirugía","618":"Ginecología y obstetricia",
    "619":"Medicina veterinaria","62":"Ingeniería",
    "620":"Ingeniería general","621":"Ingeniería mecánica",
    "622":"Minería","623":"Ingeniería militar",
    "624":"Ingeniería civil","625":"Ingeniería de transporte",
    "627":"Obras hidráulicas","628":"Ingeniería sanitaria",
    "629":"Ingeniería del transporte y espacial",
    "63":"Agricultura y ganadería","630":"Silvicultura",
    "631":"Técnicas agrícolas","632":"Plagas y enfermedades",
    "633":"Cultivos agrícolas",
    "634":"Fruticultura y horticultura",
    "635":"Jardinería y horticultura","636":"Ganadería",
    "637":"Productos animales","638":"Apicultura",
    "639":"Pesca, caza y acuicultura","64":"Economía doméstica",
    "641":"Gastronomía y cocina",
    "643":"Vivienda y decoración",
    "645":"Decoración de interiores","646":"Confección y moda",
    "65":"Comunicación y gestión empresarial",
    "654":"Telecomunicaciones",
    "655":"Artes gráficas e industria editorial",
    "656":"Transporte y tráfico","657":"Contabilidad",
    "658":"Administración y gestión de empresas",
    "659":"Publicidad y relaciones públicas",
    "66":"Química industrial","663":"Bebidas y fermentación",
    "664":"Industria alimentaria","674":"Industria maderera",
    "676":"Industria del papel","677":"Industria textil",
    "67":"Industrias de materiales",
    "68":"Industrias especializadas",
    "681":"Instrumentos de precisión","684":"Carpintería",
    "686":"Encuadernación","69":"Construcción",
    "691":"Materiales de construcción","697":"Climatización",
    "6":"Tecnología y ciencias aplicadas",
    "71":"Urbanismo y ordenación del territorio",
    "712":"Paisajismo y jardines","72":"Arquitectura",
    "721":"Elementos arquitectónicos","725":"Arquitectura civil",
    "726":"Arquitectura religiosa",
    "728":"Arquitectura residencial",
    "73":"Artes plásticas y escultura",
    "730":"Escultura general","736":"Grabado y talla",
    "737":"Numismática","738":"Cerámica",
    "739":"Orfebrería y joyería",
    "74":"Diseño y artes decorativas","741":"Dibujo",
    "741.5":"Cómic e historietas","741.52":"Cómic e historietas",
    "742":"Perspectiva y geometría descriptiva",
    "745":"Artes decorativas y aplicadas",
    "746":"Bordado y tejido artístico",
    "747":"Interiorismo y decoración",
    "748":"Vidriería artística","749":"Muebles y ornamentación",
    "75":"Pintura","750":"Pintura general",
    "751":"Técnicas pictóricas","757":"Retrato",
    "758":"Paisaje","759":"Historia de la pintura",
    "76":"Grabado y artes gráficas","77":"Fotografía",
    "778":"Cine y técnicas audiovisuales","78":"Música",
    "780":"Musicología","781":"Teoría musical",
    "782":"Ópera","783":"Música sacra","784":"Música vocal",
    "785":"Música de cámara e instrumental",
    "786":"Piano y teclado","787":"Instrumentos de cuerda",
    "788":"Instrumentos de viento",
    "79":"Espectáculo, deporte y juego",
    "791":"Espectáculos públicos",
    "792":"Teatro y artes escénicas",
    "793":"Juegos de salón","794":"Ajedrez",
    "796":"Deportes y educación física",
    "797":"Deportes acuáticos y aéreos",
    "798":"Deportes ecuestres","799":"Pesca deportiva y caza",
    "7":"Artes y recreación",
    "800":"Literatura general","801":"Teoría y crítica literaria",
    "821.111":"Literatura inglesa","821.112.2":"Literatura alemana",
    "821.113.5":"Literatura sueca","821.113.6":"Literatura danesa",
    "821.124":"Literatura latina",
    "821.131.1":"Literatura italiana",
    "821.133.1":"Literatura francesa",
    "821.134.1":"Literatura española (todas variedades)",
    "821.134.2":"Literatura española",
    "821.134.3":"Literatura portuguesa",
    "821.14":"Literatura griega clásica",
    "821.161.1":"Literatura rusa",
    "821.163.2":"Literatura búlgara",
    "821.163.4":"Literatura checa",
    "821.411.21":"Literatura árabe",
    "821.512.161":"Literatura turca",
    "821.521":"Literatura china",
    "821.521.1":"Literatura japonesa",
    "821":"Literatura",
    "830":"Literatura alemana","840":"Literatura francesa",
    "850":"Literatura italiana","860":"Literatura española",
    "861":"Literatura catalana","862":"Literatura vasca",
    "863":"Literatura gallega","864":"Literatura occitana",
    "869.0":"Literatura brasileña","869":"Literatura portuguesa",
    "871":"Literatura griega clásica",
    "872":"Literatura latina clásica",
    "88":"Literatura eslava","882":"Literatura rusa",
    "89":"Otras literaturas","892":"Literatura árabe",
    "8":"Literatura y lengua",
    "902":"Arqueología","903":"Prehistoria y arqueología",
    "904":"Restos arqueológicos históricos",
    "908":"Historia y geografía regional",
    "91":"Geografía","910":"Geografía general y viajes",
    "911":"Geografía física y humana",
    "912":"Representaciones cartográficas",
    "913":"Geografía regional","914":"Geografía de Europa",
    "915":"Geografía de Asia","916":"Geografía de África",
    "917":"Geografía de América del Norte",
    "918":"Geografía de América del Sur",
    "919":"Geografía de otras regiones",
    "929":"Biografías y genealogías",
    "930":"Historiografía y ciencias históricas",
    "940":"Historia de Europa general",
    "941":"Historia de Islas Británicas",
    "943":"Historia de Alemania","944":"Historia de Francia",
    "945":"Historia de Italia","946":"Historia de España",
    "947":"Historia de Rusia","948":"Historia de Escandinavia",
    "949":"Historia de otros países europeos",
    "94":"Historia de Europa",
    "95":"Historia de Asia","96":"Historia de África",
    "97":"Historia de América del Norte",
    "980":"Historia de América del Sur",
    "981":"Historia de Brasil","982":"Historia de Argentina",
    "983":"Historia de Chile","984":"Historia de Bolivia",
    "985":"Historia de Perú","986":"Historia de Colombia",
    "987":"Historia de Venezuela",
    "98":"Historia de América del Sur",
    "99":"Historia de otras regiones",
    "93":"Historia","9":"Historia y Geografía",
}

_CDU_LANG = {
    "111":"inglesa","112.2":"alemana","112.5":"neerlandesa",
    "113.5":"sueca","113.6":"danesa","113.61":"noruega",
    "114":"letona","124":"latina","131.1":"italiana",
    "133.1":"francesa","134.1":"española (todas variedades)",
    "134.2":"española","134.3":"portuguesa",
    "134.31":"gallega","134.32":"catalana","134.33":"vasca",
    "14":"griega clásica","152":"rumana",
    "161.1":"rusa","161.2":"ucraniana",
    "163.2":"búlgara","163.4":"checa","163.42":"eslovaca",
    "163.6":"eslovena","411.21":"árabe","411.16":"hebrea",
    "512.161":"turca","512.165":"azerbaiyana",
    "521":"china","521.1":"japonesa","522":"coreana",
}

_CDU_FORM = {
    "-1":"Poesía","-11":"Poesía épica","-12":"Poesía lírica",
    "-13":"Poesía dramática","-14":"Poesía didáctica",
    "-2":"Teatro","-21":"Tragedia","-22":"Comedia",
    "-23":"Drama","-3":"Narrativa","-31":"Novela",
    "-311":"Novela de aventuras","-312":"Novela policiaca",
    "-312.4":"Novela negra","-313":"Ciencia ficción",
    "-314":"Fantasía","-32":"Cuentos y relatos",
    "-321":"Cuentos","-322":"Relatos cortos",
    "-34":"Humor y sátira","-4":"Ensayo",
    "-5":"Discursos y oratoria","-6":"Epistolario y cartas",
    "-7":"Sátira y humor","-8":"Traducción",
    "-9":"Miscelánea","-91":"Diarios",
    "-92":"Autobiografía","-93":"Memorias",
    "-94":"Literatura de viajes",
}

_CDU_COUNTRY = {
    "(100)":"Mundial","(4)":"Europa",
    "(410)":"Reino Unido","(420)":"Inglaterra",
    "(430)":"Alemania","(436)":"Austria",
    "(44)":"Francia","(450)":"Italia",
    "(460)":"España",
    "(460.11)":"Galicia","(460.12)":"Asturias",
    "(460.13)":"Cantabria","(460.14)":"País Vasco",
    "(460.15)":"Navarra","(460.16)":"La Rioja",
    "(460.17)":"Aragón","(460.18)":"Cataluña",
    "(460.19)":"Baleares","(460.21)":"Castilla y León",
    "(460.22)":"Madrid","(460.23)":"Castilla-La Mancha",
    "(460.24)":"Extremadura","(460.25)":"Valencia",
    "(460.26)":"Murcia","(460.27)":"Andalucía",
    "(460.28)":"Canarias",
    "(460.353)":"Sevilla",
    "(460.354)":"Huelva","(460.355)":"Cádiz",
    "(460.356)":"Málaga","(460.357)":"Córdoba",
    "(460.358)":"Jaén","(460.359)":"Granada",
    "(460.360)":"Almería",
    "(460.35)":"País Vasco",
    "(460.351)":"Álava","(460.352)":"Guipúzcoa",
    "(460.361)":"Vizcaya","(460.36)":"Navarra",
    "(460.181)":"Barcelona","(460.182)":"Girona",
    "(460.183)":"Lleida","(460.184)":"Tarragona",
    "(460.111)":"A Coruña","(460.112)":"Lugo",
    "(460.113)":"Ourense","(460.114)":"Pontevedra",
    "(469)":"Portugal","(47)":"Rusia","(48)":"Escandinavia",
    "(492)":"Países Bajos","(493)":"Bélgica","(494)":"Suiza",
    "(32)":"Egipto","(33)":"Libia","(35)":"Argelia",
    "(36)":"Marruecos","(37)":"Sudán","(38)":"Etiopía",
    "(42)":"Siria","(43)":"Líbano","(442)":"Palestina",
    "(44)":"Iraq","(45)":"Irán","(46)":"Arabia Saudí",
    "(48)":"Israel","(53)":"Arabia","(54)":"India",
    "(55)":"Pakistán",
    "(5)":"Asia","(51)":"China","(52)":"Japón",
    "(520)":"Japón","(569)":"Oriente Medio",
    "(6)":"África","(61)":"Túnez","(62)":"Egipto",
    "(64)":"Marruecos","(65)":"Argelia",
    "(7)":"América del Norte","(71)":"Canadá",
    "(72)":"México","(73)":"Estados Unidos",
    "(7/8)":"América","(8)":"América Latina",
    "(81)":"Brasil","(82)":"Argentina","(83)":"Chile",
    "(84)":"Perú","(85)":"Bolivia","(86)":"Colombia",
    "(87)":"Venezuela","(9)":"Australia y Pacífico",
}

_CDU_ETHNIC = {
    "(=411.16)":"Judíos","(=411.21)":"Árabes",
    "(=411)":"Pueblos semíticos","(=413)":"Pueblo armenio",
    "(=414)":"Pueblo kurdo","(=415)":"Pueblo persa",
    "(=134)":"Hispanohablantes","(=161)":"Pueblos eslavos",
    "(=112)":"Pueblos germánicos","(=111)":"Pueblos celtas",
    "(=521.1)":"Pueblo japonés","(=521)":"Pueblo chino",
    "(=522)":"Pueblo coreano","(=54)":"Pueblos indios",
    "(=6)":"Pueblos africanos","(=91)":"Pueblo gitano / Roma",
    "(=916)":"Pueblo gitano / Roma",
}

_CDU_CENTURY = {
    '"03"':"s.IV",   '"04"':"s.V",    '"05"':"s.VI",
    '"06"':"s.VII",  '"07"':"s.VIII", '"08"':"s.IX",
    '"09"':"s.X",    '"10"':"s.XI",   '"11"':"s.XII",
    '"12"':"s.XIII", '"13"':"s.XIV",  '"14"':"s.XV",
    '"15"':"s.XVI",  '"16"':"s.XVII", '"17"':"s.XVIII",
    '"18"':"s.XIX",  '"19"':"s.XX",   '"20"':"s.XXI",
}

_CDU_SPECIAL = {
    "(031)":"Enciclopedias generales",
    "(032)":"Enciclopedias especializadas",
    "(033)":"Anuarios y almanaques",
    "(035)":"Enciclopedias y diccionarios especializados",
    "(036)":"Guías y manuales","(038)":"Diccionarios",
    "(03)":"Obras de referencia","(04)":"Ensayos y artículos",
    "(05)":"Publicaciones en serie","(06)":"Actas y congresos",
    "(07)":"Material didáctico","(08)":"Obras completas",
    "(09)":"Historia y biografía",
    "(083.1)":"Normas","(083.2)":"Especificaciones técnicas",
    "(083.4)":"Patentes","(083.7)":"Marcas comerciales",
    "(083.8)":"Catálogos comerciales",
    "(083.824)":"Catálogos de exposición",
    "(084)":"Material gráfico","(084.1)":"Mapas",
    "(084.3)":"Planos","(086)":"Documentos audiovisuales",
    "(086.8)":"Vídeo",
}

_HISTORY_BASES = {"93","94","95","96","97","98","99"}


def _clean_cdu_code(code):
    raw = code.strip()
    raw = re.sub(r'\((\d[\d.]*)\s+[A-Za-záéíóúñÁÉÍÓÚÑ][^)]*\)', r'(\1)', raw)
    open_p  = raw.count("(")
    close_p = raw.count(")")
    if open_p > close_p:
        raw = raw + ")" * (open_p - close_p)
    m = re.match(r'^([\d.\-"()/+:=]+(?:\([^)]*\))*[\d.\-"]*)', raw)
    return m.group(1).strip() if m else raw


def _extract_bio_subject(code):
    m = re.match(r'^[\d.\-"()/+:\s=]+\s+(.+)$', code.strip())
    if m:
        subject = m.group(1).strip()
        if len(subject) > 2 and not subject[0].isdigit():
            return subject
    return None


def _extract_geo_locality(code):
    m = re.search(
        r'\(\d[\d.]*\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}[a-záéíóúñA-ZÁÉÍÓÚÑ\s]*)',
        code
    )
    if m:
        loc = m.group(1).strip().rstrip(')').strip()
        if len(loc) >= 3:
            return loc
    return None


def _is_spanish(text):
    words = re.findall(r'\b[a-záéíóúüñ]+\b', text.lower())
    if len(words) < 5:
        return True
    foreign = sum(1 for w in words if w in _NON_SPANISH_STOPWORDS)
    return (foreign / len(words)) < 0.12


def _translate_cdu(code):
    raw  = code.strip()
    tag  = "CDU:" + raw
    work = re.sub(r"\s+", "", raw)
    if ":" in work:
        parts = []
        for p in work.split(":", 1):
            s = _translate_cdu_simple(p.strip())
            if s:
                parts.append(s)
        return [tag, " y ".join(parts)] if parts else [tag]
    if "+" in work:
        s = _translate_cdu_simple(work.split("+")[0])
        return [tag, s + " (y otros)"] if s else [tag]
    if "/" in work:
        dp = 0; dq = 0; slash_out = False
        for ch in work:
            if ch == "(": dp += 1
            elif ch == ")": dp -= 1
            elif ch == '"': dq = 1 - dq
            elif ch == "/" and dp == 0 and dq == 0:
                slash_out = True; break
        if slash_out:
            s = _translate_cdu_simple(work.split("/")[0])
            return [tag, s + " (y relacionados)"] if s else [tag]
    desc = _translate_cdu_simple(work)
    return [tag, desc] if desc else [tag]


def _translate_cdu_simple(work):
    if not work:
        return None
    rest = work
    parts = []
    rest = re.sub(r'\(0[^)]*\)', '', rest)
    base_key = None
    for key in sorted(_CDU_BASE.keys(), key=len, reverse=True):
        if rest.startswith(key):
            base_key = key
            break
    if not base_key:
        if rest and rest[0].isdigit():
            return {
                "0":"Generalidades","1":"Filosofía","2":"Religión",
                "3":"Ciencias sociales","4":"Lingüística",
                "5":"Ciencias naturales","6":"Tecnología",
                "7":"Artes","8":"Literatura","9":"Historia y Geografía",
            }.get(rest[0])
        return None
    parts.append(_CDU_BASE[base_key])
    rest = rest[len(base_key):]
    lit_bases = {
        "821","82","8","820","860","861","862","863",
        "811","830","840","850","869",
    }
    if base_key in lit_bases and rest.startswith("."):
        lang_rest = rest[1:]
        for key in sorted(_CDU_LANG.keys(), key=len, reverse=True):
            if lang_rest.startswith(key):
                lang_label = "Literatura " + _CDU_LANG[key]
                if _CDU_LANG[key] not in parts[0]:
                    parts[0] = lang_label
                rest = lang_rest[len(key):]
                if rest.startswith("'"):
                    end = len(rest)
                    for stop in ["-", "(", '"']:
                        idx = rest.find(stop)
                        if idx != -1 and idx < end:
                            end = idx
                    rest = rest[end:]
                break
    for key in sorted(_CDU_FORM.keys(), key=len, reverse=True):
        if key in rest:
            parts.append(_CDU_FORM[key])
            rest = rest.replace(key, "", 1)
            break
    for key in sorted(_CDU_SPECIAL.keys(), key=len, reverse=True):
        if key in rest:
            parts.append(_CDU_SPECIAL[key])
            rest = rest.replace(key, "", 1)
            break
    for key in sorted(_CDU_ETHNIC.keys(), key=len, reverse=True):
        if key in rest:
            parts.append(_CDU_ETHNIC[key])
            rest = rest.replace(key, "", 1)
            break
    for key in sorted(_CDU_COUNTRY.keys(), key=len, reverse=True):
        if key in rest:
            country = _CDU_COUNTRY[key]
            if base_key in _HISTORY_BASES:
                parts[0] = "Historia de " + country
            else:
                parts.append(country)
            rest = rest.replace(key, "", 1)
            break
    for key, val in _CDU_CENTURY.items():
        if key in rest:
            parts.append(val)
            break
    return " · ".join(p for p in parts if p) or None


# ═══════════════════════════════════════════════════════════════
# TRADUCTOR LCC (inglés)
# ═══════════════════════════════════════════════════════════════

_LCC_BASE = {
    "AC":"General Collections","AE":"Encyclopedias",
    "AG":"Dictionaries and Reference Works",
    "AM":"Museums","AN":"Newspapers","AP":"Periodicals",
    "AY":"Yearbooks and Almanacs",
    "AZ":"History of Scholarship",
    "BC":"Logic","BD":"Speculative Philosophy",
    "BF":"Psychology","BH":"Aesthetics","BJ":"Ethics",
    "BL":"Religion and Mythology","BM":"Judaism",
    "BP":"Islam and Bahai Faith","BQ":"Buddhism",
    "BR":"Christianity","BS":"The Bible",
    "BT":"Doctrinal Theology","BV":"Practical Theology",
    "BX":"Christian Denominations","B":"Philosophy",
    "CB":"History of Civilization","CC":"Archaeology",
    "CS":"Genealogy","CT":"Biography",
    "DA":"History of Great Britain",
    "DB":"History of Austria and Hungary",
    "DC":"History of France","DD":"History of Germany",
    "DE":"History of Mediterranean Region",
    "DF":"History of Greece","DG":"History of Italy",
    "DH":"History of Low Countries",
    "DK":"History of Russia and Soviet Union",
    "DL":"History of Scandinavia",
    "DP":"History of Spain and Portugal",
    "DR":"History of Balkan Peninsula",
    "DS":"History of Asia","DT":"History of Africa",
    "DU":"History of Oceania","D":"World History",
    "E":"History of America",
    "F":"History of United States, Local",
    "GA":"Cartography","GB":"Physical Geography",
    "GC":"Oceanography","GE":"Environmental Sciences",
    "GF":"Human Ecology","GN":"Anthropology",
    "GR":"Folklore","GT":"Manners and Customs",
    "GV":"Recreation and Sports","G":"Geography",
    "HA":"Statistics","HB":"Economic Theory",
    "HC":"Economic History","HD":"Industry and Labor",
    "HE":"Transportation","HF":"Commerce","HG":"Finance",
    "HJ":"Public Finance","HM":"Sociology",
    "HN":"Social History","HQ":"Family, Marriage, Women",
    "HT":"Communities and Classes",
    "HV":"Social Pathology and Criminology",
    "HX":"Socialism and Communism","H":"Social Sciences",
    "JA":"Political Science","JC":"Political Theory",
    "JF":"Political Institutions",
    "JK":"Politics, United States",
    "JN":"Politics, Europe","JQ":"Politics, Asia and Africa",
    "JS":"Local Government","JV":"Colonization",
    "JZ":"International Relations","J":"Political Science",
    "KF":"Law of the United States",
    "KD":"Law of United Kingdom","K":"Law",
    "LA":"History of Education","LB":"Theory of Education",
    "LC":"Special Aspects of Education","L":"Education",
    "ML":"Music Literature","MT":"Music Instruction","M":"Music",
    "NA":"Architecture","NB":"Sculpture",
    "NC":"Drawing and Design","ND":"Painting",
    "NE":"Print Media","NK":"Decorative Arts",
    "NX":"Arts in General","N":"Fine Arts",
    "PA":"Classical Languages and Literature",
    "PB":"Celtic Languages","PC":"Romance Languages",
    "PD":"Germanic Languages","PE":"English Language",
    "PF":"West Germanic Languages",
    "PG":"Slavic Languages and Literatures",
    "PJ":"Oriental Languages and Literatures",
    "PK":"Indo-Iranian Languages and Literatures",
    "PL":"East Asian Languages and Literatures",
    "PN":"General Literature",
    "PQ":"French, Italian, Spanish, Portuguese Literature",
    "PR":"English Literature","PS":"American Literature",
    "PT":"German Literature",
    "PZ1":"Adventure Fiction","PZ2":"Detective and Mystery Fiction",
    "PZ3":"Classic Fiction","PZ4":"Contemporary Fiction",
    "PZ5":"Comic Books and Graphic Novels",
    "PZ7":"Children's Literature",
    "PZ8":"Folklore and Fairy Tales",
    "PZ":"Fiction and Juvenile Literature",
    "P":"Language and Literature",
    "QA":"Mathematics","QB":"Astronomy","QC":"Physics",
    "QD":"Chemistry","QE":"Geology",
    "QH":"Natural History and Biology","QK":"Botany",
    "QL":"Zoology","QM":"Human Anatomy","QP":"Physiology",
    "QR":"Microbiology","Q":"Science",
    "RA":"Public Health","RB":"Pathology",
    "RC":"Internal Medicine","RD":"Surgery",
    "RE":"Ophthalmology","RG":"Gynecology and Obstetrics",
    "RJ":"Pediatrics","RK":"Dentistry",
    "RL":"Dermatology","RM":"Pharmacology","RT":"Nursing",
    "R":"Medicine",
    "SB":"Plant Culture","SD":"Forestry",
    "SF":"Animal Culture","SH":"Fisheries","S":"Agriculture",
    "TA":"Engineering","TC":"Hydraulic Engineering",
    "TD":"Environmental Engineering",
    "TE":"Highway Engineering","TH":"Building Construction",
    "TJ":"Mechanical Engineering",
    "TK":"Electrical Engineering and Electronics",
    "TL":"Motor Vehicles and Aeronautics",
    "TN":"Mining Engineering","TP":"Chemical Technology",
    "TR":"Photography","TS":"Manufactures",
    "TT":"Handicrafts and Arts and Crafts",
    "TX":"Home Economics","T":"Technology",
    "UA":"Armies","UG":"Military Engineering and Air Forces",
    "U":"Military Science",
    "VK":"Navigation","VM":"Naval Architecture","V":"Naval Science",
    "Z":"Bibliography and Library Science",
    "ZA":"Information Resources",
}

_LCC_LIT = {
    "PQ1":"French Literature",
    "PQ3":"French Literature, Medieval",
    "PQ4":"Italian Literature",
    "PQ6":"Spanish Literature",
    "PQ7":"Spanish American Literature",
    "PQ8":"South American Literature",
    "PQ9":"Portuguese Literature",
    "PR":"English Literature","PS":"American Literature",
    "PT1":"German Literature","PT5":"Dutch Literature",
    "PT7":"Scandinavian Literature",
}


def _translate_lcc(code):
    if not code:
        return []
    raw = code.strip()
    tag = "LCC:" + raw
    upper = raw.upper()
    for key in sorted(_LCC_LIT.keys(), key=len, reverse=True):
        if upper.startswith(key):
            return [tag, _LCC_LIT[key]]
    for key in sorted([k for k in _LCC_BASE if k.startswith("PZ")],
                      key=len, reverse=True):
        if upper.startswith(key):
            return [tag, _LCC_BASE[key]]
    m = re.match(r'^([A-Z]{1,3})', upper)
    if not m:
        return [tag]
    prefix = m.group(1)
    for key in sorted(_LCC_BASE.keys(), key=len, reverse=True):
        if prefix == key or upper.startswith(key):
            return [tag, _LCC_BASE[key]]
    first = prefix[0]
    for key, val in _LCC_BASE.items():
        if key == first:
            return [tag, val]
    return [tag]


# ═══════════════════════════════════════════════════════════════
# UTILIDADES COMUNES
# ═══════════════════════════════════════════════════════════════

def _invert_author(marc_name):
    name = re.sub(r",?\s*\d{4}-\d{0,4}\s*$", "", marc_name).strip()
    name = name.rstrip(",. ")
    if "," not in name:
        return name
    parts = [p.strip() for p in name.split(",", 1)]
    return (parts[1] + " " + parts[0]) if len(parts) == 2 and parts[1] else parts[0]


def _extract_series_index(raw):
    if not raw:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", raw)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def _title_similarity(t1, t2):
    if not t1 or not t2:
        return 0.0
    clean = lambda t: re.sub(r"[^\w\s]", "", t.lower())
    w1 = set(clean(t1).split())
    w2 = set(clean(t2).split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / max(len(w1), len(w2))


def _score_metadata(mi):
    """
    Puntúa un Metadata por riqueza de campos rellenos.
    Se usa para elegir el mejor resultado entre múltiples candidatos.
    """
    score = 0
    if mi.publisher:                    score += 1
    if mi.pubdate:                      score += 1
    if mi.series:                       score += 2
    if mi.series_index is not None:     score += 1
    if mi.tags:                         score += min(len(mi.tags), 10)
    if mi.comments:                     score += 2
    if mi.language:                     score += 1
    if mi.identifiers.get("isbn"):      score += 1
    if mi.authors and mi.authors != ["Unknown"]: score += 1
    return score


def _is_complete(mi):
    """
    Devuelve True si el resultado tiene todos los campos clave rellenos.
    Un resultado completo no necesita enriquecimiento adicional.
    """
    return bool(
        mi.title
        and mi.authors and mi.authors != ["Unknown"]
        and mi.publisher
        and mi.pubdate
        and mi.tags
    )


# ═══════════════════════════════════════════════════════════════
# PLUGIN PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class BiblioMeta(Source):

    name                    = "BiblioMeta"
    description             = (
        "Metadatos bibliográficos desde fuentes autoritativas — "
        "BNE · LoC · Wikidata · Open Library · Google Books"
    )
    author                  = "Ludovico"
    version                 = (1, 2, 1)
    minimum_calibre_version = (5, 0, 0)
    supported_platforms     = ["windows", "osx", "linux"]
    type                    = "Metadata source"
    capabilities            = frozenset(["identify", "cover"])

    @property
    def touched_fields(self):
        fields = frozenset([
            "title", "authors", "publisher", "pubdate",
            "isbn", "language", "series", "series_index",
            "comments",  # v1.2: sinopsis BNE 520$a en merge
        ])
        if self.prefs.get("replace_tags", False):
            fields = fields | frozenset(["tags"])
        return fields

    has_html_comments               = False
    supports_gzip_transfer_encoding = True
    can_get_multiple_covers         = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Stats acumuladas en memoria — sin I/O por libro
        self._stats_delta = {
            "total": 0, "found": 0, "not_found": 0,
            "bne": 0, "loc": 0, "ol": 0, "wd": 0,
        }
        # Timeout dinámico por servidor — aprende del historial de sesión
        self._server_timeout = {
            "bne": _DEFAULT_TIMEOUT_BNE,
            "loc": _DEFAULT_TIMEOUT_LOC,
            "gb":  _DEFAULT_TIMEOUT_GBOOKS,
            "ol":  _DEFAULT_TIMEOUT_OL,
            "wd":  _DEFAULT_TIMEOUT_WD,
        }
        # Histórico de tiempos de respuesta para ajuste dinámico
        self._response_times = {"bne": [], "loc": [], "gb": [], "ol": []}

    # ── Timeout dinámico ──────────────────────────────────────

    def _record_response_time(self, server, elapsed):
        """
        Registra tiempo de respuesta y ajusta timeout del servidor.
        Mantiene ventana deslizante de 10 mediciones.
        """
        history = self._response_times.get(server, [])
        history.append(elapsed)
        if len(history) > 10:
            history = history[-10:]
        self._response_times[server] = history
        # Ajustar timeout: media + 2 desviaciones estándar, mínimo 5s
        if len(history) >= 3:
            avg = sum(history) / len(history)
            variance = sum((x - avg) ** 2 for x in history) / len(history)
            std = variance ** 0.5
            new_timeout = max(5.0, min(avg + 2 * std + 1.0, 30.0))
            self._server_timeout[server] = new_timeout

    def _get_timeout(self, server):
        return self._server_timeout.get(server, 20)

    # ── Configuración ─────────────────────────────────────────

    @property
    def prefs(self):
        if not hasattr(self, "_prefs"):
            self._prefs = JSONConfig("metadata_sources/BiblioMeta")
            self._prefs.defaults.update({
                "language_mode":    "all",
                "use_openlibrary":  True,
                "use_google_books": True,
                "use_wikidata":     True,
                "replace_tags":     False,
                "cdu_tags":         True,
                "genre_tags":       True,
                "lcc_tags":         True,
                "debug_log":        False,
                "stats": {
                    "total": 0, "found": 0, "not_found": 0,
                    "bne": 0, "loc": 0, "ol": 0, "wd": 0,
                    "last_run": "",
                },
            })
        return self._prefs

    def is_customizable(self):
        return True

    def config_widget(self):
        from qt.core import (
            QWidget, QVBoxLayout, QCheckBox,
            QGroupBox, QComboBox, QLabel, QHBoxLayout
        )
        w = QWidget()
        layout = QVBoxLayout()
        w.setLayout(layout)

        g_lang = QGroupBox("Idioma de la biblioteca")
        l_lang = QHBoxLayout()
        l_lang.addWidget(QLabel("Modo:"))
        w.cb_lang = QComboBox()
        w.cb_lang.addItem("Todos los idiomas (detección automática)", "all")
        w.cb_lang.addItem("Solo español  —  BNE + Open Library + Google Books", "spa")
        w.cb_lang.addItem("Solo inglés  —  LoC + Open Library + Google Books", "eng")
        idx = w.cb_lang.findData(self.prefs.get("language_mode", "all"))
        w.cb_lang.setCurrentIndex(idx if idx >= 0 else 0)
        l_lang.addWidget(w.cb_lang)
        l_lang.addStretch()
        g_lang.setLayout(l_lang)
        layout.addWidget(g_lang)

        g_sources = QGroupBox("Fuentes de metadatos")
        l_sources = QVBoxLayout()
        w.cb_openlibrary = QCheckBox(
            "Open Library  —  fallback por ISBN cuando la fuente primaria falla"
        )
        w.cb_openlibrary.setChecked(self.prefs["use_openlibrary"])
        l_sources.addWidget(w.cb_openlibrary)
        w.cb_wikidata = QCheckBox(
            "Wikidata  —  fallback para obras clásicas (género, serie, fecha)"
        )
        w.cb_wikidata.setChecked(self.prefs["use_wikidata"])
        l_sources.addWidget(w.cb_wikidata)
        w.cb_google = QCheckBox("Google Books  —  comentarios y portadas")
        w.cb_google.setChecked(self.prefs["use_google_books"])
        l_sources.addWidget(w.cb_google)
        g_sources.setLayout(l_sources)
        layout.addWidget(g_sources)

        g_tags = QGroupBox("Etiquetas (tags)")
        l_tags = QVBoxLayout()
        w.cb_replace = QCheckBox(
            "Reemplazar tags existentes con los de la fuente primaria"
        )
        w.cb_replace.setChecked(self.prefs["replace_tags"])
        l_tags.addWidget(w.cb_replace)
        w.cb_cdu = QCheckBox(
            "Tags CDU  —  clasificación española (código + descripción)"
        )
        w.cb_cdu.setChecked(self.prefs["cdu_tags"])
        l_tags.addWidget(w.cb_cdu)
        w.cb_lcc = QCheckBox(
            "Tags LCC  —  clasificación inglesa (código + descripción)"
        )
        w.cb_lcc.setChecked(self.prefs["lcc_tags"])
        l_tags.addWidget(w.cb_lcc)
        w.cb_genre = QCheckBox(
            "Género / forma  —  campo 655 de la fuente primaria"
        )
        w.cb_genre.setChecked(self.prefs["genre_tags"])
        l_tags.addWidget(w.cb_genre)
        g_tags.setLayout(l_tags)
        layout.addWidget(g_tags)

        g_adv = QGroupBox("Avanzado")
        l_adv = QVBoxLayout()
        w.cb_debug = QCheckBox(
            "Log detallado (debug)  —  activa solo para diagnóstico"
        )
        w.cb_debug.setChecked(self.prefs.get("debug_log", False))
        l_adv.addWidget(w.cb_debug)
        g_adv.setLayout(l_adv)
        layout.addWidget(g_adv)

        layout.addStretch()
        return w

    def save_settings(self, config_widget):
        w = config_widget
        self.prefs["language_mode"]    = w.cb_lang.currentData()
        self.prefs["use_openlibrary"]  = w.cb_openlibrary.isChecked()
        self.prefs["use_google_books"] = w.cb_google.isChecked()
        self.prefs["use_wikidata"]     = w.cb_wikidata.isChecked()
        self.prefs["replace_tags"]     = w.cb_replace.isChecked()
        self.prefs["cdu_tags"]         = w.cb_cdu.isChecked()
        self.prefs["lcc_tags"]         = w.cb_lcc.isChecked()
        self.prefs["genre_tags"]       = w.cb_genre.isChecked()
        self.prefs["debug_log"]        = w.cb_debug.isChecked()

    # ── Logging ───────────────────────────────────────────────

    def _log(self, log, msg, level="info"):
        """
        Logging condicional — solo DEBUG en modo debug,
        siempre warnings y errores.
        """
        if level == "warn":
            log.warn(msg)
        elif level == "error":
            log.exception(msg)
        elif self.prefs.get("debug_log", False):
            log.info(msg)

    # ── URL canónica ──────────────────────────────────────────

    def get_book_url(self, identifiers):
        bne_id = identifiers.get("bne", "")
        if bne_id and bne_id.startswith("bimo"):
            return (
                "bne", bne_id,
                "https://catalogo.bne.es/discovery/search"
                "?query=alma.identifier,exact," + bne_id,
            )
        loc_id = identifiers.get("loc", "")
        if loc_id:
            return ("loc", loc_id, "https://lccn.loc.gov/" + loc_id)
        return None

    def get_book_url_name(self, idtype, idval, url):
        return "BNE" if idtype == "bne" else "LoC"

    # ── Limpieza de título ────────────────────────────────────

    def _clean_title(self, title):
        t = re.sub(r'^[¿¡\s]+', '', title).strip()
        t = re.sub(r'^\d+[\s\-\.\)\:]+', '', t).strip()
        t = re.sub(r'^[\(\[][^\)\]]{1,40}[\)\]]\s*', '', t).strip()
        t = re.sub(r'\s*[\(\[][^\)\]]{1,40}[\)\]]\s*$', '', t).strip()
        return t

    def _extract_surname(self, author):
        author = re.split(r'[;&]', author)[0].strip()
        if "," in author:
            surname = author.split(",")[0].strip()
        else:
            parts = author.split()
            surname = parts[-1] if parts else author
        return surname if len(surname) >= 3 else ""

    # ── Detección de idioma ───────────────────────────────────

    def _detect_language(self, identifiers, title, authors):
        mode = self.prefs.get("language_mode", "all")
        if mode == "spa":
            return "spa"
        if mode == "eng":
            return "eng"
        if identifiers.get("bne"):
            return "spa"
        if identifiers.get("loc"):
            return "eng"
        isbn = identifiers.get("isbn", "")
        if isbn:
            spa_prefixes = (
                "9788", "97884", "97895", "97896", "97899",
                "9789580", "9789876", "9789682", "9789681",
            )
            if any(isbn.startswith(p) for p in spa_prefixes):
                return "spa"
            eng_prefixes = ("9780", "9781")
            if any(isbn.startswith(p) for p in eng_prefixes):
                return "eng"
        return "both"

    # ── Ranking ───────────────────────────────────────────────

    def _rank_results(self, results, title):
        """
        v1.2.1: similitud de título es criterio primario.
        La riqueza de metadatos actúa solo como desempate.
        Resultados con similitud muy baja respecto al mejor se descartan
        para evitar confusiones entre títulos distintos.
        """
        if not results or len(results) == 1:
            return results

        scored = [
            (mi, _title_similarity(title, mi.title), _score_metadata(mi))
            for mi in results
        ]

        # Filtrar resultados con similitud muy baja respecto al mejor
        max_sim = max(s for _, s, _ in scored)
        if max_sim > 0.3:
            scored = [
                (mi, s, m) for mi, s, m in scored
                if s >= max_sim * 0.5
            ]

        # Ordenar: primero similitud de título, riqueza como desempate
        return [
            mi for mi, s, m in sorted(
                scored,
                key=lambda x: (x[1], x[2]),
                reverse=True,
            )
        ]

    # ── Queries BNE ───────────────────────────────────────────

    def _build_query_spa(self, isbn, title, authors, identifiers):
        """
        v1.2.1: estrategia de identificadores verificada contra SRU de Alma:
          - alma.mms_id funciona exactamente para IDs numéricos 991...
          - alma.local_control_number devuelve ~6M resultados (inútil)
          - alma.identifier devuelve siempre 0
          - bimoBNE no tiene índice SRU exacto — ignorar, caer a ISBN
        """
        bne_id  = identifiers.get("bne", "")
        bne_mms = identifiers.get("bne-mms", "")

        # MMS ID numérico (991...) en cualquiera de los dos campos → exacto
        mms = bne_mms or bne_id
        if mms and mms.startswith("991"):
            return 'alma.mms_id="%s"' % mms, None

        # bimoBNE: sin índice SRU exacto en Alma — caer a ISBN o título+autor

        if isbn:
            primary = 'alma.isbn="%s"' % isbn
            fallback = None
            if title:
                clean   = self._clean_title(title)
                surname = self._extract_surname(authors[0]) if authors else ""
                if surname:
                    fallback = (
                        'alma.title="%s" and alma.creator all "%s"'
                        ' and alma.lang="spa"' % (clean, surname)
                    )
                else:
                    fallback = 'alma.title="%s" and alma.lang="spa"' % clean
            return primary, fallback

        if title:
            clean = self._clean_title(title)
            if authors:
                surname = self._extract_surname(authors[0])
                if surname:
                    primary = (
                        'alma.title="%s" and alma.creator all "%s"'
                        ' and alma.lang="spa"' % (clean, surname)
                    )
                else:
                    primary = 'alma.title="%s" and alma.lang="spa"' % clean
            else:
                primary = 'alma.title="%s" and alma.lang="spa"' % clean
            return primary, None

        return None, None

    # ── Queries LoC ───────────────────────────────────────────

    def _build_query_eng(self, isbn, title, authors, identifiers):
        loc_id = identifiers.get("loc", "")
        if loc_id:
            return 'bath.lccn="%s"' % loc_id, None

        if isbn:
            primary = 'bath.isbn="%s"' % isbn
            fallback = None
            if title:
                clean   = self._clean_title(title)
                surname = self._extract_surname(authors[0]) if authors else ""
                if surname:
                    fallback = (
                        'dc.title="%s" and dc.creator="%s"'
                        % (clean, surname)
                    )
                else:
                    fallback = 'dc.title="%s"' % clean
            return primary, fallback

        if title:
            clean = self._clean_title(title)
            if authors:
                surname = self._extract_surname(authors[0])
                if surname:
                    primary = (
                        'dc.title="%s" and dc.creator="%s"'
                        % (clean, surname)
                    )
                else:
                    primary = 'dc.title="%s"' % clean
            else:
                primary = 'dc.title="%s"' % clean
            return primary, None

        return None, None

    # ── maximumRecords dinámico ───────────────────────────────

    def _max_records(self, query, fallback):
        """
        1 cuando la query es por ID o ISBN exacto (resultado único esperado).
        3 cuando es por título+autor (necesitamos ranking).
        """
        if fallback is None and (
            "isbn" in query
            or "local_control_number" in query
            or "lccn" in query
            or "mms_id" in query
        ):
            return 1
        return 3

    # ── SRU ───────────────────────────────────────────────────

    def _run_sru(self, base_url, query, server_key, log, max_records=3, retry=2):
        params = {
            "operation":      "searchRetrieve",
            "version":        SRU_VERSION,
            "query":          query,
            "recordSchema":   "marcxml",
            "startRecord":    "1",
            "maximumRecords": str(max_records),
        }
        url = base_url + "?" + urllib.parse.urlencode(params)
        self._log(log, "SRU: %s" % url)
        timeout = self._get_timeout(server_key)
        for attempt in range(retry + 1):
            t0 = time.time()
            try:
                raw = self.browser.open_novisit(url, timeout=timeout).read()
                self._record_response_time(server_key, time.time() - t0)
                return raw
            except Exception as exc:
                err = str(exc)
                if ("502" in err or "503" in err) and attempt < retry:
                    wait = 2 ** attempt
                    self._log(log, "SRU %s — reintento en %ds" % (err[:20], wait), "warn")
                    time.sleep(wait)
                else:
                    raise

    def _process_sru(self, raw, log, abort, lang_filter=None):
        try:
            root = etree.fromstring(raw)
        except Exception as exc:
            self._log(log, "SRU XML: %s" % exc, "warn")
            return []
        diags = root.findall(".//srw:diagnostic/srw:message", NS)
        if diags:
            self._log(log, "SRU diag: %s" % "; ".join(d.text or "" for d in diags), "warn")
            return []
        records = root.findall(".//srw:record/srw:recordData/marc:record", NS)
        self._log(log, "SRU: %d registro(s)" % len(records))
        results = []
        for idx, record in enumerate(records):
            if abort.is_set():
                break
            try:
                mi = self._marc_to_metadata(record, log, lang_filter)
                if mi is not None:
                    mi.source_relevance = idx
                    results.append(mi)
            except Exception as exc:
                self._log(log, "SRU registro %d: %s" % (idx, exc), "warn")
        return results

    # ── Google Books ──────────────────────────────────────────

    def _gbooks_fetch(self, isbn, log, retry=2):
        timeout = self._get_timeout("gb")
        for attempt in range(retry + 1):
            t0 = time.time()
            try:
                params = urllib.parse.urlencode({
                    "q":          "isbn:" + isbn,
                    "maxResults": "1",
                    "fields":     "items(id,volumeInfo(description,imageLinks))",
                })
                url = GBOOKS_API + "?" + params
                self._log(log, "Google Books: %s" % url)
                with urllib.request.urlopen(url, timeout=timeout) as r:
                    data = json.loads(r.read().decode("utf-8"))
                self._record_response_time("gb", time.time() - t0)
                items = data.get("items", [])
                return items[0] if items else None
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retry:
                    wait = 2 ** attempt
                    self._log(log, "Google Books 429 — reintento en %ds" % wait, "warn")
                    time.sleep(wait)
                else:
                    self._log(log, "Google Books error: %s" % e, "warn")
                    return None
            except Exception as exc:
                self._log(log, "Google Books error: %s" % exc, "warn")
                return None
        return None

    def _gbooks_apply(self, mi, item, log, check_lang=True):
        vol = item.get("volumeInfo", {})
        gid = item.get("id", "")
        if not mi.comments:
            desc = vol.get("description", "")
            if desc:
                if not check_lang or _is_spanish(desc):
                    mi.comments = desc
                    self._log(log, "Google Books: comments añadidos")
                elif check_lang:
                    self._log(log, "Google Books: comments descartados (idioma)")
        imgs = vol.get("imageLinks", {})
        cover_url = (
            imgs.get("large") or imgs.get("medium")
            or imgs.get("thumbnail") or imgs.get("smallThumbnail")
        )
        if cover_url and gid:
            cover_url = re.sub(r"zoom=\d", "zoom=3", cover_url)
            cover_url = cover_url.replace("&edge=curl", "")
            self.cache_identifier_to_cover_url(gid, cover_url)
            mi.set_identifier("google", gid)
            self._log(log, "Google Books: portada en caché")

    # ── Open Library ──────────────────────────────────────────

    def _openlibrary_fetch(self, isbn, log):
        timeout = self._get_timeout("ol")
        t0 = time.time()
        try:
            params = urllib.parse.urlencode({
                "bibkeys": "ISBN:" + isbn,
                "format":  "json",
                "jscmd":   "data",
            })
            url = OPENLIBRARY_API + "?" + params
            self._log(log, "Open Library: %s" % url)
            with urllib.request.urlopen(url, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            self._record_response_time("ol", time.time() - t0)
            return data.get("ISBN:" + isbn)
        except Exception as exc:
            self._log(log, "Open Library error: %s" % exc, "warn")
            return None

    def _openlibrary_to_metadata(self, data, isbn, log):
        title = data.get("title", "")
        if not title:
            return None
        authors = [
            a.get("name", "") for a in data.get("authors", [])
            if a.get("name")
        ]
        mi = Metadata(title, authors if authors else ["Unknown"])
        if isbn:
            mi.set_identifier("isbn", isbn)
        publishers = data.get("publishers", [])
        if publishers:
            mi.publisher = publishers[0].get("name", "").rstrip(",. ")
        pub_date = data.get("publish_date", "")
        if pub_date:
            m = re.search(r"\d{4}", pub_date)
            if m:
                try:
                    mi.pubdate = datetime(int(m.group()), 1, 1)
                except ValueError:
                    pass
        subjects = data.get("subjects", [])
        if subjects:
            tags = []
            for s in subjects[:8]:
                val = s.get("name", s) if isinstance(s, dict) else s
                if val and isinstance(val, str):
                    tags.append(val.rstrip(".,- "))
            if tags:
                mi.tags = tags
        self._log(log, "Open Library: %s" % title)
        return mi

    # ── Wikidata ──────────────────────────────────────────────

    def _wikidata_fetch(self, title, authors, lang, log):
        if not title:
            return None
        clean = self._clean_title(title)
        query = '''
SELECT ?item ?itemLabel ?authorLabel ?seriesLabel ?pubdate ?genreLabel WHERE {
  ?item wdt:P31 wd:Q7725634 .
  ?item rdfs:label "%s"@%s .
  OPTIONAL { ?item wdt:P50 ?author }
  OPTIONAL { ?item wdt:P179 ?series }
  OPTIONAL { ?item wdt:P577 ?pubdate }
  OPTIONAL { ?item wdt:P136 ?genre }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%s,en" }
} LIMIT 1
''' % (clean.replace('"', '\\"'), lang, lang)
        try:
            params = urllib.parse.urlencode({"query": query, "format": "json"})
            url = WIKIDATA_SPARQL + "?" + params
            self._log(log, "Wikidata: %s" % url[:80])
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "BiblioMeta/1.2 (Calibre plugin)")
            req.add_header("Accept", "application/sparql-results+json")
            timeout = self._get_timeout("wd")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            results = data.get("results", {}).get("bindings", [])
            return results[0] if results else None
        except Exception as exc:
            self._log(log, "Wikidata error: %s" % exc, "warn")
            return None

    def _wikidata_apply(self, mi, wd_result, log):
        if not wd_result:
            return
        author = wd_result.get("authorLabel", {}).get("value", "")
        if author and mi.authors == ["Unknown"]:
            mi.authors = [author]
        pubdate = wd_result.get("pubdate", {}).get("value", "")
        if pubdate and not mi.pubdate:
            m = re.search(r"(\d{4})", pubdate)
            if m:
                try:
                    mi.pubdate = datetime(int(m.group(1)), 1, 1)
                except ValueError:
                    pass
        series = wd_result.get("seriesLabel", {}).get("value", "")
        if series and not mi.series:
            mi.series = series
            self._log(log, "Wikidata: serie — %s" % series)
        genre = wd_result.get("genreLabel", {}).get("value", "")
        if genre:
            existing = list(mi.tags or [])
            if genre not in existing:
                existing.append(genre)
                mi.tags = existing
                self._log(log, "Wikidata: género — %s" % genre)

    # ── Stats ─────────────────────────────────────────────────

    def _update_stats(self, found, source):
        self._stats_delta["total"] += 1
        if found:
            self._stats_delta["found"] += 1
            if source and source in self._stats_delta:
                self._stats_delta[source] += 1
        else:
            self._stats_delta["not_found"] += 1

    def flush_stats(self):
        try:
            stats = dict(self.prefs.get("stats", {}))
            for k, v in self._stats_delta.items():
                stats[k] = stats.get(k, 0) + v
            stats["last_run"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            self.prefs["stats"] = stats
            for k in self._stats_delta:
                self._stats_delta[k] = 0
        except Exception:
            pass

    # ── Portadas ──────────────────────────────────────────────

    def get_cached_cover_url(self, identifiers):
        gid = identifiers.get("google")
        if gid:
            url = self.cached_identifier_to_cover_url(gid)
            if url:
                return url
        isbn = identifiers.get("isbn")
        if isbn:
            url = self.cached_identifier_to_cover_url("ol_" + isbn)
            if url:
                return url
        return None

    def download_cover(self, log, result_queue, abort,
                       title=None, authors=None, identifiers={},
                       timeout=30, get_best_cover=False):
        isbn = check_isbn(identifiers.get("isbn", ""))
        cached = self.get_cached_cover_url(identifiers)
        if cached:
            self._fetch_cover(cached, log, result_queue, self._get_timeout("gb"))
            return
        if not isbn:
            self._log(log, "BiblioMeta cover: se requiere ISBN", "warn")
            return
        if self.prefs["use_google_books"]:
            try:
                params = urllib.parse.urlencode({
                    "q":          "isbn:" + isbn,
                    "maxResults": "1",
                    "fields":     "items(id,volumeInfo(imageLinks))",
                })
                url = GBOOKS_API + "?" + params
                with urllib.request.urlopen(url, timeout=self._get_timeout("gb")) as r:
                    data = json.loads(r.read().decode("utf-8"))
                items = data.get("items", [])
                if items:
                    vol  = items[0].get("volumeInfo", {})
                    gid  = items[0].get("id", "")
                    imgs = vol.get("imageLinks", {})
                    cover_url = (
                        imgs.get("large") or imgs.get("medium")
                        or imgs.get("thumbnail") or imgs.get("smallThumbnail")
                    )
                    if cover_url:
                        cover_url = re.sub(r"zoom=\d", "zoom=3", cover_url)
                        cover_url = cover_url.replace("&edge=curl", "")
                        if self._fetch_cover(cover_url, log, result_queue,
                                             self._get_timeout("gb")):
                            if gid:
                                self.cache_identifier_to_cover_url(gid, cover_url)
                            return
            except Exception as exc:
                self._log(log, "Google Books cover: %s" % exc, "warn")
        if abort.is_set():
            return
        try:
            ol_url = OPENLIBRARY_COVER % isbn
            if self._fetch_cover(ol_url, log, result_queue, self._get_timeout("ol")):
                self.cache_identifier_to_cover_url("ol_" + isbn, ol_url)
        except Exception as exc:
            self._log(log, "Open Library cover: %s" % exc, "warn")

    def _fetch_cover(self, url, log, result_queue, timeout):
        try:
            data = self.browser.open_novisit(url, timeout=timeout).read()
            if data and len(data) > 1000:
                result_queue.put((self, data))
                self._log(log, "Cover: %d bytes" % len(data))
                return True
            self._log(log, "Cover: placeholder ignorado", "warn")
            return False
        except Exception as exc:
            self._log(log, "Cover fetch: %s" % exc, "warn")
            return False

    # ── Identify principal ─────────────────────────────────────

    def identify(self, log, result_queue, abort,
                 title=None, authors=None, identifiers={}, timeout=30):
        log.info("BiblioMeta v1.2.0: identify()")

        # Validar ISBN antes de procesar
        isbn_raw = identifiers.get("isbn", "")
        isbn = check_isbn(isbn_raw) if isbn_raw else None
        if isbn_raw and not isbn:
            self._log(log, "ISBN inválido ignorado: %s" % isbn_raw, "warn")

        lang = self._detect_language(
            {**identifiers, "isbn": isbn or ""}, title, authors
        )
        self._log(log, "BiblioMeta: idioma — %s" % lang)

        if lang == "both":
            self._identify_both(
                log, result_queue, abort,
                title, authors, identifiers, isbn
            )
        elif lang == "eng":
            self._identify_eng(
                log, result_queue, abort,
                title, authors, identifiers, isbn
            )
        else:
            self._identify_spa(
                log, result_queue, abort,
                title, authors, identifiers, isbn
            )

        return None

    # ── Modo "both" paralelo ──────────────────────────────────

    def _identify_both(self, log, result_queue, abort,
                       title, authors, identifiers, isbn):
        """
        Lanza BNE y LoC en paralelo. Publica el resultado con más metadatos.
        Tiempo total ≈ max(BNE, LoC) en lugar de BNE + LoC.
        """
        spa_q = Queue()
        eng_q = Queue()

        def run_spa():
            try:
                self._identify_spa(
                    log, spa_q, abort, title, authors, identifiers, isbn
                )
            except Exception as exc:
                self._log(log, "Both/spa error: %s" % exc, "warn")

        def run_eng():
            try:
                self._identify_eng(
                    log, eng_q, abort, title, authors, identifiers, isbn
                )
            except Exception as exc:
                self._log(log, "Both/eng error: %s" % exc, "warn")

        t_spa = Thread(target=run_spa, daemon=True)
        t_eng = Thread(target=run_eng, daemon=True)
        t_spa.start()
        t_eng.start()

        timeout_both = max(
            self._get_timeout("bne"),
            self._get_timeout("loc")
        ) + 3

        t_spa.join(timeout=timeout_both)
        t_eng.join(timeout=timeout_both)

        # Recoger resultados de ambas colas
        candidates = []
        while True:
            try:
                candidates.append(spa_q.get_nowait())
            except Empty:
                break
        while True:
            try:
                candidates.append(eng_q.get_nowait())
            except Empty:
                break

        if not candidates:
            self._update_stats(False, None)
            return

        # Elegir el resultado con más metadatos
        best = max(candidates, key=_score_metadata)
        result_queue.put(best)
        self._log(log, "Both: elegido resultado con score %d" % _score_metadata(best))

    # ── Cadena española ───────────────────────────────────────

    def _identify_spa(self, log, result_queue, abort,
                      title, authors, identifiers, isbn):
        query, fallback = self._build_query_spa(isbn, title, authors, identifiers)
        if not query:
            self._log(log, "BNE: se requiere ISBN o título.", "warn")
            return

        # Flag de cancelación temprana para Google Books
        gb_needed  = [True]
        gb_container = [None]

        if isbn and self.prefs["use_google_books"]:
            def fetch_gb():
                if gb_needed[0]:
                    gb_container[0] = self._gbooks_fetch(isbn, log)
            t_gb = Thread(target=fetch_gb, daemon=True)
            t_gb.start()
        else:
            t_gb = None

        # BNE query
        results = []
        try:
            max_rec = self._max_records(query, fallback)
            raw     = self._run_sru(BNE_SRU_BASE, query, "bne", log, max_rec)
            results = self._process_sru(raw, log, abort, lang_filter="spa")
        except Exception as exc:
            self._log(log, "BNE: %s" % exc, "warn")

        if not results and fallback and not abort.is_set():
            self._log(log, "BNE fallback: %s" % fallback)
            try:
                raw2    = self._run_sru(BNE_SRU_BASE, fallback, "bne", log, 3)
                results = self._process_sru(raw2, log, abort, lang_filter="spa")
            except Exception as exc:
                self._log(log, "BNE fallback: %s" % exc, "warn")

        # Cancelar GB si BNE devuelve resultado con comments (520$a)
        if results and results[0].comments:
            gb_needed[0] = False
            self._log(log, "BNE: comments desde 520$a — GB cancelado")

        if t_gb:
            t_gb.join(timeout=self._get_timeout("gb") + 1)

        # Open Library por ISBN como fallback
        if not results and isbn and not abort.is_set() \
                and self.prefs["use_openlibrary"]:
            ol_data = self._openlibrary_fetch(isbn, log)
            if ol_data:
                mi = self._openlibrary_to_metadata(ol_data, isbn, log)
                if mi:
                    if gb_container[0]:
                        self._gbooks_apply(mi, gb_container[0], log, check_lang=True)
                    if self.prefs.get("use_wikidata", True) and title and not mi.tags:
                        wd = self._wikidata_fetch(title, authors, "es", log)
                        self._wikidata_apply(mi, wd, log)
                    mi.source_relevance = 0
                    result_queue.put(mi)
                    self._update_stats(True, "ol")
                    return

        # Wikidata solo si no hay tags
        if not results and not abort.is_set() \
                and self.prefs.get("use_wikidata", True) and title:
            wd = self._wikidata_fetch(title, authors, "es", log)
            if wd:
                t_val = wd.get("itemLabel", {}).get("value", "")
                a_val = wd.get("authorLabel", {}).get("value", "")
                if t_val:
                    mi = Metadata(t_val, [a_val] if a_val else ["Unknown"])
                    self._wikidata_apply(mi, wd, log)
                    if isbn:
                        mi.set_identifier("isbn", isbn)
                    if gb_container[0]:
                        self._gbooks_apply(mi, gb_container[0], log, check_lang=True)
                    mi.source_relevance = 0
                    result_queue.put(mi)
                    self._update_stats(True, "wd")
                    return

        if title and len(results) > 1:
            results = self._rank_results(results, title)

        source = "bne" if results else None
        for mi in results:
            if abort.is_set():
                break
            if gb_container[0]:
                self._gbooks_apply(mi, gb_container[0], log, check_lang=True)
            # Wikidata solo si faltan tags
            if self.prefs.get("use_wikidata", True) and title and not mi.tags:
                wd = self._wikidata_fetch(title, authors, "es", log)
                self._wikidata_apply(mi, wd, log)
            # Abort temprano si el resultado está completo
            result_queue.put(mi)
            if _is_complete(mi):
                self._log(log, "BNE: resultado completo — abort temprano")
                break

        self._update_stats(bool(results), source)

    # ── Cadena inglesa ────────────────────────────────────────

    def _identify_eng(self, log, result_queue, abort,
                      title, authors, identifiers, isbn):
        query, fallback = self._build_query_eng(isbn, title, authors, identifiers)
        if not query:
            self._log(log, "LoC: se requiere ISBN o título.", "warn")
            return

        gb_needed    = [True]
        gb_container = [None]

        if isbn and self.prefs["use_google_books"]:
            def fetch_gb():
                if gb_needed[0]:
                    gb_container[0] = self._gbooks_fetch(isbn, log)
            t_gb = Thread(target=fetch_gb, daemon=True)
            t_gb.start()
        else:
            t_gb = None

        results = []
        try:
            max_rec = self._max_records(query, fallback)
            raw     = self._run_sru(LOC_SRU_BASE, query, "loc", log, max_rec)
            results = self._process_sru(raw, log, abort, lang_filter="eng")
        except Exception as exc:
            self._log(log, "LoC: %s" % exc, "warn")

        if not results and fallback and not abort.is_set():
            self._log(log, "LoC fallback: %s" % fallback)
            try:
                raw2    = self._run_sru(LOC_SRU_BASE, fallback, "loc", log, 3)
                results = self._process_sru(raw2, log, abort, lang_filter="eng")
            except Exception as exc:
                self._log(log, "LoC fallback: %s" % exc, "warn")

        if results and results[0].comments:
            gb_needed[0] = False

        if t_gb:
            t_gb.join(timeout=self._get_timeout("gb") + 1)

        if not results and isbn and not abort.is_set() \
                and self.prefs["use_openlibrary"]:
            ol_data = self._openlibrary_fetch(isbn, log)
            if ol_data:
                mi = self._openlibrary_to_metadata(ol_data, isbn, log)
                if mi:
                    if gb_container[0]:
                        self._gbooks_apply(mi, gb_container[0], log, check_lang=False)
                    if self.prefs.get("use_wikidata", True) and title and not mi.tags:
                        wd = self._wikidata_fetch(title, authors, "en", log)
                        self._wikidata_apply(mi, wd, log)
                    mi.source_relevance = 0
                    result_queue.put(mi)
                    self._update_stats(True, "ol")
                    return

        if not results and not abort.is_set() \
                and self.prefs.get("use_wikidata", True) and title:
            wd = self._wikidata_fetch(title, authors, "en", log)
            if wd:
                t_val = wd.get("itemLabel", {}).get("value", "")
                a_val = wd.get("authorLabel", {}).get("value", "")
                if t_val:
                    mi = Metadata(t_val, [a_val] if a_val else ["Unknown"])
                    self._wikidata_apply(mi, wd, log)
                    if isbn:
                        mi.set_identifier("isbn", isbn)
                    if gb_container[0]:
                        self._gbooks_apply(mi, gb_container[0], log, check_lang=False)
                    mi.source_relevance = 0
                    result_queue.put(mi)
                    self._update_stats(True, "wd")
                    return

        if title and len(results) > 1:
            results = self._rank_results(results, title)

        source = "loc" if results else None
        for mi in results:
            if abort.is_set():
                break
            if gb_container[0]:
                self._gbooks_apply(mi, gb_container[0], log, check_lang=False)
            if self.prefs.get("use_wikidata", True) and title and not mi.tags:
                wd = self._wikidata_fetch(title, authors, "en", log)
                self._wikidata_apply(mi, wd, log)
            result_queue.put(mi)
            if _is_complete(mi):
                self._log(log, "LoC: resultado completo — abort temprano")
                break

        self._update_stats(bool(results), source)

    # ── MARC XML → Metadata ────────────────────────────────────

    def _marc_to_metadata(self, record, log, lang_filter=None):

        def get_control(tag):
            el = record.find("marc:controlfield[@tag='%s']" % tag, NS)
            return el.text.strip() if el is not None and el.text else None

        def get_subfields(tag, *codes):
            results = []
            for field in record.findall(
                "marc:datafield[@tag='%s']" % tag, NS
            ):
                for code in codes:
                    for sub in field.findall(
                        "marc:subfield[@code='%s']" % code, NS
                    ):
                        if sub.text:
                            results.append(sub.text.strip())
            return results

        def first_subfield(tag, *codes):
            vals = get_subfields(tag, *codes)
            return vals[0] if vals else None

        mms_id = get_control("001")
        bne_id = None
        loc_id = None

        for field in record.findall("marc:datafield[@tag='016']", NS):
            source = field.find("marc:subfield[@code='2']", NS)
            val    = field.find("marc:subfield[@code='a']", NS)
            if source is not None and "SpMaBN" in (source.text or ""):
                if val is not None and val.text:
                    bne_id = val.text.strip()
                    break

        lccn_raw = first_subfield("010", "a")
        if lccn_raw:
            loc_id = lccn_raw.strip()

        if not bne_id:
            bne_id = mms_id

        lang_edition = first_subfield("041", "a")
        target_lang  = "spa" if lang_filter == "spa" else "eng"

        title = None
        if lang_edition and lang_edition.lower() != target_lang:
            titulo_uniforme = first_subfield("240", "a")
            if titulo_uniforme:
                title = titulo_uniforme.rstrip(" /=:").strip()
                self._log(log, "MARC: edición '%s', 240$a: %s" % (lang_edition, title))

        if not title:
            title_parts = get_subfields("245", "a", "b")
            title = (
                " ".join(title_parts).rstrip(" /=:").strip()
                if title_parts else None
            )

        if not title:
            return None

        if lang_filter == "spa" and lang_edition \
                and lang_edition.lower() not in ("spa", "") \
                and not first_subfield("240", "a"):
            self._log(log, "MARC: edición '%s' sin 240$a, descartada" % lang_edition)
            return None

        # Autores
        authors = []
        main_raw = first_subfield("100", "a")
        if main_raw:
            authors.append(_invert_author(main_raw))

        for field in record.findall("marc:datafield[@tag='700']", NS):
            relator_e = field.find("marc:subfield[@code='e']", NS)
            relator_4 = field.find("marc:subfield[@code='4']", NS)
            relator_val = ""
            if relator_e is not None and relator_e.text:
                relator_val = relator_e.text.lower().rstrip(". ,")
            elif relator_4 is not None and relator_4.text:
                relator_val = relator_4.text.lower().strip()
            if relator_val and relator_val in EXCLUDED_RELATORS:
                continue
            name_sub = field.find("marc:subfield[@code='a']", NS)
            if name_sub is not None and name_sub.text:
                inv = _invert_author(name_sub.text)
                if inv and inv not in authors:
                    authors.append(inv)

        mi = Metadata(title, authors if authors else ["Unknown"])

        if bne_id and (lang_filter == "spa" or not loc_id):
            mi.set_identifier("bne", bne_id)
        if mms_id and lang_filter == "spa":
            mi.set_identifier("bne-mms", mms_id)
        if loc_id:
            mi.set_identifier("loc", loc_id)
        if mms_id and lang_filter == "eng":
            mi.set_identifier("loc-mms", mms_id)

        raw_isbn = first_subfield("020", "a")
        if raw_isbn:
            clean = re.sub(r"[^\dX]", "", raw_isbn.split()[0])
            valid = check_isbn(clean)
            if valid:
                mi.set_identifier("isbn", valid)

        publisher = first_subfield("260", "b") or first_subfield("264", "b")
        if publisher:
            mi.publisher = publisher.rstrip(",. ")

        pub_year = first_subfield("260", "c") or first_subfield("264", "c")
        if pub_year:
            m = re.search(r"\d{4}", pub_year)
            if m:
                try:
                    mi.pubdate = datetime(int(m.group()), 1, 1)
                except ValueError:
                    pass

        field_008 = get_control("008")
        lang_008  = None
        if field_008 and len(field_008) >= 38:
            c = field_008[35:38].strip().lower()
            if c and c not in ("   ", "und", ""):
                lang_008 = c
        language = lang_edition or lang_008
        if language:
            mi.language = language[:3].lower()

        # Serie: 490 → 830 → 440
        series_name = None
        series_vol  = None
        for stag in ("490", "830", "440"):
            nr = first_subfield(stag, "a")
            if nr:
                series_name = nr.rstrip(" ,;")
                series_vol  = first_subfield(stag, "v")
                break
        if series_name:
            mi.series = series_name
            idx = _extract_series_index(series_vol)
            if idx is not None:
                mi.series_index = idx

        # Sinopsis (520)
        comments = first_subfield("520", "a")
        if comments:
            mi.comments = comments

        # Tags
        tags = []

        # 650 — materias LCSH / BNE
        for val in get_subfields("650", "a"):
            clean = val.rstrip(".,- ")
            if clean and clean not in tags:
                tags.append(clean)

        # 653 — palabras clave libres (v1.2)
        for val in get_subfields("653", "a"):
            clean = val.rstrip(".,- ")
            if clean and clean not in tags:
                tags.append(clean)

        # 655 — género/forma
        if self.prefs["genre_tags"]:
            for val in get_subfields("655", "a"):
                clean = val.rstrip(".,- ")
                if clean and clean not in tags:
                    tags.append(clean)

        # 080 — CDU (español)
        if lang_filter == "spa" and self.prefs["cdu_tags"]:
            for cdu_raw in get_subfields("080", "a"):
                if not cdu_raw.strip():
                    continue
                bio_subject = _extract_bio_subject(cdu_raw)
                if bio_subject and bio_subject not in tags:
                    tags.append(bio_subject)
                geo_loc = _extract_geo_locality(cdu_raw)
                if geo_loc and geo_loc not in tags:
                    tags.append(geo_loc)
                cdu_code = _clean_cdu_code(cdu_raw)
                for t in _translate_cdu(cdu_code):
                    if t and t not in tags:
                        tags.append(t)

        # 050 — LCC (inglés)
        if lang_filter == "eng" and self.prefs["lcc_tags"]:
            for lcc_raw in get_subfields("050", "a"):
                if not lcc_raw.strip():
                    continue
                for t in _translate_lcc(lcc_raw.strip()):
                    if t and t not in tags:
                        tags.append(t)

        if tags:
            mi.tags = tags

        return mi
