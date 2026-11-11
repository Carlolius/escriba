# escriba

*[Read in English](README.md)*

[![CI](https://github.com/Carlolius/escriba/actions/workflows/ci.yml/badge.svg)](https://github.com/Carlolius/escriba/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Carlolius/escriba)](https://github.com/Carlolius/escriba/releases)
[![Licencia](https://img.shields.io/badge/licencia-MIT%20%2F%20Apache--2.0-blue)](#licencia)
![Plataformas](https://img.shields.io/badge/plataformas-Windows%20%7C%20Linux-lightgrey)

**Graba tus reuniones, obtén la transcripción y sabe quién dijo qué.**

escriba graba la llamada y tu micrófono, los transcribe en la nube o en tu PC y reconoce a cada persona por la voz. Aprende las voces de cada proyecto a medida que revisas transcripciones, así que cada reunión necesita menos correcciones que la anterior.

![Grabando una reunión](docs/screenshots/es/record.png)

> [!WARNING]
> **Grabar a otras personas tiene consecuencias legales.**
> - **Pide permiso.** Avisa a todos de que grabas antes de empezar. En muchos países es ilegal sin su consentimiento.
> - **Las huellas de voz son datos biométricos.** Para el RGPD son una categoría especial de datos personales. Guarda la biblioteca de voces en privado y borra las muestras de una persona si te lo pide.
> - **El modo nube envía el audio a EE. UU.** (AssemblyAI). Si una reunión no debe salir de tu organización, usa el modo local.
>
> El uso legal de escriba es responsabilidad tuya.

## Funciones

- **Grabación** del audio de la llamada y tu micrófono en un solo archivo, sin programas adicionales.
- **Transcripción** en la nube o sin conexión, con un glosario para nombres y jerga.
- **Identificación de hablantes** por la voz, con una biblioteca de voces por proyecto.
- **Revisión** de cada hablante con frases y audio de muestra, para confirmar o corregir quién es.
- **Archivado** de las reuniones revisadas en Opus, unas 15 veces más pequeñas.
- **Interfaz en el navegador y menú de terminal**, en castellano e inglés, con temas de color (Gruvbox, Tokyo Night, Catppuccin, Dracula, Nord...).

## Nube o local

| | Nube (AssemblyAI) | Local |
|---|---|---|
| Tiempo por hora de audio | unos minutos | ~1 h 15 min en CPU |
| Coste | ~0,23 $ por hora | gratis |
| El audio sale de tu PC | sí | no |
| Instalación adicional | ninguna | ~1,5 GB |

Los hablantes se identifican siempre en tu PC, en los dos modos.

## Instalación

### Windows

Descarga la última versión de [Releases](https://github.com/Carlolius/escriba/releases) (*Source code (zip)*), descomprímela y ejecuta `install.ps1` (clic derecho > *Ejecutar con PowerShell*). Se instala en tu carpeta de usuario, no necesita permisos de administrador y crea un acceso directo *Escriba*.

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1           # nube
powershell -ExecutionPolicy Bypass -File install.ps1 -Local    # nube + local
powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
```

Para actualizar, cierra escriba y ejecuta el `install.ps1` de la versión nueva.

### Linux

Necesita [`uv`](https://docs.astral.sh/uv/) y `libpulse`. Desde la carpeta de la [última versión](https://github.com/Carlolius/escriba/releases):

```bash
uv tool install --python 3.11 "escriba @ file://$PWD"
escriba install-local    # opcional: modo local
```

## Primeros pasos

1. Abre escriba con `escriba web` (o el acceso directo *Escriba*) y pega tu clave de [AssemblyAI](https://www.assemblyai.com) en *Ajustes*.
2. Crea un proyecto y elige la carpeta donde se guardarán sus reuniones.
3. **Graba** la reunión, **transcríbela** y **revisa** quién es cada hablante.

¿Prefieres la terminal? Ejecuta `escriba` para el menú, o `escriba --help` para las órdenes sueltas.

<table>
<tr>
<td><img src="docs/screenshots/es/meetings.png" alt="Reuniones"></td>
<td><img src="docs/screenshots/es/transcribe.png" alt="Transcribir"></td>
</tr>
<tr>
<td><img src="docs/screenshots/es/review.png" alt="Revisar"></td>
<td><img src="docs/screenshots/es/people.png" alt="Personas"></td>
</tr>
</table>

## Modo local

Instálalo desde *Ajustes*, con `escriba install-local` o con `install.ps1 -Local`. Además necesita un [token de Hugging Face](https://hf.co/settings/tokens) con las condiciones de [speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1) y [speaker-diarization-community-1](https://hf.co/pyannote/speaker-diarization-community-1) aceptadas.

> [!NOTE]
> **GPU NVIDIA (experimental).** `escriba install-local --gpu` o `install.ps1 -Gpu` (~5 GB; driver 528+ en Windows, 525+ en Linux) deja el modo local en minutos. Aún no se ha probado en hardware real, y si la GPU falla escriba sigue con la CPU. [Abre un issue](https://github.com/Carlolius/escriba/issues) para contarnos cómo te ha ido.

## Tus datos

Las grabaciones y transcripciones se quedan en la carpeta de cada proyecto. Las bibliotecas de voces, el glosario, las claves y los ajustes se guardan en `%LOCALAPPDATA%\escriba` en Windows y en `~/.local/share/escriba` en Linux. No se envía nada a ningún sitio, salvo el audio que transcribes en modo nube.

## Desarrollo

```bash
uv venv --python 3.11 .venv
uv pip install --torch-backend cpu -e ".[local]" pytest
.venv/bin/python -m pytest
```

Los textos de la interfaz se escriben en inglés dentro de `_()` y se traducen en `escriba/locales/<idioma>.json`. Las huellas de voz usan el codificador de voz de [Resemblyzer](https://github.com/resemble-ai/Resemblyzer) (Apache-2.0), reimplementado en numpy.

## Contribuir

Las incidencias y pull requests son bienvenidas (en inglés). Consulta [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

Con licencia [Apache 2.0](LICENSE-APACHE) o [MIT](LICENSE-MIT), a tu elección.
