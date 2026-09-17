# PLAN — Path tracer en tiempo real para TouchDesigner

Documento de control para una sesión de Claude Code. Pégalo en la raíz del repo y arranca la sesión con: *"Lee PLAN_RAYTRACER_TD.md y ejecuta el PROTOCOLO. No hagas nada más."*

---

## PROTOCOLO — LEER ANTES DE ESCRIBIR UNA SOLA LÍNEA

1. **Gate obligatorio.** No ejecutas ninguna tarea hasta que Jack escriba exactamente `SIGUIENTE TAREA` en mayúsculas. Cualquier otro mensaje se trata como pregunta o corrección, no como permiso para avanzar.
2. **Una tarea por desbloqueo.** Al terminar la tarea actual, PARAS. No encadenas, no adelantas la siguiente "ya que estamos", no preparas archivos futuros.
3. **Cero suposiciones.** Si te falta un dato (versión, ruta, nombre de operador, hardware, formato), haces la pregunta y esperas. Nunca inventes nombres de uniforms, rutas de operadores ni APIs de TouchDesigner. Si no estás seguro de que un uniform o método existe en esta build, lo dices explícitamente y preguntas antes de usarlo.
4. **No refactorices lo que no se te pidió.** No renombres, no reorganices, no "limpies" código de tareas anteriores que ya está validado.
5. **Disciplina de tokens.** No vuelques el archivo completo en el chat. Editas el archivo y describes el cambio en máximo 5 líneas. No leas el repo entero: solo los archivos que la tarea lista.
6. **No puedes ver el render.** Nunca afirmes que algo "funciona" o "se ve bien". Terminas cada tarea con un criterio de verificación que Jack ejecuta en TD.
7. **Si la tarea se desborda** (resulta ser más grande de lo escrito), paras, lo dices, y propones cómo partirla. No la completas por tu cuenta.
8. **Formato de cierre obligatorio de cada tarea:**
   - `CAMBIOS:` archivos tocados, 1 línea cada uno
   - `VERIFICA EN TD:` pasos concretos y qué debería verse
   - `PREGUNTAS:` lo que necesitas de Jack (o "ninguna")
   - `ESPERANDO SIGUIENTE TAREA`

---

## TAREA 0 — INTAKE (no escribe código)

Antes de la Tarea 1, haz estas preguntas en un solo mensaje y espera respuesta. No adivines ninguna.

- Build exacta de TouchDesigner (menú Help → About) y si es Commercial/Pro/Non-Commercial.
- Sistema operativo y GPU (modelo y VRAM). ¿El desarrollo es en Windows, Mac, o ambos? Esto cambia si el compute shader y los formatos 32-bit float son viables igual.
- Resolución y fps objetivo del render final.
- Destino del proyecto: ¿show en vivo, tox reutilizable, material de curso, portafolio? Esto define si hay que empaquetar y parametrizar o no.
- ¿La geometría de la escena será estática, animada, o generada por simulación cada frame?
- ¿Ya está configurada la sincronía Text DAT ↔ archivo en disco para los shaders? Si no, la Tarea 1 la incluye.
- ¿La geometría de la escena va a vivir en POPs o en SOPs? Afecta solo a la Fase 4, pero condiciona cómo se escribe la Tarea 11. Si la respuesta es POPs, confirma que la build es 2025 o posterior.
- Ruta absoluta del repo y del archivo .toe.
- ¿Cuántas horas al día reales tiene Jack para esto?

---

## FASE 1 — BASE TRAZABLE (Día 1)

### TAREA 1 — Andamiaje y sincronía de archivos
Crear estructura `shaders/` con `trace.frag` y un include `common.glsl`. Configurar el GLSL TOP para leer desde Text DAT sincronizado a disco, con reload en caliente. El shader solo pinta `vUV` como color.
**Acepta si:** un gradiente UV en pantalla, y editar el .frag en el editor actualiza TD sin reabrir nada.
**Tiempo:** 45 min.

### TAREA 2 — Generación de rayos desde la cámara de TD
Pasar la matriz de la cámara como uniform (expresión sobre el Camera COMP, no matriz inventada), más fov y aspect. Construir origen y dirección por pixel.
**Acepta si:** pintando `dir*0.5+0.5` como color, orbitar la cámara en TD mueve el patrón de forma coherente.
**Tiempo:** 1 h.

### TAREA 3 — Intersecciones analíticas
`Hit` struct (t, posición, normal, material id). Intersección de plano, esfera y caja. Escena hardcodeada: piso + dos esferas.
**Acepta si:** siluetas correctas al orbitar, sin z-fighting ni acné.
**Tiempo:** 1.5 h.

### TAREA 4 — Luz directa y sombra dura
Un area light rectangular. Un shadow ray por pixel, lambert puro, un solo sample.
**Acepta si:** sombras proyectadas en el piso que se mueven con la luz.
**Tiempo:** 1 h.

---

## FASE 2 — PATH TRACING REAL (Día 2)

### TAREA 5 — RNG y muestreo de hemisferio
Hash por pixel + frame para la semilla. Muestreo coseno-ponderado. Loop de 3 rebotes difusos.
**Acepta si:** imagen ruidosa pero con bounce de color entre superficies (una esfera roja debe teñir el piso).
**Tiempo:** 1.5 h.

### TAREA 6 — Acumulación progresiva
Feedback TOP en **32-bit float RGBA** (no 16-bit, se estanca). Contador de samples. Reset automático al cambiar cámara, luz o cualquier parámetro de escena.
**Acepta si:** con la cámara quieta la imagen converge a limpia en segundos; al mover la cámara se resetea al instante sin arrastrar fantasmas.
**Tiempo:** 2 h. *Aquí es donde más gente se atora — si el reset no dispara, todo lo demás miente.*

### TAREA 7 — GGX: metal y roughness
BRDF microfacetas con Fresnel Schlick. Parámetros metallic y roughness por material.
**Acepta si:** una esfera metálica refleja la escena y el blur del reflejo escala con roughness.
**Tiempo:** 2 h.

---

## FASE 3 — MATERIALES Y LUCES (Día 3)

### TAREA 8 — Dieléctricos / translucidez
Refracción con IOR, reflexión/transmisión por Fresnel, absorción Beer-Lambert dentro del medio.
**Acepta si:** una esfera de vidrio invierte la imagen detrás de ella y tiñe según el grosor.
**Tiempo:** 2 h.

### TAREA 9 — Geometría emisiva como luz + NEE
Materiales con `emit`. Next Event Estimation: muestreo directo de la superficie emisiva, con MIS contra el muestreo del BSDF.
**Acepta si:** una esfera emisiva pequeña ilumina su entorno con ruido bajo. Sin NEE serían miles de samples; con NEE, decenas.
**Tiempo:** 3 h.

### TAREA 10 — Checkpoint y limpieza
Parametrizar lo hardcodeado a Custom Parameters del contenedor. Sin features nuevos.
**Tiempo:** 1.5 h. **Fin del alcance de la semana 1.**

---

## FASE 4 — MALLAS (Semana 2)

### TAREA 11 — Puente geometría → shader

**Antes de escribir código, verifica y repórtale a Jack:** ¿puede el GLSL TOP leer directamente el buffer de un POP (vía SSBO o equivalente), o hay que pasar por textura de todas formas? Revisa la documentación de la clase POP y los OP Snippets. **No inventes un uniform ni un método que no hayas confirmado que existe.** El resultado de esa verificación decide cuál de las dos rutas se implementa:

- **Ruta A — POP directo.** Si el shader puede leer el buffer del POP, se elimina toda la conversión. Es la ruta buena, sobre todo con geometría animada: los POPs son GPU-nativos y existen justamente para matar el roundtrip a CPU.
- **Ruta B — fallback por textura.** SOP to CHOP → CHOP to TOP en 32-bit float, o POP → TOP. Posiciones, normales, uv e índices en texturas separadas, leídas con `texelFetch`.

Sin BVH todavía; fuerza bruta sobre todos los triángulos.
**Acepta si:** una malla de ~5k triángulos traza correctamente a 720p, aunque sea lento. Si la geometría es animada, debe seguir correcta al deformarse.
**Tiempo:** 2 h por la Ruta A, 3–4 h por la Ruta B.

### TAREA 12 — Atributos interpolados y material maps
Coordenadas baricéntricas, normales interpoladas, uv. Sampleo de mapas de albedo, roughness, metal, normal y emit.
**Tiempo:** 3 h.

### TAREA 13 — LBVH: construcción
Morton codes + sort en GPU + construcción de jerarquía en compute shader. **Pregunta a Jack si prefiere construir en Python/numpy primero** (más simple, solo sirve para geometría estática) antes de meterse a la versión GPU.

Nota de alcance: los POPs pueden servir para el cálculo de Morton codes y posiblemente el sort, porque eso sí es una operación por punto. La construcción de la jerarquía **no**: escribe nodos internos que no corresponden a ningún punto de entrada, y eso está fuera del modelo de los POPs. Esa parte es compute shader. No intentes forzarla a una red de nodos.
**Tiempo:** 6–10 h. La tarea más grande del proyecto.

### TAREA 14 — Traversal stackless
Recorrido con skip pointers (nada de stack en fragment shader). Cap de iteraciones para evitar TDR del driver.
**Acepta si:** la misma malla corre 10–50× más rápido que en la Tarea 11, con imagen idéntica.
**Tiempo:** 4–6 h.

---

## FASE 5 — 60 FPS (Semanas 3–4)

### TAREA 15 — Reproyección temporal
Motion vectors desde la matriz de cámara del frame anterior. Acumulación de historia con rechazo por profundidad y normal.
**Tiempo:** 4–6 h.

### TAREA 16 — Denoise espacial à-trous
Filtro edge-avoiding guiado por normal, profundidad y varianza. Esto es lo que convierte 1–2 spp en imagen presentable a 60fps.
**Tiempo:** 6–8 h. Espera iterar el ghosting a ojo varias veces.

### TAREA 17 — Perf, seguridad y empaque
Caps de iteración, presupuesto de tiempo por frame, degradado de calidad al mover la cámara, empaque como .tox con parámetros.
**Tiempo:** 4 h.

---

## MEJORAS OPCIONALES (no entran al plan base)

- HDRI de entorno con muestreo por CDF de luminancia.
- Blue noise / secuencias de Sobol en vez de hash blanco: menos ruido perceptual al mismo spp.
- Depth of field y motion blur (casi gratis en un path tracer).
- Volumétricos con T3D o densidad propia.
- Reactividad de audio a emisión y roughness — el argumento comercial real en vivo.

---

## TIEMPO TOTAL

| Bloque | Horas | Calendario realista |
|---|---|---|
| Fases 1–3 (demo analítica completa) | 16–18 h | 1 semana |
| Fase 4 (mallas + BVH) | 16–22 h | +1.5 semanas |
| Fase 5 (60 fps denoised) | 14–18 h | +1.5 semanas |
| **Total a producto** | **46–58 h** | **4 semanas a medio tiempo** |

Sumar 20–30% si el desarrollo es en Mac o si la geometría es animada desde el día 1.

Restar 1–2 h de la Fase 4 si la Ruta A de la Tarea 11 resulta viable.

---

## NOTA SOBRE POPs

El trace, el BVH y el denoiser **no** son territorio de POPs: el trace es un kernel por pixel con acceso aleatorio a toda la escena, y el denoiser es dominio de imagen (TOPs). Los POPs entran en la preparación de geometría — generación procedural, normales, empaquetado de atributos — y en el puente de la Tarea 11. Que exista un Script POP no cambia esto: corre Python en el cook thread, así que nunca metas ahí nada pesado.
