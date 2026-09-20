"""Lightweight, modular UI translation (mirrors ``odoo_instance_manager``).

English is the source language: the string in the code is already English, so the
default UI needs no translation. When Spanish is selected, translation happens at
a few display/input chokepoints (see ``ui``/``prompts``) plus ``tf`` for
interpolated messages, so call sites barely change. Any string missing from the
catalog falls back to English, so partial translation degrades gracefully.

The authoring catalog below is kept Spanish→English (one readable source of
truth); the English→Spanish lookup table used at runtime is derived from it.
"""

from __future__ import annotations

_LANG = "en"


def set_language(lang: str) -> None:
    global _LANG
    _LANG = "es" if str(lang).lower().startswith("es") else "en"


def current_language() -> str:
    return _LANG


def t(text: str) -> str:
    """Translate an English UI string to the current language (English → Spanish)."""
    if _LANG == "en":
        return text
    return _ES.get(text, text)


def tf(template: str, *args: object, **kwargs: object) -> str:
    """Translate a message template, then fill its ``{}``/``{name}`` placeholders.

    The English template is the catalog key, so interpolated messages translate
    too — e.g. ``tf("Already exists {}", path)`` looks up ``"Already exists {}"``.
    """
    return t(template).format(*args, **kwargs)


# Authoring catalog (Spanish source → English). Extend by adding entries here;
# ``_ES`` (the runtime English → Spanish table) is derived from it below.
_ES_TO_EN: dict[str, str] = {
    # startup / top-level menu
    "Idioma / Language": "Idioma / Language",
    "Generador de workspaces de desarrollo y migración de Odoo": "Odoo development & migration workspace generator",
    "- Genera y mantiene workspaces de Odoo Community por cliente": "- Generates and maintains per-client Odoo Community workspaces",
    "- Secciones opcionales: provisión del sistema y migración (12→19)": "- Optional sections: system provisioning and migration (12→19)",
    "- Muestra el plan de comandos antes de ejecutar nada": "- Shows the command plan before running anything",
    "\n¿Qué quieres hacer?": "\nWhat do you want to do?",
    "Workspaces (generar / gestionar)": "Workspaces (create / manage)",
    "Provisión del sistema (opcional)": "System provisioning (optional)",
    "Migración (OpenUpgrade 12→19)": "Migration (OpenUpgrade 12→19)",
    "Salir": "Exit",
    "\nSaliendo.": "\nExiting.",
    "\nOperación interrumpida. Volviendo al menú.": "\nOperation interrupted. Returning to the menu.",
    "\nEntrada cerrada. Saliendo.": "\nInput closed. Exiting.",
    "\n[ERROR] La operación no se completó: {}": "\n[ERROR] The operation did not complete: {}",
    # generic menu chrome
    "Volver": "Back",
    "Cancelar": "Cancel",
    "Selecciona opción": "Select an option",
    "Introduce el número de opción.": "Enter the option number.",
    "Opción fuera de rango.": "Option out of range.",
    "Sin selección (0 para cancelar).": "No selection (0 to cancel).",
    "Plan de ejecución": "Execution plan",
    "Comando terminó con código {}.": "Command finished with code {}.",
    # prompt primitives
    "Valor obligatorio.": "Value is required.",
    "Responde 'sí'/'s' o 'no'/'n' (Enter = opción por defecto).": "Answer 'yes'/'y' or 'no'/'n' (Enter = default).",
    "Escribe exactamente": "Type exactly",
    "para confirmar": "to confirm",
    # apply / safety
    "Para aplicar cambios en el sistema ejecuta con privilegios (sudo).": "To apply system changes, run with privileges (sudo).",
    # migration
    "Generar un entorno de migración": "Generate a migration environment",
    "Limpiar un entorno de migración": "Clean a migration environment",
    "Qué entorno": "Which environment",
    "No hay entornos de migración en {}.": "No migration environments found under {}.",
    "¿Eliminar también la caché compartida de clones (.repos)? La usan todos los entornos de migración.": "Also remove the shared clones cache (.repos)? It serves every migration environment.",
    "Esto elimina permanentemente {}.": "This permanently deletes {}.",
    "Cancelado.": "Cancelled.",
    "Entorno de migración eliminado.": "Migration environment removed.",
    "La base de datos PostgreSQL de migración (si existe) no se toca — bórrala con "
    "`dropdb -h 127.0.0.1 -U odoo migration` cuando quieras una ejecución totalmente limpia.":
        "The PostgreSQL migration database (if any) is untouched — drop it with "
        "`dropdb -h 127.0.0.1 -U odoo migration` when you want a fully clean run.",
    "Rol PostgreSQL de desarrollo": "Development PostgreSQL role",
    "Todos los ficheros generados ya están al día.": "Every generated file is already up to date.",
    "Solo se escriben los ficheros que cambian; antes se guarda cada uno existente como <fichero>.bak-<fecha>.": "Only files that change are written; each existing one is kept as <file>.bak-<date> first.",
    "Odoo {} no declara un Python máximo y no se sabe que compile en {}; se recomienda Python {}.": "Odoo {} states no Python maximum and is not known to build on {}; Python {} is recommended.",
    "Rol PostgreSQL no válido: {}": "Invalid PostgreSQL role: {}",
    "Elimina el entorno de migración {}": "Remove migration environment {}",
    "Elimina la caché compartida de clones {}": "Remove shared migration clones {}",
    # preflight
    "Comprobación previa (preflight)": "Preflight check",
    "Fichero de dump origen a verificar (vacío para omitir)": "Source dump file to verify (empty to skip)",
    "Base de datos existente a verificar (vacío para omitir)": "Existing database to verify (empty to skip)",
    "Faltan comprobaciones requeridas (MISSING) — ¿continuar de todos modos?": "Some required checks are MISSING — continue anyway?",
    "Resuelve las comprobaciones MISSING antes de ejecutar la migración.": "Resolve the MISSING checks before running the migration.",
    "Preflight superado.": "Preflight passed.",
    # staging
    "Preparar módulos custom (staging)": "Stage custom modules",
    "La herramienta de staging (odoo-module-migrator) no está instalada. Este plan la instala:": "The staging tool (odoo-module-migrator) is not installed. This plan installs it:",
    "Directorio con tus módulos custom (en la versión origen)": "Directory containing your custom modules (at the source version)",
    "Módulos a preparar (separados por comas, vacío = todos)": "Modules to stage (comma-separated, empty = all)",
    "No es un directorio: {}": "Not a directory: {}",
    "No encontrados en el directorio origen: {}": "Not found in the source directory: {}",
    "No hay módulos que preparar.": "No modules to stage.",
    "Sin clon de OpenUpgrade para {} — la detección de candidatos quedará vacía en esos pasos (genera antes el entorno).": "No OpenUpgrade clone for {} — candidate detection will be empty for those steps (generate the environment first).",
    "Esto reemplaza el código ya preparado de: {}.": "This replaces the already-staged code of: {}.",
    "Informe de staging: {}": "Staging report: {}",
    "El staging es un punto de partida preparado — tu revisión completa la migración.": "Staging is a prepared starting point — your review completes the migration.",
    # --- complete UI coverage (checked by tests/test_i18n.py) ---
    "English": "English",
    "Español": "Español",
    "El path seleccionado para {} no coincide con las extensiones esperadas: {}": "The selected path for {} does not match the expected extensions: {}",
    "¿Usar este fichero de todos modos?": "Use this file anyway?",
    "Selecciona el fichero requerido": "Select required file",
    "(por defecto)": "(default)",
    "Directorio actual": "Current directory",
    "  0) Introducir una ruta manual": "  0) Choose a manual path",
    "  ..) Subir un nivel": "  ..) Up one level",
    "  q) Cancelar": "  q) Cancel",
    "Elige un número, .., q o una ruta manual": "Choose a number, ..,  q, or a manual path",
    "Ruta completa del fichero": "Full file path",
    "Entrada no válida.": "Invalid input.",
    "Odoo {} soporta Python {} — este host usa {}.": "Odoo {} supports Python {} — this host runs {}.",
    "una versión no detectada": "an undetected version",
    "uv no puede proporcionar Python {} en este host — instala uv (provision check lo indica) para usarlo.": "uv cannot provide Python {} on this host — install uv (provision check reports it) to build with it.",
    "Mantener el python3 del host ({})": "Keep the host python3 ({})",
    "Usar Python {} de uv (recomendado)": "Build with uv Python {} (recommended)",
    "Elegir otra versión de Python": "Choose another Python version",
    "Intérprete para Odoo {}": "Interpreter for Odoo {}",
    "Versión de Python (p. ej. 3.10)": "Python version (e.g. 3.10)",
    "Python {} está fuera del rango soportado por Odoo {} (límite: {}).": "Python {} is outside the supported range for Odoo {} (bound: {}).",
    "¿Usarlo de todos modos?": "Use it anyway?",
    "\nWorkspaces": "\nWorkspaces",
    "Crear un workspace": "Create a workspace",
    "Gestionar un workspace existente": "Manage an existing workspace",
    "Nuevo workspace": "New workspace",
    "Nuevo (rápido)": "New (quick)",
    "Desde un fichero de perfil": "From a profile file",
    "Nombre del workspace": "Workspace name",
    "Versiones de Odoo (separadas por comas)": "Odoo versions (comma-separated)",
    "Repositorios OCA (separados por comas, opcional)": "OCA repositories (comma-separated, optional)",
    "Nada que hacer.": "Nothing to do.",
    "El venv de Odoo {} usará Python {}.": "Odoo {} venv will use Python {}.",
    "El workspace {} ya existe — usa gestionar para modificarlo.": "Workspace {} already exists — use manage to modify it.",
    "Workspace {} creado.": "Workspace {} created.",
    "No hay workspace.json en {} — no se puede gestionar.": "No workspace.json in {} — cannot manage it.",
    "No se encontraron workspaces.": "No workspaces found.",
    "Workspaces existentes": "Existing workspaces",
    "Gestionar {}": "Manage {}",
    "Actualizar los ficheros generados": "Refresh generated files",
    "Regenerar un venv": "Regenerate a venv",
    "Actualizar los repos compartidos": "Refresh shared repos",
    "Añadir una versión": "Add a version",
    "¿Qué versión?": "Which version",
    "Esto elimina y reconstruye .venv/odoo{}.": "This removes and rebuilds .venv/odoo{}.",
    "No hay clones presentes que actualizar.": "No present clones to refresh.",
    "Nueva versión de Odoo (p. ej. 19.0)": "New Odoo version (e.g. 19.0)",
    "{} ya está en el workspace.": "{} is already in the workspace.",
    "\nProvisión del sistema": "\nSystem provisioning",
    "Comprobar si el host está listo": "Check host readiness",
    "Aplicar (instalar lo que falte)": "Apply (install what's missing)",
    "Capacidad": "Capability",
    "{} no está soportado — hosts soportados: {}.": "{} is not supported — supported hosts: {}.",
    "¿Instalar rtlcss (con Node.js)? Solo hace falta si los usuarios trabajan en un idioma de derecha a izquierda (árabe, hebreo, persa…)": "Install rtlcss (with Node.js)? Only needed if users work in a right-to-left language (Arabic, Hebrew, Persian…)",
    "El host ya está provisionado — nada que hacer.": "Host already provisioned — nothing to do.",
    "Provisión aplicada.": "Provisioning applied.",
    "\nMigración (OpenUpgrade 12→19)": "\nMigration (OpenUpgrade 12→19)",
    "Versión de Odoo origen (p. ej. 13.0)": "Source Odoo version (e.g. 13.0)",
    "Versión de Odoo destino (p. ej. 18.0)": "Target Odoo version (e.g. 18.0)",
    "fijado por ti": "pinned by you",
    "recomendado": "recommended",
    "Paso": "Step",
    "Intérprete": "Interpreter",
    "Origen": "Source",
    "¿Fijar un paso a una versión concreta de Python?": "Pin a step to a specific Python version?",
    "¿Qué paso?": "Which step",
    "Python para Odoo {}": "Python for Odoo {}",
    "¿Fijarlo de todos modos?": "Pin it anyway?",
    "Cadena de migración: {}": "Migration chain: {}",
    "¿Aplicar este plan ahora?": "Apply this plan now?",
    "Entorno listo. Ejecuta: bash {}/run_migration.sh <dump-origen>": "Environment ready. Run: bash {}/run_migration.sh <source-dump>",
    "Crear el directorio migrations de {} ({})": "Create migrations directory for {} ({})",
    "Estado": "State",
    "Comprobación": "Check",
    "Detalle": "Detail",
    "Escribir {}": "Write {}",
    "Fijar permisos {} en {}": "Set mode {} on {}",
    "Clonar Odoo {} en la caché compartida": "Clone Odoo {} into the shared cache",
    "Clonar OCA {} ({}) en la caché compartida": "Clone OCA {} ({}) into the shared cache",
    "Crear los directorios del workspace {}": "Create workspace directories for {}",
    "Enlazar OCA {} para Odoo {}": "Link OCA {} for Odoo {}",
    "Copia de seguridad de {} en {}": "Back up {} to {}",
    "Crear el directorio de {}": "Create directory for {}",
    "Actualizar las listas de paquetes apt": "Update apt package lists",
    "Instalar las dependencias de compilación de Odoo": "Install Odoo build dependencies",
    "Instalar PostgreSQL": "Install PostgreSQL",
    "Habilitar e iniciar PostgreSQL": "Enable and start PostgreSQL",
    "Crear el rol de desarrollo {} (si falta)": "Create development role {} (if missing)",
    "Confiar en las conexiones loopback de {} para desarrollo local (pg_hba)": "Trust loopback connections of {} for local development (pg_hba)",
    "Recargar PostgreSQL": "Reload PostgreSQL",
    "Asegurar que curl está disponible": "Ensure curl is available",
    "Descargar wkhtmltopdf parcheado ({})": "Download patched wkhtmltopdf ({})",
    "Verificar el SHA-256 de wkhtmltopdf (aborta si no coincide)": "Verify wkhtmltopdf SHA-256 (abort on mismatch)",
    "Instalar el .deb verificado de wkhtmltopdf": "Install verified wkhtmltopdf .deb",
    "Comprobar que el wkhtmltopdf del PATH es el parcheado":
        "Check that the patched wkhtmltopdf is the one on PATH",
    "Eliminar el .deb descargado de wkhtmltopdf": "Remove downloaded wkhtmltopdf .deb",
    "Instalar Node.js y npm": "Install Node.js and npm",
    "Instalar rtlcss globalmente": "Install rtlcss globally",
    "Clonar OpenUpgrade {}": "Clone OpenUpgrade {}",
    "Clonar Odoo {}": "Clone Odoo {}",
    "Crear el directorio de requirements": "Create requirements directory",
    "Crear el venv uv (Python {}) para Odoo {}": "Create uv venv (Python {}) for Odoo {}",
    "Instalar psycopg2-binary y openupgradelib para Odoo {}": "Install psycopg2-binary and openupgradelib for Odoo {}",
    "Marcar el venv de Odoo {} como listo": "Mark Odoo {} venv as ready",
    "Marcar el venv {} como listo": "Mark the venv {} ready",
    "Crear los directorios de migración": "Create migration directories",
    "Crear el venv de la herramienta de staging": "Create the staging tool venv",
    "Instalar odoo-module-migrator": "Install odoo-module-migrator",
    "Crear los directorios de staging de {}": "Create staging directories for {}",
    "Copiar {} etapa {} desde la etapa {}": "Copy {} stage {} from the {} stage",
    "Preparar el worktree git de {} etapa {}": "Prepare the git worktree for {} stage {}",
    "Migrar el código de {} {} -> {}": "Migrate {} code {} -> {}",
    "Actualizar Odoo {}": "Refresh Odoo {}",
    "Actualizar OCA {} ({})": "Refresh OCA {} ({})",
    "Eliminar el venv existente {}": "Remove existing venv {}",
    "Crear el venv {} con uv (Python {})": "Create venv {} with uv (Python {})",
    "Crear el venv {}": "Create venv {}",
    "Actualizar pip/wheel/setuptools en {}": "Upgrade pip/wheel/setuptools in {}",
    "Instalar los requisitos de Odoo {}": "Install Odoo {} requirements",
    # --- egress control and mail capture ---
    'Redirigir el correo de una base de datos a Mailpit': "Redirect a database's mail to Mailpit",
    'Crear el directorio de descarga {}': 'Create download directory {}',
    'Descargar {}': 'Download {}',
    'Verificar el SHA-512 de {} (aborta si no coincide)': 'Verify {} SHA-512 (abort on mismatch)',
    'Instalar OpenSnitch {} sin arrancarlo': 'Install OpenSnitch {} without starting it',
    'Eliminar los paquetes descargados': 'Remove downloaded packages',
    'Endurecer {}': 'Harden {}',
    'Sustituir las reglas propias de OpenSnitch ({}*)': "Replace the tool's own OpenSnitch rules ({}*)",
    'Habilitar y (re)iniciar OpenSnitch': 'Enable and (re)start OpenSnitch',
    'Descargar Mailpit {}': 'Download Mailpit {}',
    'Verificar el SHA-256 de Mailpit (aborta si no coincide)': 'Verify Mailpit SHA-256 (abort on mismatch)',
    'Instalar Mailpit en {}': 'Install Mailpit to {}',
    'Eliminar los ficheros descargados': 'Remove downloaded files',
    'Habilitar y (re)iniciar Mailpit': 'Enable and (re)start Mailpit',
    'Redirigir el correo de la base de datos {} a Mailpit': 'Redirect the mail of database {} to Mailpit',
    '¿Instalar o actualizar el cortafuegos de salida (OpenSnitch)?': 'Install or update the outbound firewall (OpenSnitch)?',
    '¿Instalar o actualizar la captura local de correo (Mailpit)?': 'Install or update the local mail capture (Mailpit)?',
    'Comprobar que {} conecta por loopback': 'Check that {} connects over loopback',
    'Preguntar a PostgreSQL por las reglas que tiene para {}':
        'Ask PostgreSQL to read back the rules for {}',
    'OpenSnitch bloquea toda conexión saliente sin regla y pregunta en su interfaz cuando está abierta. Odoo solo puede llegar a localhost, más DNS en el puerto 53; las herramientas de desarrollo conservan sus destinos. Ver docs/egress-control.md.': 'OpenSnitch blocks every outbound connection without a rule, asking in its UI when it is open. Odoo may reach only localhost, plus DNS on port 53; the development tools keep their hosts. See docs/egress-control.md.',
    'Base de datos cuyo correo redirigir': 'Database whose mail to redirect',
    'Nombre de base de datos no válido: {}': 'Invalid database name: {}',
    'Todos los servidores de correo de {} apuntarán a Mailpit y perderán sus credenciales, y se detiene la recepción de correo. Úsalo solo en copias de ensayo — nunca en una base de datos que vuelve a producción.': 'Every mail server of {} will point at Mailpit and lose its credentials, and mail fetching stops. Use it on rehearsal copies only — never on a database going back to production.',
    'Encender {} (y en cada arranque)': 'Turn on {} (and at every start)',
    'Apagar {} (y mantenerlo apagado tras reiniciar)': 'Turn off {} (and keep it off after a restart)',
    'Eliminar las reglas propias de OpenSnitch ({}*)': "Remove the tool's own OpenSnitch rules ({}*)",
    'Desinstalar OpenSnitch y los paquetes que arrastró': 'Purge OpenSnitch and the packages it pulled in',
    'Eliminar {}': 'Remove {}',
    'Eliminar el correo capturado ({})': 'Remove the captured mail ({})',
    'apt eliminaría {} paquete(s): {}': 'apt would remove {} package(s): {}',
    'Tus propias reglas en {} se conservan.': 'Your own rules in {} are kept.',
    'Esto elimina el cortafuegos de salida.': 'This removes the outbound firewall.',
    'Esto elimina Mailpit y todos los mensajes que capturó.': 'This removes Mailpit and every message it captured.',
    'Hecho.': 'Done.',
    'no instalado': 'not installed',
    'encendido': 'on',
    'apagado': 'off',
    'en ejecución': 'running',
    'NO está en ejecución': 'NOT running',
    'Hay un servicio instalado que no está en ejecución. Revisa `systemctl status`: una unidad que '
    'arranca y muere deja igualmente su paso de instalación informando de éxito.':
        'A service is installed but not running. Check `systemctl status` for it: a unit that '
        'starts and then exits still leaves its install step reporting success.',
    'Componente': 'Component',
    'Versión': 'Version',
    'No hay ninguno instalado — usa Aplicar para instalarlos.': 'Neither is installed — use Apply to install them.',
    '\nCortafuegos de salida y captura de correo': '\nOutbound firewall and mail capture',
    'Cortafuegos de salida y captura de correo (encender/apagar, desinstalar)': 'Outbound firewall and mail capture (on/off, uninstall)',
    'Apagar el cortafuegos de salida': 'Turn the outbound firewall off',
    'Encender el cortafuegos de salida': 'Turn the outbound firewall on',
    'Desinstalar el cortafuegos de salida': 'Uninstall the outbound firewall',
    'Apagar la captura de correo': 'Turn the mail capture off',
    'Encender la captura de correo': 'Turn the mail capture on',
    'Desinstalar la captura de correo': 'Uninstall the mail capture',
    "Descargar los módulos del kernel que usaba": "Unload the kernel modules it used",
    'No hay ningún wkhtmltopdf parcheado y verificado fijado para {} — instálalo a mano (github.com/wkhtmltopdf/packaging) o los informes PDF saldrán degradados.': 'No verified patched wkhtmltopdf is pinned for {} — install it by hand (github.com/wkhtmltopdf/packaging) or PDF reports will be degraded.',
    'No se puede usar el perfil {}: {}': 'Cannot use the profile {}: {}',
    '{} corresponde a otro workspace ({}).': '{} names another workspace ({}).',
    "No es un nombre de módulo de Odoo: {}": "Not an Odoo module name: {}",
}

# Runtime lookup: English (the in-code source) → Spanish.
_ES: dict[str, str] = {english: spanish for spanish, english in _ES_TO_EN.items()}
