# Paper Downloader

**Descarga los PDF de texto completo de toda una bibliografía de una sola vez, usando el acceso de tu universidad.**
Carga un archivo `.bib` o `.nbib` de PubMed, inicia sesión en tu institución una vez y la app descarga todos los artículos que pueda desde
ScienceDirect, PubMed, Scopus, Web of Science, IEEE Xplore y cualquier editorial accesible por DOI.

[Read in English](README.md)

![Paper Downloader](docs/main_app.png)

![La cola de descargas muestra el estado de cada referencia: descargada, pendiente o fallida.](docs/main_page.png)
*La cola de descargas muestra el estado de cada referencia: descargada, pendiente o fallida.*

## Qué hace

- **Lee tus archivos de referencias.** Sube un `.bib` (BibTeX) o un `.nbib` (PubMed/MEDLINE); todas las bases de datos pueden exportar alguno de los dos. Otros formatos no se aceptan.
- **Agrupa las referencias por base de datos** (Web of Science, Scopus, PubMed, ScienceDirect, IEEE...).
- **Usa tu acceso institucional.** Tú inicias sesión, en un navegador privado que controla la app; la app nunca ve ni guarda tus contraseñas.
- **Verifica el acceso antes de descargar.** Una prueba con un artículo por editorial detecta captchas y falta de acceso desde el principio, en vez de fallar a la mitad de 200 papers.
- **Descarga con calma.** Pausas entre papers y un límite compartido por editorial protegen la IP de tu institución de bloqueos.
- **Reintenta los fallos** con un clic, sin tocar lo que ya se descargó.
- **Multiusuario.** Varias personas pueden usar una misma instalación a la vez, cada una con su navegador, sesión y descargas.
- **Resultados en un clic.** Descarga todo en un `.zip`, o solo las filas que selecciones.

## Inicio rápido (no hace falta saber programar)

Solo necesitas un computador con internet, unos **8 GB de RAM** y **5 GB de espacio libre**.

### 1. Obtén el proyecto

En GitHub pulsa el botón verde **Code** → **Download ZIP** y descomprime el archivo donde quieras.
(Si conoces Git: `git clone https://github.com/aavzpy2023/paperdownload.git`.)

### 2. Arráncalo

| Tu computador | Qué hacer |
|---|---|
| **Windows 10/11** | Abre la carpeta descomprimida y **haz doble clic en `start.bat`**. |
| **macOS** | Abre la app **Terminal**, escribe `cd ` (con un espacio), arrastra la carpeta descomprimida a la ventana, pulsa Enter y ejecuta `./start.sh`. |
| **Linux** | Abre una terminal en la carpeta descomprimida y ejecuta `./start.sh`. |

El script hace todo por ti:

1. Comprueba si **Docker** está instalado y te ofrece instalarlo si no lo está
   (Docker Desktop con `winget` en Windows, Homebrew en macOS, el script oficial de Docker en Linux).
2. Inicia Docker si no está corriendo.
3. Construye y arranca la app. **La primera vez tarda de 5 a 10 minutos** (descarga Chrome y las herramientas).
4. Crea una contraseña de administrador privada, te la muestra y **abre la app en tu navegador**.

> **Windows:** si acabas de instalar Docker Desktop, Windows puede pedirte reiniciar. Después de reiniciar, abre Docker Desktop una vez y
> vuelve a hacer doble clic en `start.bat`.

La app queda disponible en **<http://localhost:81>** mientras Docker esté corriendo.

### ¿Prefieres hacerlo a mano?

1. Instala Docker: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS) o [Docker Engine](https://docs.docker.com/engine/install/) (Linux).
   Ambos incluyen Compose.
2. En la carpeta del proyecto ejecuta:

   ```bash
   docker compose up -d --build
   ```

3. Abre <http://localhost:81> e ingresa con `admin` / `admin`; luego **cambia esa contraseña** en *Users*.
   (`start.sh` / `start.bat` generan una aleatoria y la guardan en un archivo `.env`.)

## Cómo usarla

1. **Inicia sesión** con el usuario y la contraseña de arriba.
2. *(Opcional)* En **Settings**, pega la dirección de la página de acceso de tu biblioteca o institución. Las bases de datos también tienen su propia
   opción "Sign in via your institution", así que esto es solo un atajo.
3. **Sube tu archivo `.bib` o `.nbib`.** La app muestra una tarjeta por cada base de datos encontrada.
4. En cada base de datos, pulsa **Open articles**. Aparece un navegador remoto con uno de tus artículos por editorial.
   Inicia sesión con tu institución y resuelve cualquier casilla de "no soy un robot".
5. Pulsa **Verify access**. La app prueba cada editorial y la tarjeta pasa a **Auth Ready** cuando todo está bien.
   Mientras tanto, **Download** queda desactivado a propósito.
6. Pulsa **Download** en una tarjeta, o marca filas en la tabla y pulsa **Download selected**.
   **Pause** se detiene tras el paper actual; al volver a pulsar Download continúa donde quedó.
7. Si algunos papers fallan, la tarjeta indica cuántos y su botón pasa a **Retry**; **Retry failed** en la tabla los reintenta todos.
8. Pulsa **Download All PDFs (.zip)** para guardar todo en tu computador.

Consejos:

- Algunas editoriales muestran un captcha la primera vez. Es un solo clic y luego se recuerda.
- Web of Science se usa solo para listar tus referencias. Los PDF se descargan directo de cada editorial por DOI,
  lo que evita el captcha de imágenes de Web of Science.
- Las entradas sin DOI no se pueden obtener desde una editorial y quedan marcadas como fallidas.

## Roles

| Rol | Perfil del navegador | Puede gestionar usuarios |
|---|---|---|
| `admin` | Se guarda entre visitas (sigue con sesión en las editoriales) | Sí |
| `user` | Se guarda entre visitas | No |
| `guest` | Temporal: se borra, junto con sus descargas, al cerrar sesión o tras 30 minutos de inactividad | No |

## Privacidad y seguridad

- **Las contraseñas de tu institución y de las editoriales nunca se guardan.** El administrador de contraseñas de Chrome está desactivado; solo la sesión
  de acceso (cookies) permanece en el perfil de las cuentas `admin` y `user`. Los invitados no conservan nada.
- Las contraseñas propias de la app se guardan cifradas (hash).
- Solo está abierto el puerto **81**. El backend y los navegadores remotos viven en una red privada de Docker, y la pantalla remota solo se
  muestra mientras verificas el acceso, a usuarios con sesión iniciada.
- La app usa HTTP simple. **No la expongas directamente a internet**; úsala en tu propio computador, detrás de una VPN o
  detrás de un proxy inverso con HTTPS.
- Respeta los términos de uso de cada editorial y la política de tu institución. La app descarga a ritmo humano a propósito.

## Comandos del día a día

Ejecútalos en la carpeta del proyecto.

| Tarea | Comando |
|---|---|
| Volver a arrancar | `docker compose up -d` (o el script de inicio) |
| Detener | `docker compose down` |
| Ver los registros | `docker compose logs -f` |
| Actualizar tras traer código nuevo | `docker compose up -d --build` |
| **Borrar todo, incluidos usuarios y descargas** | `docker compose down -v` |

Tus usuarios, perfiles de navegador y PDF descargados viven en volúmenes de Docker (`pd_data`, `pd_downloads`) y sobreviven a reinicios y actualizaciones.

## Configuración

Defínelas en un archivo `.env` junto a `docker-compose.yml` (el script de inicio lo crea):

| Variable | Valor por defecto | Significado |
|---|---|---|
| `PD_ADMIN_USER` | `admin` | Primer administrador, se crea solo si la base de datos está vacía |
| `PD_ADMIN_PASSWORD` | `admin` | Su contraseña |
| `PD_MAX_SESSIONS` | `6` | Personas que pueden tener un navegador activo a la vez (unos 1 GB de RAM cada una) |
| `PD_START_URL` | *(vacío)* | Página institucional por defecto para quien no haya puesto la suya |
| `PD_SECRET_KEY` | *(generada)* | Clave que firma las sesiones de acceso |

Para usar otro puerto, cambia `"81:81"` en `docker-compose.yml`, por ejemplo `"8081:81"`.

## Solución de problemas

| Problema | Qué hacer |
|---|---|
| *"Docker is not running"* | Abre Docker Desktop (Windows/macOS) o ejecuta `sudo systemctl start docker` (Linux) y vuelve a correr el script de inicio. |
| Windows: Docker Desktop no inicia | Activa la virtualización en la BIOS/UEFI y verifica que WSL 2 esté instalado (`wsl --install` en una terminal de administrador); luego reinicia. |
| *"port is already allocated"* en el 81 | Otro programa usa el puerto 81. Cambia el puerto como se indica arriba. |
| El navegador remoto muestra *"Failed to connect"* | Pulsa **Reconnect**. Chrome puede tardar un minuto en iniciar en un computador ocupado. |
| Una base de datos pide captcha una y otra vez | Resuélvelo en el navegador remoto y pulsa **Verify access** de nuevo. Tras un captcha *durante* una descarga, la editorial queda en pausa 10 minutos para todos. |
| *"Too many active browser sessions"* | Se alcanzó el límite. Espera a que alguien cierre sesión o sube `PD_MAX_SESSIONS`. |
| *"Only .bib and .nbib files are accepted"* | Exporta tus referencias como BibTeX o PubMed (`.nbib`) desde la base de datos y sube ese archivo. |
| El primer arranque es lento o no logra descargar | Necesita internet para obtener Chrome. Revisa tu conexión o proxy y vuelve a correr el script de inicio. |
| Macs con Apple Silicon (M1–M4) | Funciona, pero Chrome corre emulado y es bastante más lento, porque Google no ofrece una versión de Linux para ARM. |

## Para desarrolladores

```bash
uv run pytest -q                            # pruebas del backend
cd frontend && npm install && npm run dev   # interfaz con recarga en vivo; redirige /api a :8000
```

Estructura: `paper_downloader/` (backend FastAPI, un módulo por base de datos y el ejecutor de descargas), `frontend/` (React + Vite + Tailwind),
`nginx/` (sirve la interfaz y protege la pantalla remota), `backend/` (Dockerfile), `tests/`.

Los selectores están en `paper_downloader/sciencedirect.py`, `ebsco.py`, `pubmed.py` y `publisher.py`; es lo primero que hay que
ajustar cuando un sitio cambia sus páginas.

## Licencia

Ver [LICENSE](LICENSE).
