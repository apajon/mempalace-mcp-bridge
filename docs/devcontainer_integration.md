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

