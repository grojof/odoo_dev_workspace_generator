"""Lightweight, modular UI translation (mirrors ``odoo_instance_manager``).

English is the source language: the string in the code is already English, so the
default UI needs no translation. When Spanish is selected, translation happens at
a few display/input chokepoints (see ``ui``/``prompts``) plus ``tf`` for
interpolated messages, so call sites barely change. Any string missing from the
catalog falls back to English, so partial translation degrades gracefully.

The catalog below is authored English→Spanish — the same direction it is read —
so an entry is looked up by exactly the literal that appears in the code.
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


# The catalog: the English string in the code → its Spanish. English is the
# source language, so this is authored in the same direction it is looked up —
# an inverted catalog would silently merge two English strings whose Spanish
# happened to match.
_ES: dict[str, str] = {
    # startup / top-level menu
    "Idioma / Language": "Idioma / Language",
    "Odoo development & migration workspace generator":
        "Generador de workspaces de desarrollo y migración de Odoo",
    "- Generates and maintains per-client Odoo Community workspaces":
        "- Genera y mantiene workspaces de Odoo Community por cliente",
    "- Optional sections: system provisioning and migration (12→19)":
        "- Secciones opcionales: provisión del sistema y migración (12→19)",
    "- Shows the command plan before running anything":
        "- Muestra el plan de comandos antes de ejecutar nada",
    "\nWhat do you want to do?": "\n¿Qué quieres hacer?",
    "Workspaces (create / manage)": "Workspaces (crear / gestionar)",
    "System provisioning (optional)": "Provisión del sistema (opcional)",
    "Migration (OpenUpgrade 12→19)": "Migración (OpenUpgrade 12→19)",
    "Exit": "Salir",
    "\nExiting.": "\nSaliendo.",
    "\nOperation interrupted. Returning to the menu.":
        "\nOperación interrumpida. Volviendo al menú.",
    "\nInput closed. Exiting.": "\nEntrada cerrada. Saliendo.",
    "\n[ERROR] The operation did not complete: {}": "\n[ERROR] La operación no se completó: {}",
    # generic menu chrome
    "Back": "Volver",
    "Cancel": "Cancelar",
    "Select an option": "Selecciona una opción",
    "Enter the option number.": "Introduce el número de opción.",
    "Option out of range.": "Opción fuera de rango.",
    "No selection (0 to cancel).": "Sin selección (0 para cancelar).",
    "Execution plan": "Plan de ejecución",
    "Command finished with code {}.": "El comando terminó con código {}.",
    # prompt primitives
    "Value is required.": "Valor obligatorio.",
    "Answer 'yes'/'y' or 'no'/'n' (Enter = default).":
        "Responde 'sí'/'s' o 'no'/'n' (Enter = opción por defecto).",
    "Type exactly": "Escribe exactamente",
    "to confirm": "para confirmar",
    # apply / safety
    "To apply system changes, run with privileges (sudo).":
        "Para aplicar cambios en el sistema, ejecútalo con privilegios (sudo).",
    # migration
    "Generate a migration environment": "Generar un entorno de migración",
    "Clean a migration environment": "Limpiar un entorno de migración",
    "Which environment": "¿Qué entorno?",
    "No migration environments found under {}.": "No hay entornos de migración en {}.",
    "Also remove the shared clones cache (.repos)? It serves every migration environment.":
        "¿Eliminar también la caché compartida de clones (.repos)? La usan todos los entornos de migración.",
    "This permanently deletes {}.": "Esto elimina permanentemente {}.",
    "This permanently deletes {}, including the staged modules: {}.":
        "Esto elimina permanentemente {}, incluidos los módulos preparados (staging): {}.",
    "Cancelled.": "Cancelado.",
    "Migration environment removed.": "Entorno de migración eliminado.",
    "The PostgreSQL migration database (if any) is untouched — drop it with "
        "`dropdb -h 127.0.0.1 -U odoo {}` when you want a fully clean run.":
        "La base de datos PostgreSQL de migración (si existe) no se toca — bórrala con "
    "`dropdb -h 127.0.0.1 -U odoo {}` cuando quieras una ejecución totalmente limpia.",
    "Development PostgreSQL role": "Rol PostgreSQL de desarrollo",
    "Every generated file is already up to date.": "Todos los ficheros generados ya están al día.",
    "Only files that change are written; each existing one is kept as <file>.bak-<date> first.":
        "Solo se escriben los ficheros que cambian; antes se guarda cada uno existente como <fichero>.bak-<fecha>.",
    "Odoo {} states no Python maximum and is not known to build on {}; Python {} is recommended.":
        "Odoo {} no declara un Python máximo y no se sabe que compile en {}; se recomienda Python {}.",
    "Invalid PostgreSQL role: {}": "Rol PostgreSQL no válido: {}",
    "Remove migration environment {}": "Eliminar el entorno de migración {}",
    "Remove shared migration clones {}": "Eliminar la caché compartida de clones de migración {}",
    # preflight
    "Preflight check": "Comprobación previa (preflight)",
    "Source dump file to verify (empty to skip)":
        "Fichero de dump origen a verificar (vacío para omitir)",
    "Existing database to verify (empty to skip)":
        "Base de datos existente a verificar (vacío para omitir)",
    "Some required checks are MISSING — continue anyway?":
        "Faltan comprobaciones requeridas (MISSING) — ¿continuar de todos modos?",
    "Resolve the MISSING checks before running the migration.":
        "Resuelve las comprobaciones MISSING antes de ejecutar la migración.",
    "Preflight passed.": "Preflight superado.",
    # staging
    "Stage custom modules": "Preparar módulos custom (staging)",
    "Promote reviewed modules": "Promover módulos revisados",
    "Report on the runs so far": "Informe de las ejecuciones hasta ahora",
    "Create {}": "Crear {}",
    "Report written: {}": "Informe escrito: {}",
    "No run recorded yet in {} — the driver writes one line per event as it goes.":
        "Todavía no hay ninguna ejecución registrada en {} — el driver escribe una línea por evento según avanza.",
    "Step {} failed": "El paso {} falló",
    "exit {} — see {}": "salida {} — ver {}",
    "Step {} never finished": "El paso {} nunca terminó",
    "started {} and recorded no outcome": "empezó {} y no registró resultado",
    "Step {} passed with {} error line(s)": "El paso {} pasó con {} línea(s) de error",
    "first: {}": "la primera: {}",
    "{} step(s) never ran in this run": "{} paso(s) no se ejecutaron en esta pasada",
    "Decided ({})": "Decidido ({})",
    "OCA repositories this chain needs (comma-separated, optional)":
        "Repositorios de OCA que necesita esta cadena (separados por comas, opcional)",
    "Invalid OCA repository name(s): {}.": "Nombre(s) de repositorio OCA no válido(s): {}.",
    "OpenUpgrade now declares {} as its successor":
        "OpenUpgrade ahora declara {} como su sucesor",
    "{}: {}{}": "{}: {}{}",
    "Decision no longer holds ({})": "La decisión ya no se sostiene ({})",
    "{} was decided {} — {}": "{} se decidió como {} — {}",
    "File recording what you decided about modules with no successor (empty to skip)":
        "Fichero con lo que decidiste sobre módulos sin sucesor (vacío para omitir)",
    "the module now resolves in this step's sources":
        "el módulo ahora se resuelve en las fuentes de este paso",
    "A location for reviewed modules is required.":
        "Hace falta una ubicación para los módulos revisados.",
    "{} is inside the migration environments ({}), which cleaning deletes. "
    "Choose a location outside it.":
        "{} está dentro de los entornos de migración ({}), que la limpieza borra. Elige una ubicación fuera.",
    "Promote {} {} to {}": "Promover {} {} a {}",
    "Take {} stage {} from the promoted copy":
        "Tomar {} en el paso {} de la copia promovida",
    "Directory holding your reviewed modules, one subdirectory per version (empty = none)":
        "Directorio con tus módulos revisados, un subdirectorio por versión (vacío = ninguno)",
    "Which module": "¿Qué módulo?",
    "No staged modules in this environment.": "No hay módulos preparados en este entorno.",
    "Environment vs promoted": "Entorno vs promovido",
    "This replaces the promoted code of {} for: {}.":
        "Esto reemplaza el código promovido de {} para: {}.",
    "Promoted {} for: {}.": "Promovido {} para: {}.",
    "The promoted copy is yours: commit it on the branch for that version if you keep it in git. "
    "The throwaway repository inside each stage directory is not that history.":
        "La copia promovida es tuya: haz commit en la rama de esa versión si la llevas en git. El repositorio desechable que hay dentro de cada directorio de preparación no es ese histórico.",
    "same": "igual",
    "diverged": "divergen",
    "not promoted": "sin promover",
    "only promoted": "solo promovido",
    "The staging tool (odoo-module-migrator) is not installed. This plan installs it:":
        "La herramienta de staging (odoo-module-migrator) no está instalada. Este plan la instala:",
    "Directory containing your custom modules (at the source version)":
        "Directorio con tus módulos custom (en la versión origen)",
    "Modules to stage (comma-separated, empty = all)":
        "Módulos a preparar (separados por comas, vacío = todos)",
    "Not a directory: {}": "No es un directorio: {}",
    "Not found in the source directory: {}": "No están en el directorio origen: {}",
    "No modules to stage.": "No hay módulos que preparar.",
    "No OpenUpgrade clone for {} — candidate detection will be empty for those steps (generate the environment first).":
        "Sin clon de OpenUpgrade para {} — la detección de candidatos quedará vacía en esos pasos (genera antes el entorno).",
    "This replaces the already-staged code of: {}.": "Esto reemplaza el código ya preparado de: {}.",
    "Staging report: {}": "Informe de staging: {}",
    "Staging is a prepared starting point — your review completes the migration.":
        "El staging es un punto de partida preparado — tu revisión completa la migración.",
    # --- capability tables (provision check, migration preflight) ---
    'Host release': 'Versión del host',
    'Odoo build dependencies': 'Dependencias de compilación de Odoo',
    'PostgreSQL loopback auth': 'Autenticación loopback de PostgreSQL',
    'PostgreSQL version': 'Versión de PostgreSQL',
    'Development role ({})': 'Rol de desarrollo ({})',
    'Outbound firewall — OpenSnitch (optional)': 'Cortafuegos de salida — OpenSnitch (opcional)',
    'Mail capture — Mailpit (optional)': 'Captura de correo — Mailpit (opcional)',
    'Node.js (optional)': 'Node.js (opcional)',
    'rtlcss (optional)': 'rtlcss (opcional)',
    'uv (interpreters)': 'uv (intérpretes)',
    'Host python3': 'python3 del host',
    'all present': 'todas presentes',
    '{} missing': 'faltan {}',
    'not installed — PDF reports will fail': 'no instalado — los informes PDF fallarán',
    'installed and running': 'instalado y en ejecución',
    'installed but not running': 'instalado pero no está en ejecución',
    'present': 'presente',
    'not found': 'no encontrado',
    'could not be checked: PostgreSQL is not running':
        'no se pudo comprobar: PostgreSQL no está en ejecución',
    'could not be checked without sudo — run with sudo, or log in as the role once':
        'no se pudo comprobar sin sudo — ejecútalo con sudo, o entra una vez como el rol',
    'not installed (only for right-to-left languages)':
        'no instalado (solo para idiomas de derecha a izquierda)',
    'present — provides {}': 'presente — proporciona {}',
    'no interpreters listed': 'no lista intérpretes',
    'not installed (needed for migration steps and for any Odoo version the host python3 is out of range for — docs.astral.sh/uv)':
        'no instalado (necesario para los pasos de migración y para cualquier versión de Odoo fuera del rango del python3 del host — docs.astral.sh/uv)',
    '{} is not supported — supported: {}': '{} no está soportado — soportados: {}',
    '{} (un-patched — reports may be degraded)':
        '{} (sin parchear — los informes pueden degradarse)',
    '{} (no version declares a floor)': '{} (ninguna versión declara un mínimo)',
    '{} is below the {} Odoo {} requires': '{} es inferior al {} que requiere Odoo {}',
    '{} (Odoo {} requires {})': '{} (Odoo {} requiere {})',
    'trust for {} only': 'solo trust para {}',
    'PostgreSQL could not be asked for its rules — it may be stopped, the view needs sudo, or it reported a rule it could not parse; apply narrows the rules either way':
        'no se pudo preguntar a PostgreSQL por sus reglas — puede estar parado, la vista necesita sudo, o informó de una regla que no pudo interpretar; apply estrecha las reglas igualmente',
    'every role may connect over loopback without a password — apply narrows it to {}':
        'cualquier rol puede conectar por loopback sin contraseña — apply lo estrecha a {}',
    "{}'s loopback trust rule is missing or is never reached — apply adds one that is":
        'la regla de trust por loopback de {} falta o nunca se alcanza — apply añade una que sí',
    'config: unreadable': 'config: ilegible',
    'config: not valid JSON': 'config: no es JSON válido',
    '{} installed but not running': '{} instalado pero no está en ejecución',
    '{} running, not hardened: {}': '{} en ejecución, sin reforzar: {}',
    '{} running, hardened (default deny)': '{} en ejecución, reforzado (denegar por defecto)',
    '{} running — SMTP 127.0.0.1:1025, UI :8025':
        '{} en ejecución — SMTP 127.0.0.1:1025, interfaz :8025',
    'Addons layout': 'Layout de addons',
    'Source dump': 'Dump origen',
    'Database checks': 'Comprobaciones de base de datos',
    'Database version': 'Versión de la base de datos',
    'Installed modules': 'Módulos instalados',
    'Coverage ({})': 'Cobertura ({})',
    'Dropped by Odoo ({})': 'Eliminado por Odoo ({})',
    'Custom module {}': 'Módulo custom {}',
    'reachable': 'accesible',
    'not reachable': 'no accesible',
    'not installed (needed to build the native venvs)':
        'no instalado (necesario para construir los venvs nativos)',
    'not found (see provision)': 'no encontrado (ver provisión)',
    'could not check without sudo — run it with sudo, or connect as the role once':
        'no se pudo comprobar sin sudo — ejecútalo con sudo, o conéctate una vez como el rol',
    'skipped (no dump given)': 'omitido (no se indicó dump)',
    'skipped (no database named)': 'omitido (no se indicó base de datos)',
    'not readable: {}': 'no legible: {}',
    'pg_restore cannot list it — a custom-format dump (pg_dump -Fc) is required. {}':
        'pg_restore no puede listarlo — hace falta un dump en formato custom (pg_dump -Fc). {}',
    'addons/odoo<major>/{custom,oca} dirs absent — regenerate the environment':
        'faltan los directorios addons/odoo<major>/{custom,oca} — regenera el entorno',
    'cannot read ir_module_module (is it an Odoo database?)':
        'no se puede leer ir_module_module (¿es una base de datos de Odoo?)',
    'base {} matches source {}': 'base {} coincide con el origen {}',
    'base is {} but the environment was generated for source {}':
        'base es {} pero el entorno se generó para el origen {}',
    '{} installed': '{} instalados',
    "that step's sources are not on disk — generate the environment before reading coverage":
        'las fuentes de ese paso no están en disco — genera el entorno antes de leer la cobertura',
    "{} — place each module's {} branch in {}": '{} — coloca la rama {} de cada módulo en {}',
    '{} — not in {} and not renamed; OpenUpgrade removes them':
        '{} — no están en {} ni renombrados; OpenUpgrade los elimina',
    'needs per-version adapted code (and migrations/ scripts when data changes) — presence is not sufficient; see the staging workflow':
        'necesita código adaptado a cada versión (y scripts migrations/ cuando cambian datos) — estar presente no basta; ver el flujo de staging',
    # validation errors (models.py)
    'Invalid Odoo version: {!r} (supported: {}).':
        'Versión de Odoo no válida: {!r} (admitidas: {}).',
    'Invalid Python version: {!r} (expected e.g. 3.10).':
        'Versión de Python no válida: {!r} (se espera p. ej. 3.10).',
    'Invalid {}: {!r} (a whole number from 1 to {}).':
        '{} no válido: {!r} (un número entero de 1 a {}).',
    'Invalid workspace name: start with a lowercase letter, only [a-z0-9_], max 32 chars.':
        'Nombre de workspace no válido: empieza por minúscula, solo [a-z0-9_], máximo 32 caracteres.',
    'Invalid db_host: {!r} (a host name or IP address).':
        'db_host no válido: {!r} (un nombre de host o una dirección IP).',
    'Invalid db_user: {!r} (a PostgreSQL role).': 'db_user no válido: {!r} (un rol de PostgreSQL).',
    'Invalid working_db: {!r}.': 'working_db no válido: {!r}.',
    'The source ({}) must be older than the target ({}).':
        'El origen ({}) debe ser anterior al destino ({}).',
    'A workspace profile must be a JSON object, not {}.':
        'Un perfil de workspace debe ser un objeto JSON, no {}.',
    '{} is not a step in this chain ({}).': '{} no es un paso de esta cadena ({}).',
    'workspace profile': 'perfil de workspace',
    # the CLI's own help, printed by argparse before any menu
    'Create / manage per-client workspaces.': 'Crear y gestionar workspaces por cliente.',
    'Prepare a Linux host (optional).': 'Preparar un host Linux (opcional).',
    'Run an OpenUpgrade migration (12→19).': 'Ejecutar una migración OpenUpgrade (12→19).',
    "Stream every line a plan's commands print (default: one line per step, plus warnings and the output of a step that fails). Also ODWG_VERBOSE=1.":
        'Muestra cada línea que imprimen los comandos del plan (por defecto: una línea por paso, más los avisos y la salida de un paso que falla). También con ODWG_VERBOSE=1.',
    '(no output)': '(sin salida)',
    '{} — outside the supported range': '{} — fuera del rango soportado',
    'At least one Odoo version is required.':
        'Hace falta al menos una versión de Odoo.',
    'oca_repos must be a list of OCA repository names.':
        'oca_repos debe ser una lista de nombres de repositorios OCA.',
    'Invalid OCA repository name: {!r}.':
        'Nombre de repositorio OCA no válido: {!r}.',
    'Invalid db_user: {!r} (a PostgreSQL role: lowercase letters, digits and underscores, max 63 chars).':
        'db_user no válido: {!r} (un rol de PostgreSQL: minúsculas, dígitos y guiones bajos, máximo 63 caracteres).',
    # --- complete UI coverage (checked by tests/test_i18n.py) ---
    "English": "English",
    "Español": "Español",
    "The selected path for {} does not match the expected extensions: {}":
        "La ruta seleccionada para {} no coincide con las extensiones esperadas: {}",
    "Use this file anyway?": "¿Usar este fichero de todos modos?",
    "Select required file": "Selecciona el fichero requerido",
    "(default)": "(por defecto)",
    "Current directory": "Directorio actual",
    "  0) Choose a manual path": "  0) Introducir una ruta manual",
    "  ..) Up one level": "  ..) Subir un nivel",
    "  q) Cancel": "  q) Cancelar",
    "Choose a number, ..,  q, or a manual path": "Elige un número, .., q o una ruta manual",
    "Full file path": "Ruta completa del fichero",
    "Invalid input.": "Entrada no válida.",
    "Odoo {} supports Python {} — this host runs {}.":
        "Odoo {} soporta Python {} — este host usa {}.",
    "an undetected version": "una versión no detectada",
    "uv cannot provide Python {} on this host — install uv (provision check reports it) to build with it.":
        "uv no puede proporcionar Python {} en este host — instala uv (provision check lo indica) para usarlo.",
    "Keep the host python3 ({})": "Mantener el python3 del host ({})",
    "Build with uv Python {} (recommended)": "Usar Python {} de uv (recomendado)",
    "Choose another Python version": "Elegir otra versión de Python",
    "Interpreter for Odoo {}": "Intérprete para Odoo {}",
    "Python version (e.g. 3.10)": "Versión de Python (p. ej. 3.10)",
    "Python {} is outside the supported range for Odoo {} (bound: {}).":
        "Python {} está fuera del rango soportado por Odoo {} (límite: {}).",
    "Use it anyway?": "¿Usarlo de todos modos?",
    "\nWorkspaces": "\nWorkspaces",
    "Create a workspace": "Crear un workspace",
    "Manage an existing workspace": "Gestionar un workspace existente",
    "New workspace": "Nuevo workspace",
    "New (quick)": "Nuevo (rápido)",
    "From a profile file": "Desde un fichero de perfil",
    "Workspace name": "Nombre del workspace",
    "Odoo versions (comma-separated)": "Versiones de Odoo (separadas por comas)",
    "OCA repositories (comma-separated, optional)":
        "Repositorios OCA (separados por comas, opcional)",
    "Nothing to do.": "Nada que hacer.",
    "Odoo {} venv will use Python {}.": "El venv de Odoo {} usará Python {}.",
    "Workspace {} already exists — use manage to modify it.":
        "El workspace {} ya existe — usa gestionar para modificarlo.",
    "Workspace {} created.": "Workspace {} creado.",
    "No workspace.json in {} — cannot manage it.":
        "No hay workspace.json en {} — no se puede gestionar.",
    "No workspaces found.": "No se encontraron workspaces.",
    "Existing workspaces": "Workspaces existentes",
    "Manage {}": "Gestionar {}",
    "Refresh generated files": "Actualizar los ficheros generados",
    "Regenerate a venv": "Regenerar un venv",
    "Refresh shared repos": "Actualizar los repos compartidos",
    "Add a version": "Añadir una versión",
    "Which version": "¿Qué versión?",
    "This removes and rebuilds .venv/odoo{}.": "Esto elimina y reconstruye .venv/odoo{}.",
    "No present clones to refresh.": "No hay clones presentes que actualizar.",
    "New Odoo version (e.g. 19.0)": "Nueva versión de Odoo (p. ej. 19.0)",
    "{} is already in the workspace.": "{} ya está en el workspace.",
    "\nSystem provisioning": "\nProvisión del sistema",
    "Check host readiness": "Comprobar si el host está listo",
    "Apply (install what's missing)": "Aplicar (instalar lo que falte)",
    "Capability": "Capacidad",
    "{} is not supported — supported hosts: {}.": "{} no está soportado — hosts soportados: {}.",
    "Install rtlcss (with Node.js)? Only needed if users work in a right-to-left language (Arabic, Hebrew, Persian…)":
        "¿Instalar rtlcss (con Node.js)? Solo hace falta si los usuarios trabajan en un idioma de derecha a izquierda (árabe, hebreo, persa…)",
    "Host already provisioned — nothing to do.": "El host ya está provisionado — nada que hacer.",
    "Provisioning applied.": "Provisión aplicada.",
    "\nMigration (OpenUpgrade 12→19)": "\nMigración (OpenUpgrade 12→19)",
    "Source Odoo version (e.g. 13.0)": "Versión de Odoo origen (p. ej. 13.0)",
    "Target Odoo version (e.g. 18.0)": "Versión de Odoo destino (p. ej. 18.0)",
    "pinned by you": "fijado por ti",
    "recommended": "recomendado",
    "{} — the venv on disk was built with {}": "{} — el venv en disco se construyó con {}",
    "Step": "Paso",
    "Interpreter": "Intérprete",
    "Source": "Origen",
    "Pin a step to a specific Python version?": "¿Fijar un paso a una versión concreta de Python?",
    "Which step": "¿Qué paso?",
    "Python for Odoo {}": "Python para Odoo {}",
    "Pin it anyway?": "¿Fijarlo de todos modos?",
    "Migration chain: {}": "Cadena de migración: {}",
    "Apply this plan now?": "¿Aplicar este plan ahora?",
    "Environment ready. Run: bash {}/run_migration.sh <source-dump>":
        "Entorno listo. Ejecuta: bash {}/run_migration.sh <dump-origen>",
    "Create migrations directory for {} ({})": "Crear el directorio migrations de {} ({})",
    "State": "Estado",
    "Check": "Comprobación",
    "Detail": "Detalle",
    "Write {} (mode {})": "Escribir {} (modo {})",
    "Set mode {} on {}": "Fijar permisos {} en {}",
    "Clone Odoo {} into the shared cache": "Clonar Odoo {} en la caché compartida",
    "Clone OCA {} ({}) into the shared cache": "Clonar OCA {} ({}) en la caché compartida",
    "Create workspace directories for {}": "Crear los directorios del workspace {}",
    "Link OCA {} for Odoo {}": "Enlazar OCA {} para Odoo {}",
    "Back up {} to {}": "Guardar copia de seguridad de {} en {}",
    "Create directory for {}": "Crear el directorio de {}",
    "Update apt package lists": "Actualizar las listas de paquetes apt",
    "Install Odoo build dependencies": "Instalar las dependencias de compilación de Odoo",
    "Install PostgreSQL": "Instalar PostgreSQL",
    "Enable and start PostgreSQL": "Habilitar e iniciar PostgreSQL",
    "Create development role {} (if missing)": "Crear el rol de desarrollo {} (si falta)",
    "Trust loopback connections of {} for local development (pg_hba)":
        "Confiar en las conexiones loopback de {} para desarrollo local (pg_hba)",
    "Reload PostgreSQL": "Recargar PostgreSQL",
    "Ensure curl is available": "Asegurar que curl está disponible",
    "Download patched wkhtmltopdf ({})": "Descargar wkhtmltopdf parcheado ({})",
    "Verify wkhtmltopdf SHA-256 (abort on mismatch)":
        "Verificar el SHA-256 de wkhtmltopdf (aborta si no coincide)",
    "Install verified wkhtmltopdf .deb": "Instalar el .deb verificado de wkhtmltopdf",
    "Check that the patched wkhtmltopdf is the one on PATH":
        "Comprobar que el wkhtmltopdf del PATH es el parcheado",
    "Remove downloaded wkhtmltopdf .deb": "Eliminar el .deb descargado de wkhtmltopdf",
    "Install Node.js and npm": "Instalar Node.js y npm",
    "Install rtlcss globally": "Instalar rtlcss globalmente",
    "Clone OpenUpgrade {}": "Clonar OpenUpgrade {}",
    "Clone Odoo {}": "Clonar Odoo {}",
    "Create requirements directory": "Crear el directorio de requirements",
    "Create uv venv (Python {}) for Odoo {}": "Crear el venv uv (Python {}) para Odoo {}",
    "Install psycopg2-binary and openupgradelib for Odoo {}":
        "Instalar psycopg2-binary y openupgradelib para Odoo {}",
    "Mark Odoo {} venv as ready": "Marcar el venv de Odoo {} como listo",
    "Mark the venv {} ready": "Marcar el venv {} como listo",
    "Create migration directories": "Crear los directorios de migración",
    "Create the staging tool venv": "Crear el venv de la herramienta de staging",
    "Install odoo-module-migrator": "Instalar odoo-module-migrator",
    "Create staging directories for {}": "Crear los directorios de staging de {}",
    "Copy {} stage {} from the {} stage": "Copiar {} etapa {} desde la etapa {}",
    "Prepare the git worktree for {} stage {}": "Preparar el worktree git de {} etapa {}",
    "Migrate {} code {} -> {}": "Migrar el código de {} {} -> {}",
    "Refresh Odoo {}": "Actualizar Odoo {}",
    "Refresh OCA {} ({})": "Actualizar OCA {} ({})",
    "Remove existing venv {}": "Eliminar el venv existente {}",
    "Create venv {} with uv (Python {})": "Crear el venv {} con uv (Python {})",
    "Create venv {}": "Crear el venv {}",
    "Upgrade pip/wheel/setuptools in {}": "Actualizar pip/wheel/setuptools en {}",
    "Install Odoo {} requirements": "Instalar los requisitos de Odoo {}",
    # --- egress control and mail capture ---
    "Redirect a database's mail to Mailpit": 'Redirigir el correo de una base de datos a Mailpit',
    'Create download directory {}': 'Crear el directorio de descarga {}',
    'Download {}': 'Descargar {}',
    'Verify {} SHA-512 (abort on mismatch)': 'Verificar el SHA-512 de {} (aborta si no coincide)',
    'Install OpenSnitch {} without starting it': 'Instalar OpenSnitch {} sin arrancarlo',
    'Remove downloaded packages': 'Eliminar los paquetes descargados',
    'Harden {}': 'Endurecer {}',
    "Replace the tool's own OpenSnitch rules ({}*)":
        'Sustituir las reglas propias de OpenSnitch ({}*)',
    'Enable and (re)start OpenSnitch': 'Habilitar y (re)iniciar OpenSnitch',
    'Download Mailpit {}': 'Descargar Mailpit {}',
    'Verify Mailpit SHA-256 (abort on mismatch)':
        'Verificar el SHA-256 de Mailpit (aborta si no coincide)',
    'Install Mailpit to {}': 'Instalar Mailpit en {}',
    'Remove downloaded files': 'Eliminar los ficheros descargados',
    'Enable and (re)start Mailpit': 'Habilitar y (re)iniciar Mailpit',
    'Redirect the mail of database {} to Mailpit':
        'Redirigir el correo de la base de datos {} a Mailpit',
    'Install or update the outbound firewall (OpenSnitch)?':
        '¿Instalar o actualizar el cortafuegos de salida (OpenSnitch)?',
    'Install or update the local mail capture (Mailpit)?':
        '¿Instalar o actualizar la captura local de correo (Mailpit)?',
    'Check that {} connects over loopback': 'Comprobar que {} conecta por loopback',
    'Ask PostgreSQL to read back the rules for {}':
        'Preguntar a PostgreSQL por las reglas que tiene para {}',
    'OpenSnitch blocks every outbound connection without a rule, asking in its UI when it is open. Odoo may reach only localhost, plus DNS on port 53; the development tools keep their hosts. See docs/egress-control.md.':
        'OpenSnitch bloquea toda conexión saliente sin regla y pregunta en su interfaz cuando está abierta. Odoo solo puede llegar a localhost, más DNS en el puerto 53; las herramientas de desarrollo conservan sus destinos. Ver docs/egress-control.md.',
    'Database whose mail to redirect': 'Base de datos a la que redirigir el correo',
    'Invalid database name: {}': 'Nombre de base de datos no válido: {}',
    'Every mail server of {} will point at Mailpit and lose its credentials, and mail fetching stops. Use it on rehearsal copies only — never on a database going back to production.':
        'Todos los servidores de correo de {} apuntarán a Mailpit y perderán sus credenciales, y se detiene la recepción de correo. Úsalo solo en copias de ensayo — nunca en una base de datos que vuelve a producción.',
    'Turn on {} (and at every start)': 'Encender {} (y en cada arranque)',
    'Turn off {} (and keep it off after a restart)':
        'Apagar {} (y mantenerlo apagado tras reiniciar)',
    "Remove the tool's own OpenSnitch rules ({}*)":
        'Eliminar las reglas propias de OpenSnitch ({}*)',
    'Purge OpenSnitch and the packages it pulled in':
        'Purgar OpenSnitch y los paquetes que arrastró',
    'Remove {}': 'Eliminar {}',
    'Remove the captured mail ({})': 'Eliminar el correo capturado ({})',
    'apt would remove {} package(s): {}': 'apt eliminaría {} paquete(s): {}',
    'Your own rules in {} are kept.': 'Tus propias reglas en {} se conservan.',
    'This removes the outbound firewall.': 'Esto elimina el cortafuegos de salida.',
    'This removes Mailpit and every message it captured.':
        'Esto elimina Mailpit y todos los mensajes que capturó.',
    'Done.': 'Hecho.',
    'not installed': 'no instalado',
    'on': 'encendido',
    'off': 'apagado',
    'running': 'en ejecución',
    'NOT running': 'NO está en ejecución',
    'A service is installed but not running. Check `systemctl status` for it: a unit that '
        'starts and then exits still leaves its install step reporting success.':
        'Hay un servicio instalado que no está en ejecución. Revisa `systemctl status`: una unidad que '
    'arranca y muere deja igualmente su paso de instalación informando de éxito.',
    'Component': 'Componente',
    'Version': 'Versión',
    'Neither is installed — use Apply to install them.':
        'No hay ninguno instalado — usa Aplicar para instalarlos.',
    '\nOutbound firewall and mail capture': '\nCortafuegos de salida y captura de correo',
    'Outbound firewall and mail capture (on/off, uninstall)':
        'Cortafuegos de salida y captura de correo (encender/apagar, desinstalar)',
    'Turn the outbound firewall off': 'Apagar el cortafuegos de salida',
    'Turn the outbound firewall on': 'Encender el cortafuegos de salida',
    'Uninstall the outbound firewall': 'Desinstalar el cortafuegos de salida',
    'Turn the mail capture off': 'Apagar la captura de correo',
    'Turn the mail capture on': 'Encender la captura de correo',
    'Uninstall the mail capture': 'Desinstalar la captura de correo',
    "Unload the kernel modules it used": "Retirar de memoria los módulos del kernel que usaba",
    'No verified patched wkhtmltopdf is pinned for {} — install it by hand (github.com/wkhtmltopdf/packaging) or PDF reports will be degraded.':
        'No hay ningún wkhtmltopdf parcheado y verificado fijado para {} — instálalo a mano (github.com/wkhtmltopdf/packaging) o los informes PDF saldrán degradados.',
    'Cannot read {}: {}': 'No se puede leer {}: {}',
    "Edit {} and run this again.": "Edita {} y vuelve a ejecutarlo.",
    "Make {} executable again": "Volver a hacer ejecutable {}",
    "These OCA repos are in the profile but not on disk: {}. The refreshed files name them "
    "in addons_path; run Refresh shared repos to clone and link them.":
        "Estos repos de OCA están en el perfil pero no en disco: {}. Los ficheros regenerados los "
        "nombran en addons_path; ejecuta «Refrescar repos compartidos» para clonarlos y enlazarlos.",
    "Adding {} moves the port of every later version: {}. Stop any instance you have "
    "running before applying, and use the new port afterwards.":
        "Añadir {} mueve el puerto de todas las versiones posteriores: {}. Para cualquier instancia "
        "que tengas en marcha antes de aplicar, y usa el puerto nuevo después.",
    "The venv for Odoo {} on disk was built with Python {}, outside the supported range "
    "({}). The refreshed files describe and rebuild it as it is.":
        "El venv de Odoo {} en disco se construyó con Python {}, fuera del rango soportado ({}). "
        "Los ficheros regenerados lo describen y lo reconstruyen tal cual.",
    'Cannot use the profile {}: {}': 'No se puede usar el perfil {}: {}',
    '{} names another workspace ({}).': '{} corresponde a otro workspace ({}).',
    "Not an Odoo module name: {}": "No es un nombre de módulo de Odoo: {}",
}

# Runtime lookup: English (the in-code source) → Spanish.
