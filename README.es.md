# escriba

*[Read in English](README.md)*

Graba, transcribe e identifica quién habla en tus reuniones, en Windows y Linux.

- **Grabar:** mezcla lo que suena en el PC (la gente de la llamada) con tu micrófono en un WAV mono de 16 kHz. WASAPI en Windows, PipeWire/PulseAudio en Linux. No hace falta ffmpeg.
- **Transcribir:** en la nube con AssemblyAI (unos minutos, ~0,23 $ por hora de audio) o en tu PC con faster-whisper + pyannote (gratis, pero ~1 h 15 min por hora de audio sin tarjeta NVIDIA).
- **Identificar hablantes:** por la voz, contra una librería de voces de cada proyecto que aprende cada vez que revisas una transcripción. Siempre se hace en tu PC, también en modo nube.
- **Archivar:** cuando una reunión está revisada, su WAV se comprime a Opus (~15 veces menos).

Tiene interfaz en el navegador y menú en la terminal, los dos en **castellano e inglés**. Sigue el idioma del sistema; se cambia en *Ajustes*, en el menú de la terminal o con `escriba --lang es|en`.

## Antes de grabar a nadie

Grabar una reunión y guardar huellas de voz de quienes participan tiene implicaciones legales y éticas:

- **Avisa a todos** de que grabas antes de empezar, y para si alguien no quiere. En muchos países necesitas su consentimiento.
- **Las huellas de voz son datos biométricos.** En la UE, una voz identificable es un dato personal según el RGPD, y las huellas de voz que sirven para identificar a alguien son una categoría especial. Guarda la librería de voces en privado, no la compartas y borra las muestras de una persona si te lo pide.
- **El modo nube saca el audio de tu PC** hacia AssemblyAI (EE. UU.). escriba borra de AssemblyAI la transcripción y el audio subido en cuanto tiene el resultado, pero si la reunión no puede salir de tu organización, usa el modo local.

Eres responsable de usar escriba de forma legal allí donde estés.

## Instalar en Windows

Descarga este repositorio (o el .zip, descomprimido) y haz clic derecho en `install.ps1` > **Ejecutar con PowerShell**. O, desde PowerShell en esa carpeta:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1           # solo nube
powershell -ExecutionPolicy Bypass -File install.ps1 -Local    # nube + local
```

Qué hace, paso a paso:

1. **Instala [`uv`](https://docs.astral.sh/uv/)** si no está, con su instalador oficial. uv es un gestor de Python: descarga la versión de Python que necesita escriba sin tocar ningún otro Python que tengas.
2. **Instala escriba** con `uv tool install`, en un entorno propio dentro de tu carpeta de usuario (sin permisos de administrador): Python 3.11 y todas las librerías, incluidas las de audio, torch para las huellas de voz (~200 MB) y la interfaz web. Con `-Local`, también faster-whisper y pyannote (varios GB más).
3. **Crea el acceso directo "Escriba"** en el escritorio y en el menú Inicio. Abre una ventana negra (déjala abierta mientras uses escriba; al cerrarla se cierra) y el navegador con la aplicación. Si escriba ya está en marcha, solo abre el navegador.

Después:
- **La primera vez:** ve a *Ajustes* y pega tu clave de AssemblyAI. Se guarda en `%LOCALAPPDATA%\escriba\secrets.env`.
- **Si el micrófono no graba nada:** Configuración de Windows > Privacidad y seguridad > Micrófono > "Permitir que las aplicaciones de escritorio accedan al micrófono".
- **Actualizar:** vuelve a ejecutar el script.
- **Desinstalar:** `install.ps1 -Uninstall`. Quita el programa y los accesos directos; tus datos (voces, glosario, claves) se quedan en `%LOCALAPPDATA%\escriba`.

El script no necesita git: si no está junto al código, descarga el .zip del repositorio desde GitHub (`-Source` para indicar otra carpeta o URL). Si Windows está en castellano, sus mensajes también.

Dos detalles propios de Windows de los que se encarga:
- **`webrtcvad`:** resemblyzer pide `webrtcvad`, que en Windows hay que compilar. En su lugar se instala `webrtcvad-wheels`: el mismo módulo, ya compilado.
- **Leer el audio en local:** pyannote recibe el audio ya cargado; leer los archivos por su cuenta necesitaría las DLL de FFmpeg.

## Instalar en Linux

Necesita [`uv`](https://docs.astral.sh/uv/) y `libpulse` (viene con PipeWire y PulseAudio).

```bash
uv tool install --python 3.11 "escriba @ file://$PWD"            # solo nube
uv tool install --python 3.11 "escriba[local] @ file://$PWD"     # nube + local
```

En Linux, el torch de PyPI trae soporte NVIDIA (~2 GB) aunque no lo uses. Para la versión solo CPU, instálalo en un entorno virtual:

```bash
uv venv --python 3.11 .venv
uv pip install --torch-backend cpu -e ".[local]"
```

## Uso

```bash
escriba web        # interfaz en el navegador
escriba            # menú en la terminal
escriba --help     # órdenes sueltas: record, transcribe, archive, enroll, repair, data
```

La web y el menú de la terminal hacen lo mismo y se pueden usar a la vez. La web solo escucha en tu propio PC (`127.0.0.1:8765`), así que nadie de tu red puede entrar. Cerrar el navegador no para una grabación ni una transcripción; cerrar la ventana de la terminal sí para la grabación.

Cada orden tiene su propia ayuda, p. ej. `escriba transcribe --help`. Los nombres de las órdenes están en inglés en los dos idiomas; la ayuda sale en el tuyo.

En la web, el proyecto con el que trabajas se elige en la barra de arriba (escribe un nombre nuevo para crearlo); todas las páginas muestran ese proyecto. *Reuniones* lista lo grabado en su carpeta, con su estado, un reproductor y la transcripción, y permite borrar una reunión (por ejemplo una prueba) con sus archivos y, si quieres, las muestras de voz que salieron de ella. *Transcribir* muestra paso a paso las transcripciones en marcha de todos los proyectos.

Las transcripciones en segundo plano siguen aunque cierres el menú o el navegador, y su progreso (fase, %, tiempo que queda) sale arriba del menú principal y en la página *Transcribir*. Las transcripciones con hablantes por revisar aparecen en *Revisar*, con unas frases de cada uno para saber quién es sin tener que escuchar.

## Tus datos

Las grabaciones y transcripciones se quedan en las carpetas que elijas para cada proyecto. Todo lo demás vive en tu carpeta de datos (`escriba data` te la dice):

| Sistema | Carpeta |
|---|---|
| Windows | `%LOCALAPPDATA%\escriba` |
| Linux | `~/.local/share/escriba` |

Dentro:
- `voiceprints/<proyecto>.json`: huellas de voz de personas reales (ver arriba). No las compartas.
- `glossary.txt`: nombres y términos de tus reuniones; mejora la transcripción en los dos modos.
- `secrets.env`: claves, una por línea (`ASSEMBLYAI_API_KEY=...`, `HF_TOKEN=...`). Una variable de entorno con el mismo nombre tiene prioridad. Si ya guardas tus claves en otro `.env`, `secrets.env` puede ser un enlace a él: guardar una clave solo cambia su línea.
- `state.json`: últimos proyectos y carpetas, transcripciones en marcha, dispositivos preferidos, tema e idioma.

Si mueves reuniones a otra carpeta, sus muestras de voz ya no se pueden escuchar. *Reparar rutas* (en *Personas*, o `escriba repair`) las vuelve a encontrar por el nombre del archivo.

## Modo nube (AssemblyAI)

Crea una cuenta en assemblyai.com (las cuentas nuevas traen 50 $ de crédito) y pega la clave en *Ajustes*.

escriba sube una copia en Opus del audio, pasa tu glosario como términos clave y, al acabar, borra la transcripción de AssemblyAI (allí no se queda ni el audio ni el texto). La transcripción y la separación de hablantes se hacen allí; quién es quién se decide en tu PC contra tu librería.

Probado con 3 reuniones reales: más completo y con mejores nombres propios que `medium` en local. Con idioma "auto", una reunión que mezcla gallego y castellano sale en castellano; con "gl" respeta la mezcla, pero en una prueba juntó a dos personas en un solo hablante.

## Modo local (faster-whisper + pyannote)

Instala con `-Local` (Windows) o el extra `local` (Linux) y, una sola vez:

1. Crea un token en https://hf.co/settings/tokens
2. Acepta las condiciones en https://hf.co/pyannote/speaker-diarization-3.1 y https://hf.co/pyannote/speaker-diarization-community-1
3. Pega el token en *Ajustes* (`HF_TOKEN`)

Siempre funciona con prioridad baja, así que el PC sigue fluido mientras trabaja.

### Rendimiento (Ryzen 5 5625U, solo CPU)

Medido con 5 minutos de una reunión real (oct 2026):

| Paso | Tiempo |
|---|---|
| Transcripción, `medium` (por defecto) | ~114 s |
| Transcripción, `turbo` | ~93 s |
| Separación de hablantes (pyannote 3.1) | ~250 s |

`turbo` (large-v3-turbo) acierta más palabras sueltas, pero en las pruebas se saltó una frase entera, se inventó un "Gracias." final y pasó una reunión en gallego a castellano. Por eso `medium` sigue siendo el de por defecto.

La separación de hablantes es el cuello de botella: casi todo su tiempo se va en las huellas de voz. Espaciar sus ventanas (`segmentation.step`) la hace hasta 5 veces más rápida, pero acaba juntando a dos personas en una, así que se deja como está. Transcribir y separar hablantes en paralelo solo gana un 4% y satura la CPU.

## Identificación por voz

Cada proyecto (cliente, equipo...) tiene su propia librería de voces, que se crea al crear el proyecto. Al revisar los hablantes de una transcripción, confirmar o corregir un nombre añade esa muestra a la persona; "No lo sé" no toca la librería.

En *Personas* puedes escuchar, mover o borrar muestras, cambiar el nombre de una persona (también en las transcripciones del proyecto; si el nombre nuevo ya existe, se juntan), borrar a una persona, deshacer el último cambio, añadir una muestra a mano, reparar rutas y auditar la librería (avisa de muestras demasiado parecidas entre dos personas, de casi duplicadas y de muestras de la misma persona que no se parecen entre sí).

## Desarrollo

El código, los comentarios y los nombres están en inglés; ver la sección *Development* del [README en inglés](README.md), con la tabla de módulos y cómo añadir traducciones.

## Licencia

Con licencia [Apache 2.0](LICENSE-APACHE) o [MIT](LICENSE-MIT), a tu elección.

Salvo que digas expresamente lo contrario, cualquier contribución que envíes para incluirla en escriba, tal como la define la licencia Apache-2.0, tendrá esta misma doble licencia, sin condiciones adicionales.
