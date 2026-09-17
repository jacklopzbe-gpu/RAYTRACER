# ARCHITECTURE — cómo está construido el path tracer

Documento para humanos y para modelos de lenguaje que vayan a modificar el proyecto. Describe el flujo de datos,
cada archivo, las decisiones tomadas y las particularidades de TouchDesigner 2025 que condicionan el diseño.

## 1. Idea general

Un path tracer progresivo de Monte Carlo corre como **compute shader dentro de un GLSL POP**: cada punto de un
Grid POP de `Resw × Resh` puntos es un píxel. El kernel traza caminos con hasta `Bounces` rebotes, hace Next Event
Estimation (NEE) con MIS contra las luces de área, y escribe en el atributo `Color` la media acumulada (rgb) y el
número de samples (a). Un POP to TOP convierte el atributo en imagen, un Feedback TOP la devuelve al kernel como
`sPrev` para el siguiente frame, y un GLSL TOP de display aplica exposición, ACES y sRGB.

Las mallas se intersectan con **ray tracing por hardware**: el GLSL POP recibe un Collision POP (la malla
triangulada) y el shader usa `rayQueryEXT`. Los objetos de demostración (piso, esferas, caja, luz rectangular)
son analíticos en el shader.

## 2. Flujo de datos

```
                         cam1 (Camera COMP) ── accum_ctl escribe su matriz en uCamC0..3 cada frame
                                                        │
 pix_grid (Grid POP W×H, sin conectividad) ──► trace_pop (GLSL POP, compute) ──► acc (POP to TOP, attr Color)
   in_mesh ─► mesh_src(switch) ─► mesh_in ─► mesh_attr_defaults ─► mesh_tri ──┤ colpop (Collision POP)   │
   mesh_sphere ─┘                             (mat, Color)      (Triangulate) │                           │
                                                   └─► mesh_verts (Attribute Convert point→vertex) ─► In POPs[1]
   in_albedo/in_rm/in_normal/in_emit ─► tex_*_sw ─► maps_atlas_a ─► maps_atlas (2×2) ─► sampler sAtlas    │
   in_env ─► env_sw (env_default) ─► sampler sEnv                                                          │
   black (Constant TOP 32f) ─► fb (Feedback TOP, target = acc) ─► sampler sPrev ◄─────────────────────────┘
 acc ─► display (GLSL TOP: exposure, ACES, sRGB) ─► denoise (Nvidia Denoise TOP) ─► denoise_switch ─► out_final ─► movieout
```

`accum_ctl` (Execute DAT, Frame Start) es el "sistema nervioso": ver §4.

## 3. Archivos

| Archivo | Papel |
|---|---|
| `shaders/common.glsl` | Biblioteca: `Ray`, `Hit`, intersecciones (plano, esfera, caja, triángulo), RNG PCG, muestreo coseno y GGX-VNDF, BSDF GGX + Lambert (`bsdfEval`, `bsdfSample`), estructuras `Material` y `RectLight`. Se incluye con `#include "common_glsl"` (nombre del Text DAT). |
| `shaders/trace.glsl` | Kernel del GLSL POP. Escena analítica, `hitMesh` (ray query + atributos interpolados + tangentes), materiales, mapas, efectos de vidrio, NEE/MIS, loop de camino, acumulación con ventana temporal. Las uniforms **no se declaran** en el shader: las declara el POP. |
| `shaders/display.frag` | Exposición, tonemap ACES, linear→sRGB, visualización del contador. |
| `shaders/env_default.frag` | Entorno equirectangular generado (rayas azul/naranja animadas). |
| `shaders/atlas_a.frag`, `atlas_b.frag` | Empaquetan los 4 mapas de material en un atlas 2×2 (el GLSL TOP solo tiene 3 entradas y el sampler del POP prefiere una textura). |
| `shaders/checker.frag` | Textura de prueba. |
| `shaders/legacy/trace_top.frag` | Kernel original como GLSL TOP (Tareas 1–12 del plan, fuerza bruta sobre triángulos). Referencia histórica, no se usa. |
| `td/build_network.py` | Construye o actualiza toda la red y los parámetros personalizados. Idempotente (`get_or_create`). Detecta la raíz del repo y usa rutas relativas si el .toe está en ella. |
| `td/accum_ctl.py` | Lógica por frame (§4). Cargado en el Execute DAT con Sync to File. |
| `td/demo_ribbons.py` | Escena demo: Grid → Noise animado → Copy → Attribute (mat/Color) → Merge → salida conectada a `in_mesh`. |
| `tools/` | Harness de pruebas automatizadas (§7). |
| `tests/probe/` | Shaders de sonda con los que se verificó la API de buffers/ray query. |

## 4. `accum_ctl` — qué hace cada frame

1. **Cámara**: escribe las 4 columnas de `cam1.worldTransform` en las uniforms `uCamC0..3`. Motivo: las uniforms
   del GLSL POP solo se resuben cuando TD detecta una dependencia de parámetro; `worldTransform` no la genera y
   la matriz se quedaba congelada (bug real encontrado y reproducido).
2. **Entradas**: por cada conector del contenedor guarda en storage `<nombre_del_In>_on` = 1/0 según haya algo
   conectado. Los Switch internos leen `parent().fetch('in_x_on', 0)` (el storage sí es dependable).
3. **Offline**: sincroniza `project.realTime` con el toggle `Offline`.
4. **Firma de escena**: `str(cam.worldTransform)`, fov, todos los `vec*value*` del POP salvo el índice de sample,
   opcionalmente `mesh_tri.totalCooks` (geometría) y `maps_atlas.totalCooks` (texturas), y `absTime.frame` en
   modo offline. Si la firma cambia → `sample = 0`.
5. **Contador de samples**: avanza solo cuando `trace_pop.totalCooks` cambió desde el frame anterior. Motivo: los
   POPs no cocinan si nadie los consume; contar frames producía medias con n enorme y la imagen se congelaba.
6. **Always Cook**: llama a `out_final.cook()` para que la cadena avance aunque ningún viewer la muestre.

## 5. Kernel (`trace.glsl`) en detalle

- **Píxel**: `id = TDIndex()`, `pix = (id % W, id / W)`; el POP to TOP con `layout = popdim` reproduce exactamente
  ese mapeo. Jitter subpíxel por sample.
- **Rayos de cámara**: `cameraRay` usa fov horizontal (Camera COMP con Viewing Angle Method = Horizontal FOV) y
  la matriz `mat4(uCamC0..3)`.
- **Intersección**: `intersectAnalytic` (piso, demo objects, luz rectangular como quad emisivo) y luego
  `hitMesh` con `rayQueryInitializeEXT(rq, uAS, gl_RayFlagsOpaqueEXT, 0xFF, o, EPS, d, tmax)`. Del triángulo
  `prim` se leen los vértices `3*prim + k` de `mesh_verts` con `TDInVert_VP/VN/Tex/VM/VC(1u, i, 0u)`; el orden coincide porque el
  Collision POP y `mesh_verts` derivan de la misma malla triangulada. Se interpolan normal, uv, color y material.
- **Materiales**: `getMaterial(id)` para analíticos; `applyMeshMaps` aplica `mat` por vértice (0 params, 1 emisivo,
  2 vidrio, 3 cromo), `Color`, y los mapas del atlas (albedo, rough/metal, normal con TBN por triángulo, emit).
- **Luces**: rect light y esfera emisiva se muestrean por área en `directLight` con MIS potencia-2 contra el pdf del
  BSDF; los emisores alcanzados por el BSDF se pesan con `misPower(prevPdfB, pdfLight)`. Las mallas emisivas no
  están en el conjunto NEE y cuentan con peso 1.
- **Vidrio**: Fresnel exacto, reflexión/refracción por ruleta, Beer-Lambert por segmento (`medium`), dispersión
  (canal de longitud de onda elegido en el primer impacto con vidrio: throughput×3 en un canal, IOR por canal),
  iridiscencia de película delgada en el Fresnel y tinte del cuerpo, y `shadowTransmittance` que deja pasar luz
  teñida por el vidrio en los rayos de sombra (cáustica barata).
- **Entorno**: `environment(d)` = color × intensidad × mapa equirectangular (u = atan(x, −z), v = asin(y)), con
  rotación. `Envvisible` decide si la cámara lo ve directamente.
- **Acumulación**: `spp` samples por cook; media progresiva `acc = (nEff·prev + col)/(nEff+1)` con
  `nEff = min(prev.a, Window)` si `Window > 0`. Clamp de radiancia por sample contra fireflies; NaN/Inf a 0.

## 6. Parámetros → uniforms

`build_network.py` declara cada uniform en el POP (`vecNname`, `vecNtype = vec4`) con expresiones a los
parámetros personalizados de `rt`. Mapa: `uCamParams`(fov), `uLightPos/Size/Color`, `uAccum`(sample, bounces,
clamp, NEE), `uEnv`(color, int), `uMat2/3/4`(metal, box, glass), `uEmit`, `uMeshBound`, `uMeshMat`, `uMeshColor`,
`uMeshMaps`, `uMeshMapParams`(normal strength, emit int, tiling), `uRes`, `uGlassFx`, `uCamC0..3`,
`uAccum2`(spp, window), `uScene`(floor, altura, demo, envmap), `uFloor`, `uFloorMat`, `uEnv2`(visible, rotación).
Samplers: `sPrev`, `sAtlas`, `sEnv`. Estructura de aceleración: `uAS`.

## 7. Harness de pruebas (cómo se verificó todo sin tocar la UI)

`tools/RayTest.toe` contiene un Execute DAT (Python, Start = On) que ejecuta `tools/td_boot.py`, el cual ejecuta
`tools/td_job.py` y escribe `tools/td_log.txt`; el job termina con `project.quit(force=True)`.
`tools/run_td.ps1` lanza TD, espera y muestra el log. Un ciclo dura unos 10–20 s. Así se comprobó cada tarea del
plan con valores numéricos (píxeles muestreados, contadores, errores de compilación) y renders guardados.
El .toe del harness se fabricó a mano con `toeexpand`/`toecollapse` (formato de texto de TD); el texto de un DAT
se serializa como `"2\n*\0\0\0" + 4×int32(1) + 0x02 + uint32 big-endian (longitud) + texto`, y el `.parm` debe
llevar `language 0 python`. No abrir `RayTest.toe` a mano: cierra TD al terminar.

## 8. Decisiones y por qué

- **GLSL TOP → GLSL POP**: el plan preveía un BVH propio (LBVH + traversal sin stack). TD 2025 expone ray queries
  por hardware solo en GLSL POP/GLSL Advanced POP, y una sonda demostró que funcionan (t, índice de primitiva,
  baricéntricas, cara). Se migró el kernel y se descartó el BVH: 200k triángulos a ritmo interactivo.
- **Ruta A del plan (buffers de POP)**: el GLSL TOP sí lee atributos con `TDBuffer_X(i)` (página Buffers), y la
  clase vértice tras un Attribute Convert point→vertex entrega la lista de triángulos des-indexada. En el POP se
  lee igual con `TDInVert_X`.
- **Atlas 2×2** en lugar de 4 texturas: el GLSL TOP tiene 3 entradas fijas.
- **Matriz de cámara por columnas + push por frame**: por la ausencia de dependencia de `worldTransform`.
- **Contador por cooks + Always Cook**: por el cook perezoso de los POPs.
- **Ventana temporal** y toggles de reset: para texturas animadas sin reiniciar a 1 sample. La reproyección
  temporal (Fase 5) es la mejora pendiente para geometría en movimiento.
- **Nvidia Denoise TOP** cableado pero apagado: necesita el SDK de NVIDIA; sin él devuelve 128×128 vacío.

## 9. Particularidades de TD 2025 comprobadas empíricamente

- GLSL POP: `attr0name = 'color'` (menú) crea `Color`; `vecNtype` debe ser `vec4`; no declarar uniforms.
- POP to TOP: `rgbamode = 'custom'`, `attribscope = 'Color'`, `layout = 'popdim'`, `format = 'rgba32float'`.
- Las uniforms de matriz del POP (`matrix0value`) no se refrescan al mover la cámara.
- `OP.totalCooks`, `cookFrame`, `cookAbsFrame` existen; `totalCooks` es el indicador fiable de "volvió a cocinar".
- Un COMP conecta entradas de familias distintas (POP y TOP) en un mismo `inputConnectors`; cada conector expone
  `inOP` y `connections`. Conectar desde fuera: `src.outputConnectors[0].connect(comp)` o `.connect(comp.inputConnectors[i])`.
- Movie File Out en modo secuencia requiere `me.fileSuffix` en la expresión de `file` e `imagefiletype` acorde.
- `project.realTime` es el interruptor de realtime. Los Text DATs leen archivos como cp1252: mantener los shaders en ASCII.
- `half` es palabra reservada en GLSL de TD; `sTD2DInputs`/`uTD2DInfos` no existen en el POP (usar samplers propios y `textureSize`).

## 10. Cómo extender

- **Nuevo material analítico**: añade un `MAT_*`, su intersección en `intersectAnalytic` y su rama en `getMaterial`.
- **Nueva uniform**: en `build_network.py` llama a `vec(N, 'uNombre', [expresiones])` y úsala en el shader sin declararla.
- **Más luces NEE**: amplía `numLights`, `sampleLight`, `lightPdfA`.
- **Denoiser propio / reproyección temporal**: el kernel puede escribir atributos extra (normal, profundidad) creando
  más `attrN` en el POP y extrayéndolos con POP to TOPs adicionales; el filtro à-trous iría como GLSL TOP después de `acc`.
- **Múltiples mallas**: hoy hay un Collision POP; merge de POPs con atributos `mat`/`Color` es la vía soportada.
