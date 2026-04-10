# Intégration MemPalace dans un devcontainer

Ce guide explique comment rendre MemPalace disponible à l'intérieur d'un devcontainer VS Code, avec le palace partagé entre l'hôte et le conteneur.

---

## Vue d'ensemble

Deux éléments sont nécessaires dans le conteneur :

| Élément | Montage | Rôle |
|---|---|---|
| **Bridge MCP** (`mempalace-mcp-bridge`) | `:ro` — lecture seule | Code du serveur MCP + venv |
| **Palace** (`~/.mempalace`) | bind mount lecture/écriture | Données (drawers, knowledge graph) |

Le palace est partagé avec l'hôte : tout ce que l'agent mémorise dans le container est directement visible sur l'hôte, et inversement.

**Principe de conception** : le clone du repo vit sur l'hôte à l'emplacement que tu choisis. Le devcontainer le monte en lecture seule à un chemin fixe (`/opt/mempalace-mcp-bridge`). Cela évite toute hypothèse machine-spécifique (ex. `~/git`) tout en gardant les scripts et la config MCP stables.

---

## Prérequis (hôte)

1. Clone le repo `mempalace-mcp-bridge` à l'endroit de ton choix :

   ```bash
   git clone https://github.com/apajon/mempalace-mcp-bridge ~/git/mempalace-mcp-bridge
   ```

   > Le chemin `~/git` n'est qu'un exemple. Tu peux utiliser n'importe quel chemin.

2. Exporte la variable d'environnement `MEMPALACE_BRIDGE_HOST_DIR` pointant vers ce clone :

   ```bash
   export MEMPALACE_BRIDGE_HOST_DIR=~/git/mempalace-mcp-bridge
   ```

   Pour rendre ce réglage permanent, ajoute la ligne ci-dessus dans ton `~/.bashrc`, `~/.zshrc` ou équivalent.

3. Le palace a été initialisé au moins une fois sur l'hôte (`bash setup.sh`).

4. `uv` est disponible dans l'image Docker du devcontainer.

---

## Étape 1 — Monter le bridge et le palace

Dans `docker-compose.yml`, ajoute les deux volumes :

```yaml
services:
  dev:
    volumes:
      # Bridge MCP (lecture seule — le venv s'installe dans le conteneur)
      - ${MEMPALACE_BRIDGE_HOST_DIR}:/opt/mempalace-mcp-bridge:ro

      # Palace partagé avec l'hôte (lecture/écriture)
      - ~/.mempalace:/home/<container-user>/.mempalace
```

Ou dans `devcontainer.json` avec la syntaxe `localEnv` de VS Code :

```json
"mounts": [
  "source=${localEnv:MEMPALACE_BRIDGE_HOST_DIR},target=/opt/mempalace-mcp-bridge,type=bind,consistency=cached,readonly"
]
```

> Remplace `<container-user>` par le nom d'utilisateur dans le conteneur (ex. `dev`, `vscode`, `user`).
> Vérifie avec `whoami` dans un terminal du devcontainer.
> Le chemin cible `/opt/mempalace-mcp-bridge` est **fixe** côté conteneur. Seul le chemin source est configurable via `MEMPALACE_BRIDGE_HOST_DIR`.

---

## Étape 2 — Valider la variable hôte (initializeCommand)

Utilise `initializeCommand` pour valider que `MEMPALACE_BRIDGE_HOST_DIR` est définie et pointe vers un répertoire existant. La commande s'exécute **sur l'hôte**, avant la création du conteneur :

```json
"initializeCommand": "test -n \"${MEMPALACE_BRIDGE_HOST_DIR}\" && test -d \"${MEMPALACE_BRIDGE_HOST_DIR}\" || (echo 'ERROR: MEMPALACE_BRIDGE_HOST_DIR is not set or does not exist. Export it to the path of your mempalace-mcp-bridge clone and rebuild.' && exit 1)"
```

Cette commande échoue tôt avec un message explicite si la variable est absente ou si le répertoire n'existe pas, avant même que Docker tente de monter le volume.

---

## Étape 3 — Installer les dépendances et vérifier le palace (post-create)

Dans `post-create.sh`, ajoute le bloc suivant. Il installe les dépendances du bridge et exécute le health check pour détecter et corriger d'éventuelles incompatibilités ChromaDB :

```bash
MEMPALACE_DIR=/opt/mempalace-mcp-bridge

if [ -f "$MEMPALACE_DIR/pyproject.toml" ]; then
    echo 'MemPalace: installation des dépendances...'
    uv sync --directory "$MEMPALACE_DIR" --quiet
    echo 'MemPalace: vérification de la santé du palace...'
    bash "$MEMPALACE_DIR/scripts/check_palace_health.sh" || true
    echo 'MemPalace: prêt'
else
    echo 'MemPalace: non disponible, skip (définissez MEMPALACE_BRIDGE_HOST_DIR et reconstruisez le conteneur pour l'\''activer)'
fi
```

> `uv sync` installe `mempalace` dans le venv du bridge à l'intérieur du conteneur.
> Le mount `:ro` garantit qu'aucun fichier n'est écrit dans le repo hôte.
> `check_palace_health.sh` corrige silencieusement les incompatibilités ChromaDB
> (voir [troubleshooting.md#chromadb-version-incompatibility](troubleshooting.md#chromadb-version-incompatibility)).

---

## Étape 4 — Configurer le serveur MCP dans VS Code

Dans le workspace devcontainer (`.vscode/mcp.json`), configure le serveur avec la variable d'environnement `MEMPALACE_PALACE_PATH` :

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "/home/<container-user>/.local/bin/uv",
      "args": [
        "run",
        "--directory", "/opt/mempalace-mcp-bridge",
        "python", "-m", "mempalace.mcp_server"
      ],
      "env": {
        "MEMPALACE_PALACE_PATH": "/home/<container-user>/.mempalace/palace"
      }
    }
  }
}
```

> Le chemin `/opt/mempalace-mcp-bridge` est toujours le même quel que soit l'endroit où tu as cloné le repo sur l'hôte.
>
> **Pourquoi `MEMPALACE_PALACE_PATH` ?**
> Sans cette variable, le serveur MCP cherche le palace dans le home de l'utilisateur
> courant du conteneur. La variable le rend explicite et prioritaire sur tout `config.json`
> qui aurait pu être copié avec un chemin d'une autre machine.
> Priorité de configuration : `env var > config.json > défaut`.

VS Code Copilot démarrera automatiquement le serveur MCP au lancement du chat.

---

## Résumé des fichiers modifiés

| Fichier | Modification |
|---|---|
| `docker-compose.yml` | Volume bridge `${MEMPALACE_BRIDGE_HOST_DIR}:/opt/…:ro` + palace bind mount |
| `devcontainer.json` | `mounts` avec `${localEnv:MEMPALACE_BRIDGE_HOST_DIR}` ; `initializeCommand` de validation |
| `post-create.sh` | `uv sync` + `check_palace_health.sh` |
| `.vscode/mcp.json` | Config MCP avec `env.MEMPALACE_PALACE_PATH` |

---

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `initializeCommand` échoue avec `MEMPALACE_BRIDGE_HOST_DIR is not set` | Variable non exportée sur l'hôte | Exécuter `export MEMPALACE_BRIDGE_HOST_DIR=<chemin>` dans le shell qui lance VS Code, puis reconstruire |
| `initializeCommand` échoue avec `does not exist` | Variable pointe vers un répertoire inexistant | Vérifier que le chemin est correct et que le clone est présent |
| `"No palace found"` dans les outils MCP | Palace non monté ou `MEMPALACE_PALACE_PATH` absent | Vérifier le bind mount `~/.mempalace` et la clé `env` dans `mcp.json` |
| `MemPalace: non disponible, skip` | `pyproject.toml` absent dans le mount | Vérifier que `MEMPALACE_BRIDGE_HOST_DIR` pointe vers la racine du repo |
| `uv: command not found` dans le container | `uv` absent de l'image | Ajouter `RUN pip install uv` dans le Dockerfile |
| Serveur MCP ne démarre pas | Chemin `uv` incorrect dans `mcp.json` | Vérifier avec `which uv` dans un terminal du devcontainer |
| Palace accessible sur l'hôte mais vide dans le container | Mauvais `<container-user>` dans le mount ou `MEMPALACE_PALACE_PATH` | Vérifier `whoami` dans le conteneur |
| Mount silencieusement vide | Docker Desktop / WSL — chemin Windows au lieu de Linux | Utiliser le chemin Linux (ex. `/home/user/...`) plutôt que `C:\...` |


---

## Vue d'ensemble

Deux éléments sont nécessaires dans le conteneur :

| Élément | Montage | Rôle |
|---|---|---|
| **Bridge MCP** (`mempalace-mcp-bridge`) | `:ro` — lecture seule | Code du serveur MCP + venv |
| **Palace** (`~/.mempalace`) | bind mount lecture/écriture | Données (drawers, knowledge graph) |

Le palace est partagé avec l'hôte : tout ce que l'agent mémorise dans le container est directement visible sur l'hôte, et inversement.

---

## Prérequis (hôte)

- Le repo `mempalace-mcp-bridge` est cloné :
  ```
  ~/git/mempalace-mcp-bridge
  ```
- Le palace a été initialisé au moins une fois sur l'hôte (`bash setup.sh`).
- `uv` est disponible dans l'image Docker du devcontainer.

---

## Étape 1 — Monter le bridge et le palace

Dans `docker-compose.yml`, ajoute les deux volumes :

```yaml
services:
  dev:
    volumes:
      # Bridge MCP (lecture seule — le venv s'installe dans le conteneur)
      - ~/git/mempalace-mcp-bridge:/opt/mempalace-mcp-bridge:ro

      # Palace partagé avec l'hôte (lecture/écriture)
      - ~/.mempalace:/home/<container-user>/.mempalace
```

> Remplace `<container-user>` par le nom d'utilisateur dans le conteneur (ex. `dev`, `vscode`, `user`).
> Vérifie avec `whoami` dans un terminal du devcontainer.

---

## Étape 2 — Créer le répertoire hôte si absent (initializeCommand)

Pour éviter que Docker crée le répertoire source en `root` si le clone n'existe pas encore :

```json
"initializeCommand": "mkdir -p ${localEnv:HOME}/git/mempalace-mcp-bridge"
```

Cette commande s'exécute **sur l'hôte**, avant la création du conteneur.

---

## Étape 3 — Installer les dépendances et vérifier le palace (post-create)

Dans `post-create.sh`, ajoute le bloc suivant. Il installe les dépendances du bridge et exécute le health check pour détecter et corriger d'éventuelles incompatibilités ChromaDB :

```bash
MEMPALACE_DIR=/opt/mempalace-mcp-bridge

if [ -f "$MEMPALACE_DIR/pyproject.toml" ]; then
    echo 'MemPalace: installation des dépendances...'
    uv sync --directory "$MEMPALACE_DIR" --quiet
    echo 'MemPalace: vérification de la santé du palace...'
    bash "$MEMPALACE_DIR/scripts/check_palace_health.sh" || true
    echo 'MemPalace: prêt'
else
    echo 'MemPalace: non disponible, skip (montez ~/git/mempalace-mcp-bridge pour l'\''activer)'
fi
```

> `uv sync` installe `mempalace` dans le venv du bridge à l'intérieur du conteneur.
> Le mount `:ro` garantit qu'aucun fichier n'est écrit dans le repo hôte.
> `check_palace_health.sh` corrige silencieusement les incompatibilités ChromaDB
> (voir [troubleshooting.md#chromadb-version-incompatibility](troubleshooting.md#chromadb-version-incompatibility)).

---

## Étape 4 — Configurer le serveur MCP dans VS Code

Dans le workspace devcontainer (`.vscode/mcp.json`), configure le serveur avec la variable d'environnement `MEMPALACE_PALACE_PATH` :

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "/home/<container-user>/.local/bin/uv",
      "args": [
        "run",
        "--directory", "/opt/mempalace-mcp-bridge",
        "python", "-m", "mempalace.mcp_server"
      ],
      "env": {
        "MEMPALACE_PALACE_PATH": "/home/<container-user>/.mempalace/palace"
      }
    }
  }
}
```

> **Pourquoi `MEMPALACE_PALACE_PATH` ?**
> Sans cette variable, le serveur MCP cherche le palace dans le home de l'utilisateur
> courant du conteneur. La variable le rend explicite et prioritaire sur tout `config.json`
> qui aurait pu être copié avec un chemin d'une autre machine.
> Priorité de configuration : `env var > config.json > défaut`.

VS Code Copilot démarrera automatiquement le serveur MCP au lancement du chat.

---

## Résumé des fichiers modifiés

| Fichier | Modification |
|---|---|
| `docker-compose.yml` | Volumes bridge (`:ro`) + palace (bind mount) |
| `devcontainer.json` | `initializeCommand` : `mkdir -p ~/git/mempalace-mcp-bridge` |
| `post-create.sh` | `uv sync` + `check_palace_health.sh` |
| `.vscode/mcp.json` | Config MCP avec `env.MEMPALACE_PALACE_PATH` |

---

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `"No palace found"` dans les outils MCP | Palace non monté ou `MEMPALACE_PALACE_PATH` absent | Vérifier le bind mount `~/.mempalace` et la clé `env` dans `mcp.json` |
| `MemPalace: non disponible, skip` | `pyproject.toml` absent dans le mount | Vérifier que le clone `~/git/mempalace-mcp-bridge` est complet |
| `uv: command not found` dans le container | `uv` absent de l'image | Ajouter `RUN pip install uv` dans le Dockerfile |
| Serveur MCP ne démarre pas | Chemin `uv` incorrect dans `mcp.json` | Vérifier avec `which uv` dans un terminal du devcontainer |
| Palace accessible sur l'hôte mais vide dans le container | Mauvais `<container-user>` dans le mount ou `MEMPALACE_PALACE_PATH` | Vérifier `whoami` dans le conteneur |

