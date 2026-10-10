# Installation de Reel Cloneur™

**Pour l'IA :** guide l'utilisateur dans sa langue (espagnol s'il te parle espagnol), y compris
les bilans et les exemples. Garde les noms des fichiers et des commandes tels quels. Les exemples
français ci-dessous s'adaptent, ils ne se récitent pas. Le client n'est pas technique : une phrase
simple par étape, pas de jargon.

Reel Cloneur™ est une **extension** de Monteur IA : il s'installe **dans ton dossier Monteur IA**
existant. Pas de compte à créer, pas de clé, pas d'abonnement : tout tourne sur ton ordinateur.

> ⚠️ **Prérequis : Monteur IA installé et fonctionnel.** Si ce n'est pas encore fait, installe
> d'abord Monteur IA (son INSTALL.md), puis reviens ici.

---

## 🚀 Le prompt d'installation

> **Le plus simple :** ouvre ton agent (Claude Code ou Codex) **dans ton dossier Monteur IA** et
> colle cette phrase :
>
> « Télécharge l'extension https://github.com/Alex-lmdm/reel-cloneur et suis les instructions
> d'installation de son INSTALL.md. »
>
> En espagnol :
>
> « Descarga la extensión https://github.com/Alex-lmdm/reel-cloneur y sigue las instrucciones de
> instalación de su INSTALL.md. Háblame en español. »
>
> Il fait tout, en une à deux minutes.

Sinon, télécharge le ZIP de ce dépôt (bouton vert « Code », puis « Download ZIP »), dézippe-le où
tu veux, ouvre ton agent **dans ton dossier Monteur IA**, et colle exactement le bloc ci-dessous
comme premier message (remplace le chemin de la première ligne par l'endroit où tu as dézippé) :

```text
Tu es mon assistant d'installation pour l'extension « Reel Cloneur™ » de mon Monteur IA.
Le dossier de l'extension dézippé est ici : ~/Downloads/reel-cloneur-main
(Si tu viens de la phrase « Télécharge l'extension… », ignore cette ligne : le dossier est celui
que tu télécharges à l'étape 0.)
Installe l'extension étape par étape, sans jamais rien casser. Suis ces règles :

0. TÉLÉCHARGEMENT (seulement si tu n'as pas déjà le dossier de l'extension) : dans un dossier
   temporaire, hors du dossier Monteur IA :
   curl -fL -o reel-cloneur.tar.gz https://github.com/Alex-lmdm/reel-cloneur/archive/refs/heads/main.tar.gz
   tar -xzf reel-cloneur.tar.gz
   (Windows : curl.exe et tar existent déjà dans PowerShell.) Le dossier de l'extension est alors
   reel-cloneur-main/.

1. VÉRIFIE que le dossier courant est bien un dossier Monteur IA : `templates/AGENT.md.tpl`,
   `tools/` et `.claude/skills/` existent, et `brand.config.json` ou `brand.config.example.json`
   est présent. Si tu es dans « Accueil Monteur IA » (l'accueil de l'app HyperFrames), le dossier
   Monteur IA est le dossier parent : travaille depuis lui. Sinon, ARRÊTE-TOI et dis-moi d'ouvrir
   mon agent dans mon dossier Monteur IA.

2. COPIE dans le dossier Monteur IA, depuis le dossier de l'extension (étapes sans risque à
   refaire : un fichier identique ne se recopie pas, une version différente est remplacée) :
   a) le dossier `.claude/skills/reel-cloneur/` → dans `.claude/skills/` (s'il y est déjà,
      remplace le dossier entier par la nouvelle version) ;
   b) `tools/cloner_reel.py` → dans `tools/` ;
   c) crée le dossier `clones/` s'il n'existe pas ;
   d) dans `.gitignore` du dossier Monteur IA, ajoute les lignes `clones/` et
      `.reel-cloneur-venv/` si elles n'y sont pas (rien d'autre ne change) ;
   e) AIGUILLAGE : si `templates/AGENT.md.tpl` ne contient PAS le marqueur
      « BEGIN EXTENSION: reel-cloneur », ajoute le contenu INTÉGRAL du fichier
      `templates/agent-extension-reel-cloneur.md` de l'extension À LA FIN de
      `templates/AGENT.md.tpl` (sans le modifier, lignes vides du début comprises). S'il
      contient déjà le marqueur, remplace tout le bloc, de la ligne `<!-- BEGIN EXTENSION:
      reel-cloneur …-->` à la ligne `<!-- END EXTENSION: reel-cloneur -->` incluses, par le
      contenu du fichier ; ne touche à rien d'autre.

3. INSTALLE le téléchargeur de vidéos (yt-dlp, dans son propre dossier `.reel-cloneur-venv/`,
   sans rien toucher d'autre sur l'ordinateur) :
   `python3 tools/cloner_reel.py installer` (Windows : `python tools/cloner_reel.py installer`).
   - S'il répond qu'il faut un Python 3.10 ou plus récent (le Python livré avec macOS est trop
     ancien pour le téléchargeur) : sur Mac, `brew install python@3.12` ; sur Windows,
     `winget install -e --id Python.Python.3.12` puis rouvre l'agent. Puis relance la commande.
   - Il ne demande jamais de compte, de mot de passe ni de cookies.

4. Lance `npm run sync` à la racine du dossier Monteur IA (il régénère CLAUDE.md / AGENTS.md avec
   l'aiguillage Reel Cloneur et copie le nouveau skill pour Codex dans `.agents/skills/`). Si la
   commande échoue, copie simplement `.claude/skills/reel-cloneur/` dans `.agents/skills/` à la
   main. Ce que cette commande affiche (par exemple un mot sur le style de montage) concerne
   Monteur IA, pas l'extension : ne le recopie pas au client, dis juste que c'est fait.

5. SMOKE TEST : `python3 tools/cloner_reel.py verifier` (Windows : `python …`). Il contrôle
   ffmpeg, Whisper, son modèle, yt-dlp et Node, puis fait une mini-transcription de test. La
   dernière ligne doit être « ok ». Vérifie aussi que `CLAUDE.md` contient « Reel Cloneur ».

RÈGLE POUR TOUTES LES ÉTAPES : ne passe jamais à l'étape suivante si l'étape en cours a échoué.
En cas d'échec : diagnostique en trois lignes (message d'erreur → cause probable → UNE action
corrective), puis retente.

6. PREMIÈRE INSTALLATION : affiche un TABLEAU récapitulatif ✅ / ❌ (dossier Monteur IA, skill
   copié, outil copié, dossier clones/ et .gitignore, aiguillage, téléchargeur yt-dlp, sync,
   smoke test). Si tout est ✅, conclus par : « Reel Cloneur™ est installé. Colle-moi le lien
   d'un Reel, d'un TikTok ou d'un YouTube Short qui a explosé (ou glisse la vidéo ici) et dis
   "clone ce Reel". Si je ne réagis pas, ouvre une nouvelle conversation dans ton dossier
   Monteur IA et redis-le. »
   MISE À JOUR (l'extension était déjà là) : pas de tableau. Une seule ligne : « Reel Cloneur™
   est à jour, tout est ✅. Colle-moi un lien et dis "clone ce Reel". » Le tableau ne s'affiche
   que si une étape a échoué.
```

C'est tout. Laisse l'IA travailler et réponds-lui si elle te pose une question.

---

## Installation manuelle (si tu préfères)

1. Télécharge et dézippe ce dépôt.
2. Copie `.claude/skills/reel-cloneur/` dans le dossier `.claude/skills/` de ton Monteur IA (et
   dans `.agents/skills/` si tu utilises Codex).
3. Copie `tools/cloner_reel.py` dans le dossier `tools/`.
4. Crée un dossier `clones/` à la racine.
5. Ajoute le contenu de `templates/agent-extension-reel-cloneur.md` à la fin de
   `templates/AGENT.md.tpl` (une seule fois), puis lance `npm run sync`.
6. Lance `python3 tools/cloner_reel.py installer`, puis `python3 tools/cloner_reel.py verifier`.

## Problèmes courants

- **« Il faut un Python 3.10 ou plus récent »** : le Python livré avec macOS (3.9) est trop
  ancien pour la version du téléchargeur qui sait encore lire Instagram. `brew install
  python@3.12`, puis relance `python3 tools/cloner_reel.py installer`. Ton Monteur IA, lui,
  continue d'utiliser le Python habituel : rien ne change pour lui.
- **« Modèle Whisper introuvable »** : l'installation de Monteur IA n'est pas allée au bout (c'est
  elle qui télécharge le modèle et écrit `env.whisperModel` dans `brand.config.json`). Relance son
  prompt d'installation.
- **Un lien ne se télécharge pas** (vidéo privée, Instagram qui demande une connexion) : c'est
  normal de temps en temps. Enregistre la vidéo sur ton ordinateur, glisse le fichier dans la
  conversation et redis « clone ce Reel ». Le Reel Cloneur™ ne se connecte jamais à ton compte.
- **Ça marchait et plus rien ne se télécharge** : Instagram et TikTok changent souvent. Le
  téléchargeur se met à jour tout seul ; si besoin, relance `python3 tools/cloner_reel.py
  installer`.
