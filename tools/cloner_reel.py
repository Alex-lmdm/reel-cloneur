#!/usr/bin/env python3
"""REEL CLONEUR : prépare l'analyse d'un Reel qui a marché (Instagram, TikTok, YouTube Short ou fichier).

L'outil fait toute la partie mécanique ; l'IA fait ensuite la lecture et l'écriture (skill
`reel-cloneur`). Il range tout dans clones/<date>-<slug>/ du dossier Monteur IA :

    media.mp4        la vidéo (720p max)
    audio.wav        l'audio en 16 kHz mono (pour Whisper)
    transcript.json  la transcription horodatée (langue détectée : le Reel peut être en anglais)
    shots.json       les coupes, la durée des plans, le rythme, la liste des images extraites
    frames/          les images à lire (une par coupe, une par seconde, deux par seconde sur 0-5 s)
    meta.json        plateforme, auteur, date, légende, likes, commentaires, vues si connues

Usage :
    python3 tools/cloner_reel.py "<lien ou fichier vidéo>" [--largeur 768] [--langue en] [--refaire]
    python3 tools/cloner_reel.py installer     # crée .reel-cloneur-venv/ avec yt-dlp (une fois)
    python3 tools/cloner_reel.py verifier      # contrôle des outils (smoke test)

Règles : jamais de cookies ni de connexion au compte du client ; si un lien ne se télécharge pas,
l'outil le dit simplement et propose de glisser le fichier vidéo à la place. Relancer l'outil sur
le même lien reprend le même dossier sans refaire ce qui est déjà fait (--refaire pour tout refaire).

Python 3.9+ standard (macOS fournit 3.9). yt-dlp, lui, vit dans .reel-cloneur-venv/ avec un Python
3.10 ou plus : les versions récentes, les seules qui savent encore lire Instagram, l'exigent.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import unicodedata

# Windows : une sortie lue par l'agent (redirigée) est en cp1252, et un « ✅ » y fait planter l'outil.
for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

WIN = os.name == "nt"
OUTILS = pathlib.Path(__file__).resolve().parent


def maison_de(depart: pathlib.Path):
    """Le dossier Monteur IA qui contient `depart` : celui qui porte templates/AGENT.md.tpl."""
    for d in (depart, *depart.parents):
        if (d / "templates" / "AGENT.md.tpl").is_file():
            return d
    return None


MAISON = maison_de(OUTILS) or OUTILS.parent
CLONES = MAISON / "clones"
VENV = MAISON / ".reel-cloneur-venv"
YTDLP_PAQUET = "yt-dlp[default,curl-cffi]"
YTDLP_VERSION_MIN = "2026.07.01"     # en dessous, Instagram ne se télécharge plus sans connexion
MAJ_STAMP = VENV / ".derniere-mise-a-jour"
MAJ_INTERVALLE = 12 * 3600           # yt-dlp vérifié au plus toutes les 12 h (et toujours après un échec)

SCENE_SEUIL = 0.3
PLAFOND_IMAGES = 60
ECART_MIN = 0.35                     # deux images plus proches que ça : on n'en garde qu'une
FICHIER_VIDEO = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp")


# ------------------------------------------------------------------ petits utilitaires
def dire(msg: str = "") -> None:
    print(msg, flush=True)


def arret(msg: str, code: int = 1) -> None:
    print(f"\n❌ {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def config() -> dict:
    for nom in ("brand.config.json", "brand.config.example.json"):
        p = MAISON / nom
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
    return {}


def binaire(cle: str, defaut: str):
    """Un exécutable : chemin de brand.config.json (env.<cle>) s'il existe, sinon celui du PATH."""
    v = (config().get("env") or {}).get(cle)
    if v and pathlib.Path(v).exists():
        return v
    if v and shutil.which(v):
        return shutil.which(v)
    trouve = shutil.which(defaut)
    if trouve:
        return trouve
    # Homebrew n'est pas toujours dans le PATH d'un agent lancé depuis une app.
    for prefixe in ("/opt/homebrew/bin", "/usr/local/bin"):
        p = pathlib.Path(prefixe) / defaut
        if p.exists():
            return str(p)
    return None


def ffprobe_de(ffmpeg: str) -> str:
    p = pathlib.Path(ffmpeg)
    cand = p.with_name(p.name.replace("ffmpeg", "ffprobe"))
    return str(cand) if cand.exists() else (shutil.which("ffprobe") or "ffprobe")


def lancer(cmd, timeout=None, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, **kw)


def slugifier(texte: str, longueur: int = 40) -> str:
    t = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:longueur].strip("-") or "video"


def ecrire_json(chemin: pathlib.Path, donnees) -> None:
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lire_json(chemin: pathlib.Path):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def mmss(t: float) -> str:
    t = max(0.0, float(t))
    return f"{int(t // 60)}:{t % 60:04.1f}"


# ------------------------------------------------------------------ yt-dlp (venv dédié)
def venv_bin(nom: str) -> pathlib.Path:
    return VENV / ("Scripts" if WIN else "bin") / (nom + (".exe" if WIN else ""))


def version_python(exe: str):
    try:
        r = lancer([exe, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], timeout=20)
        if r.returncode == 0:
            maj, mineur = r.stdout.strip().split(".")
            return int(maj), int(mineur)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def python_recent():
    """Un Python 3.10+ pour le venv. macOS fournit 3.9 : on cherche celui de Homebrew ou d'python.org."""
    candidats = [sys.executable]
    noms = ["python3.13", "python3.12", "python3.11", "python3.14", "python3.10", "python3", "python"]
    for nom in noms:
        p = shutil.which(nom)
        if p:
            candidats.append(p)
    for prefixe in ("/opt/homebrew/bin", "/usr/local/bin", "/Library/Frameworks/Python.framework/Versions/Current/bin"):
        for nom in noms:
            p = pathlib.Path(prefixe) / nom
            if p.exists():
                candidats.append(str(p))
    if WIN and shutil.which("py"):
        for v in ("3.13", "3.12", "3.11", "3.10"):
            r = lancer(["py", f"-{v}", "-c", "import sys; print(sys.executable)"], timeout=20)
            if r.returncode == 0 and r.stdout.strip():
                candidats.append(r.stdout.strip())
    vus = set()
    for c in candidats:
        if c in vus:
            continue
        vus.add(c)
        v = version_python(c)
        if v and v >= (3, 10):
            return c
    return None


def version_ytdlp(exe) -> str:
    try:
        r = lancer([exe, "--version"], timeout=60)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def assez_recent(version: str) -> bool:
    def cle(v):
        return tuple(int(x) for x in re.findall(r"\d+", v)[:3])
    return bool(version) and cle(version) >= cle(YTDLP_VERSION_MIN)


def ytdlp_exe():
    """yt-dlp du venv dédié ; à défaut, un yt-dlp du système assez récent."""
    p = venv_bin("yt-dlp")
    if p.exists():
        return str(p)
    systeme = binaire("ytDlp", "yt-dlp")
    if systeme and assez_recent(version_ytdlp(systeme)):
        return systeme
    return None


def mettre_a_jour_ytdlp(forcer: bool = False) -> None:
    """Instagram et TikTok changent souvent : yt-dlp se tient à jour tout seul (sans bloquer si hors ligne)."""
    py = venv_bin("python")
    if not py.exists():
        return
    if not forcer and MAJ_STAMP.exists() and time.time() - MAJ_STAMP.stat().st_mtime < MAJ_INTERVALLE:
        return
    try:
        r = lancer([py, "-m", "pip", "install", "--upgrade", "--quiet", "--disable-pip-version-check",
                    YTDLP_PAQUET], timeout=180)
        if r.returncode == 0:
            MAJ_STAMP.write_text(datetime.datetime.now().isoformat())
    except (OSError, subprocess.SubprocessError):
        pass


def installer() -> None:
    dire("Reel Cloneur : installation du téléchargeur de vidéos (yt-dlp)…")
    py = venv_bin("python")
    if py.exists() and not (version_python(str(py)) or (0, 0)) >= (3, 10):
        dire("• ancien environnement (Python trop ancien) : je le recrée")
        shutil.rmtree(VENV, ignore_errors=True)
    if not py.exists():
        base = python_recent()
        if not base:
            conseil = ("brew install python@3.12" if sys.platform == "darwin"
                       else "winget install -e --id Python.Python.3.12" if WIN
                       else "sudo apt install python3.12-venv")
            arret("Il faut un Python 3.10 ou plus récent pour le téléchargeur (celui de ton ordinateur est "
                  f"plus ancien). Installe-le avec : {conseil}\npuis relance : python3 tools/cloner_reel.py "
                  "installer", 3)
        dire(f"• Python utilisé : {base}")
        r = lancer([base, "-m", "venv", str(VENV)], timeout=300)
        if r.returncode != 0:
            arret("Impossible de créer l'environnement .reel-cloneur-venv/ :\n" + (r.stderr or r.stdout)[-800:]
                  + ("\nSur Linux : sudo apt install python3-venv" if sys.platform.startswith("linux") else ""))
    r = lancer([py, "-m", "pip", "install", "--upgrade", "--quiet", "--disable-pip-version-check",
                YTDLP_PAQUET], timeout=600)
    if r.returncode != 0:
        arret("L'installation de yt-dlp a échoué (connexion internet ?) :\n" + (r.stderr or r.stdout)[-800:])
    MAJ_STAMP.write_text(datetime.datetime.now().isoformat())
    v = version_ytdlp(venv_bin("yt-dlp"))
    curl = lancer([py, "-c", "import curl_cffi"], timeout=60).returncode == 0
    dire(f"✅ yt-dlp {v} installé dans .reel-cloneur-venv/ (curl_cffi : {'oui' if curl else 'NON'})")
    if not assez_recent(v):
        arret(f"yt-dlp {v} est trop ancien (il faut {YTDLP_VERSION_MIN} ou plus).")


# ------------------------------------------------------------------ vérification (smoke test)
def verifier() -> int:
    lignes = []

    def ligne(ok, quoi, detail):
        lignes.append((ok, quoi, detail))

    ffmpeg = binaire("ffmpegPath", "ffmpeg")
    ligne(bool(ffmpeg), "ffmpeg", ffmpeg or "introuvable")
    if ffmpeg:
        fp = ffprobe_de(ffmpeg)
        ligne(bool(shutil.which(fp) or pathlib.Path(fp).exists()), "ffprobe", fp)
    w = binaire("whisperCli", "whisper-cli")
    ligne(bool(w), "whisper-cli", w or "introuvable")
    m = modele_whisper()
    ligne(bool(m), "modèle Whisper", m or "introuvable (env.whisperModel de brand.config.json)")
    y = ytdlp_exe()
    v = version_ytdlp(y) if y else ""
    ligne(bool(y) and assez_recent(v), "yt-dlp", f"{v} ({y})" if y else "absent : python3 tools/cloner_reel.py installer")
    if venv_bin("python").exists():
        curl = lancer([venv_bin("python"), "-c", "import curl_cffi"], timeout=60).returncode == 0
        ligne(curl, "curl_cffi", "ok" if curl else "absent : relance l'installation")
    node = binaire("nodePath", "node")
    ligne(bool(node), "node (YouTube)", node or "introuvable")
    ok_global = all(ok for ok, _, _ in lignes)
    if ok_global and ffmpeg and w and m:
        # Mini-chaîne réelle : 2 s de vidéo de test → audio → Whisper → détection de coupes.
        test = CLONES / "_test"
        test.mkdir(parents=True, exist_ok=True)
        try:
            r1 = lancer([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x568:rate=30:d=2",
                         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", "-pix_fmt", "yuv420p",
                         test / "media.mp4"], timeout=120)
            r2 = lancer([ffmpeg, "-y", "-v", "error", "-i", test / "media.mp4", "-ac", "1", "-ar", "16000",
                         test / "audio.wav"], timeout=120)
            r3 = lancer([w, "-m", m, "-f", test / "audio.wav", "-l", "auto", "-np", "-oj", "-of",
                         test / "w"], timeout=300)
            ok = r1.returncode == 0 and r2.returncode == 0 and r3.returncode == 0 and (test / "w.json").exists()
            ligne(ok, "chaîne vidéo → audio → texte", "ok" if ok else (r1.stderr + r2.stderr + r3.stderr)[-300:])
        finally:
            shutil.rmtree(test, ignore_errors=True)
    dire("Reel Cloneur : vérification des outils")
    for ok, quoi, detail in lignes:
        dire(f"  {'✅' if ok else '❌'} {quoi} : {detail}")
    ok_global = all(ok for ok, _, _ in lignes)
    dire("ok" if ok_global else "\nAu moins un outil manque (voir ❌ ci-dessus).")
    return 0 if ok_global else 1


# ------------------------------------------------------------------ source : lien ou fichier
MOTIFS_ID = [
    ("instagram", re.compile(r"instagram\.com/(?:[\w.]+/)?(?:reel|reels|p|tv)/([\w-]+)")),
    ("tiktok", re.compile(r"tiktok\.com/.*?/(?:video|photo)/(\d+)")),
    ("youtube", re.compile(r"youtube\.com/shorts/([\w-]{11})")),
    ("youtube", re.compile(r"[?&]v=([\w-]{11})")),
    ("youtube", re.compile(r"youtu\.be/([\w-]{11})")),
]


def id_du_lien(url: str):
    for plateforme, motif in MOTIFS_ID:
        m = motif.search(url)
        if m:
            return plateforme, m.group(1)
    return None, None


def clone_existant(plateforme, ident, source):
    if not CLONES.exists():
        return None
    for meta_p in sorted(CLONES.glob("*/meta.json")):
        meta = lire_json(meta_p) or {}
        if ident and meta.get("plateforme") == plateforme and meta.get("id") == ident:
            return meta_p.parent
        if source and meta.get("source") == source:
            return meta_p.parent
    return None


def erreur_telechargement(texte: str) -> str:
    t = texte.lower()
    if "private" in t or "privé" in t:
        return "Cette vidéo est privée : elle ne se télécharge pas sans connexion au compte."
    if "login" in t or "cookies" in t or "sign in" in t or "rate-limit" in t or "rate limit" in t:
        return ("La plateforme refuse de donner cette vidéo sans connexion : vidéo privée ou supprimée, lien "
                "incomplet, ou trop de téléchargements en ce moment.")
    if "unsupported url" in t:
        return "Ce lien n'est pas reconnu comme une vidéo (vérifie que c'est bien le lien du Reel, du TikTok ou du Short)."
    if "not available" in t or "unavailable" in t or "404" in t or "removed" in t:
        return "Cette vidéo n'est pas disponible (supprimée, réservée à certains pays ou à certains comptes)."
    if "unable to download" in t or "timed out" in t or "connection" in t or "resolve" in t:
        return "La connexion internet a coupé pendant le téléchargement."
    return "Le téléchargement n'a pas marché."


def telecharger(url: str, ffmpeg: str):
    """Télécharge le lien dans clones/_telechargement/ ; renvoie (dossier temporaire, info yt-dlp)."""
    y = ytdlp_exe()
    if not y:
        arret("Le téléchargeur n'est pas installé. Lance d'abord : python3 tools/cloner_reel.py installer")
    mettre_a_jour_ytdlp()
    tmp = CLONES / "_telechargement"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    cmd = [y, "--no-playlist", "--no-cookies", "--no-progress", "--retries", "3", "--socket-timeout", "30",
           "-S", "res:720,ext:mp4:m4a", "--merge-output-format", "mp4", "--remux-video", "mp4",
           "--ffmpeg-location", ffmpeg, "--write-info-json", "-o", str(tmp / "media.%(ext)s")]
    node = binaire("nodePath", "node")
    if node:
        cmd += ["--js-runtimes", f"node:{node}"]     # YouTube exige un moteur JavaScript ; Node est déjà là
    cmd.append(url)
    erreurs = ""
    for essai in (1, 2):
        try:
            r = lancer(cmd, timeout=600)
        except subprocess.TimeoutExpired:
            r = None
        video = tmp / "media.mp4"
        if r is not None and r.returncode == 0 and video.exists():
            info = lire_json(tmp / "media.info.json") or {}
            return tmp, info
        erreurs = (r.stderr + r.stdout) if r is not None else "timed out"
        if essai == 1:
            dire("• premier essai raté : je mets à jour le téléchargeur et je réessaie…")
            mettre_a_jour_ytdlp(forcer=True)
    shutil.rmtree(tmp, ignore_errors=True)
    # Le détail reste court : la fin du message de yt-dlp conseille des cookies, ce qu'on ne fait jamais.
    detail = next((l for l in reversed(erreurs.splitlines()) if "ERROR" in l), "")
    detail = re.split(r"\. (?=[A-Z])|; please", detail)[0][:220]
    arret(f"{erreur_telechargement(erreurs)}\n\n"
          "👉 Solution : enregistre la vidéo sur ton ordinateur ou ton téléphone (bouton « Enregistrer » de "
          "l'appli quand il existe, sinon un enregistrement d'écran pendant que le Reel passe), puis glisse le "
          "fichier vidéo dans la conversation et redis « clone ce Reel ».\n"
          f"(Détail technique : {detail or 'aucun'})", 2)


def nom_plateforme(info: dict, url: str) -> str:
    cle = (info.get("extractor_key") or info.get("extractor") or "").lower()
    for p in ("instagram", "tiktok", "youtube"):
        if p in cle or p in url:
            return p
    return cle or "web"


def meta_depuis_info(info: dict, url: str) -> dict:
    plateforme = nom_plateforme(info, url)
    date = info.get("upload_date")
    if not date and info.get("timestamp"):
        date = datetime.datetime.fromtimestamp(info["timestamp"], datetime.timezone.utc).strftime("%Y%m%d")
    # Le pseudo public (@…) : Instagram le met dans « channel », TikTok dans « uploader » (uploader_id y
    # est un numéro), YouTube dans « uploader_id » (« @pseudo »).
    compte = {"instagram": info.get("channel"), "tiktok": info.get("uploader")}.get(plateforme)
    compte = compte or info.get("uploader_id") or info.get("channel_id") or info.get("uploader")
    if plateforme == "youtube":
        compte = (info.get("uploader_id") or info.get("channel") or "").lstrip("@") or compte
    musique = None
    if info.get("track") or info.get("artist"):
        musique = " · ".join(x for x in (info.get("track"), info.get("artist")) if x)
    return {
        "source": url,
        "plateforme": plateforme,
        "id": info.get("id"),
        "lien": info.get("webpage_url") or url,
        "auteur": info.get("uploader") or info.get("channel"),
        "compte": compte,
        "titre": None if (info.get("title") or "").startswith("Video by ") else info.get("title"),
        "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}" if date else None,
        "legende": info.get("description"),
        "likes": info.get("like_count"),
        "commentaires": info.get("comment_count"),
        "vues": info.get("view_count"),
        "partages": info.get("repost_count"),
        "musique": musique,
        "hashtags": info.get("tags") or [],
    }


# ------------------------------------------------------------------ média
def sonde(ffmpeg: str, video: pathlib.Path) -> dict:
    r = lancer([ffprobe_de(ffmpeg), "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", video], timeout=60)
    d = json.loads(r.stdout or "{}") if r.returncode == 0 else {}
    flux = d.get("streams") or []
    v = next((s for s in flux if s.get("codec_type") == "video"), {})
    fps = None
    try:
        n, q = (v.get("r_frame_rate") or "0/1").split("/")
        fps = round(int(n) / int(q), 2) if int(q) else None
    except ValueError:
        pass
    return {"duree": round(float((d.get("format") or {}).get("duration") or 0), 2),
            "largeur": v.get("width"), "hauteur": v.get("height"), "fps": fps,
            "audio": any(s.get("codec_type") == "audio" for s in flux)}


def preparer_fichier(chemin: pathlib.Path, dossier: pathlib.Path, ffmpeg: str) -> None:
    cible = dossier / "media.mp4"
    if chemin.suffix.lower() == ".mp4":
        shutil.copy2(chemin, cible)
        return
    r = lancer([ffmpeg, "-y", "-v", "error", "-i", chemin, "-c", "copy", "-movflags", "+faststart", cible], timeout=600)
    if r.returncode != 0:
        r = lancer([ffmpeg, "-y", "-v", "error", "-i", chemin, "-vf", "scale='min(720,iw)':-2", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "23", "-c:a", "aac", cible], timeout=1800)
        if r.returncode != 0:
            arret(f"Je n'arrive pas à lire ce fichier vidéo ({chemin.name}). Essaie un autre format (.mp4 ou .mov).")


def extraire_audio(ffmpeg: str, dossier: pathlib.Path) -> None:
    r = lancer([ffmpeg, "-y", "-v", "error", "-i", dossier / "media.mp4", "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", dossier / "audio.wav"], timeout=600)
    if r.returncode != 0:
        arret("Extraction de l'audio impossible :\n" + r.stderr[-500:])


def modele_whisper():
    m = (config().get("env") or {}).get("whisperModel")
    if m and pathlib.Path(m).expanduser().exists():
        return str(pathlib.Path(m).expanduser())
    for d in (MAISON / "models", MAISON / "assets" / "models", pathlib.Path.home() / "whisper-models",
              pathlib.Path.home() / ".cache" / "whisper"):
        if d.exists():
            for nom in ("ggml-large-v3-turbo.bin", "ggml-medium.bin", "ggml-small.bin", "ggml-base.bin"):
                if (d / nom).exists():
                    return str(d / nom)
            autres = sorted(d.glob("ggml-*.bin"))
            if autres:
                return str(autres[0])
    return None


def langue_marque() -> str:
    c = config()
    return ((c.get("derush") or {}).get("whisperLanguage") or (c.get("brand") or {}).get("language") or "fr")


def secondes(horodatage: str) -> float:
    h, m, s = horodatage.replace(",", ".").split(":")
    return round(int(h) * 3600 + int(m) * 60 + float(s), 2)


def transcrire(dossier: pathlib.Path, langue_forcee):
    w = binaire("whisperCli", "whisper-cli")
    m = modele_whisper()
    if not w or not m:
        arret("Whisper (la transcription) est introuvable : vérifie env.whisperCli et env.whisperModel dans "
              "brand.config.json (c'est l'installation de Monteur IA qui les remplit).")
    audio = dossier / "audio.wav"
    langue, proba = langue_forcee, None
    if not langue:
        # Le Reel copié n'est pas forcément dans la langue du client : on détecte d'abord.
        r = lancer([w, "-m", m, "-f", audio, "-l", "auto", "-dl"], timeout=300)
        trouve = re.search(r"auto-detected language:\s*([a-z]{2,3})\s*\(p\s*=\s*([\d.]+)", r.stderr + r.stdout)
        if trouve and float(trouve.group(2)) >= 0.5:
            langue, proba = trouve.group(1), round(float(trouve.group(2)), 3)
        else:
            langue = langue_marque()
    sortie = dossier / "_whisper"
    # Phrases de 60 caractères au plus : assez fin pour horodater le script beat par beat.
    r = lancer([w, "-m", m, "-f", audio, "-l", langue, "-np", "-ml", "60", "-sow", "-oj", "-of", sortie],
               timeout=1800)
    brut = lire_json(sortie.with_suffix(".json"))
    sortie.with_suffix(".json").unlink(missing_ok=True)
    if r.returncode != 0 or brut is None:
        arret("La transcription a échoué :\n" + (r.stderr or "")[-500:])
    segments = []
    for s in brut.get("transcription") or []:
        texte = (s.get("text") or "").strip()
        if not texte or re.fullmatch(r"[\[(].*[\])]|♪+", texte):
            continue
        segments.append({"debut": secondes(s["timestamps"]["from"]), "fin": secondes(s["timestamps"]["to"]),
                         "texte": texte})
    transcript = {
        "langue": langue,
        "langueDetectee": proba is not None,
        "probabilite": proba,
        "modele": pathlib.Path(m).name,
        "segments": segments,
        "texte": " ".join(s["texte"] for s in segments),
        "_note": "Transcription automatique : peut contenir des fautes sur les noms propres. Le texte "
                 "à l'écran (frames/) fait foi quand il dit autre chose.",
    }
    ecrire_json(dossier / "transcript.json", transcript)
    return transcript


# ------------------------------------------------------------------ coupes et images
def detecter_coupes(ffmpeg: str, video: pathlib.Path, duree: float):
    r = lancer([ffmpeg, "-hide_banner", "-nostats", "-i", video, "-an", "-filter:v",
                f"select='gt(scene,{SCENE_SEUIL})',showinfo", "-f", "null", "-"], timeout=1800)
    coupes = []
    for t in re.findall(r"pts_time:([\d.]+)", r.stderr):
        t = float(t)
        if 0.15 < t < duree - 0.1 and (not coupes or t - coupes[-1] >= 0.25):
            coupes.append(round(t, 2))
    return coupes


def choisir_images(duree: float, coupes):
    """Une image juste après chaque coupe, 2/s sur 0-5 s, 1/s ensuite, la dernière ; 60 au plus."""
    fin = max(0.0, duree - 0.1)
    cand = [(min(c + 0.12, fin), "coupe") for c in coupes]
    t = 0.0
    while t < min(5.0, duree):
        cand.append((t, "debut"))
        t += 0.5
    t = 5.0
    while t < duree - 0.2:
        cand.append((t, "seconde"))
        t += 1.0
    cand.append((fin, "fin"))
    priorite = {"debut": 0, "coupe": 1, "fin": 2, "seconde": 3}
    gardees = []
    for t, raison in sorted(cand, key=lambda x: (priorite[x[1]], x[0])):
        if all(abs(t - g[0]) >= ECART_MIN for g in gardees):
            gardees.append((round(t, 2), raison))
    if len(gardees) > PLAFOND_IMAGES:
        fixes = [g for g in gardees if g[1] != "seconde"]
        libres = [g for g in gardees if g[1] == "seconde"]
        if len(fixes) > PLAFOND_IMAGES - 5:          # beaucoup de coupes : on espace les images de coupe
            debut = [g for g in fixes if g[1] == "debut"]
            reste = [g for g in fixes if g[1] != "debut"]
            pas = len(reste) / max(1, PLAFOND_IMAGES - len(debut))
            reste = [reste[int(i * pas)] for i in range(min(len(reste), PLAFOND_IMAGES - len(debut)))]
            gardees = debut + reste
        else:
            place = PLAFOND_IMAGES - len(fixes)
            pas = len(libres) / max(1, place)
            gardees = fixes + [libres[int(i * pas)] for i in range(min(place, len(libres)))]
    return sorted(gardees)


def extraire_images(ffmpeg: str, dossier: pathlib.Path, choix, largeur: int):
    frames = dossier / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    liste = []
    for i, (t, raison) in enumerate(choix):
        nom = f"f{i:02d}_{t:06.2f}s.jpg"
        r = lancer([ffmpeg, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", dossier / "media.mp4", "-frames:v", "1",
                    "-vf", f"scale={largeur}:-2", "-q:v", "3", frames / nom], timeout=120)
        if r.returncode == 0 and (frames / nom).exists():
            liste.append({"fichier": f"frames/{nom}", "t": t, "raison": raison})
    return liste


def analyser_plans(dossier: pathlib.Path, ffmpeg: str, largeur: int, media: dict) -> dict:
    duree = media["duree"]
    coupes = detecter_coupes(ffmpeg, dossier / "media.mp4", duree)
    bornes = [0.0] + coupes + [duree]
    plans = [{"n": i + 1, "debut": bornes[i], "fin": bornes[i + 1], "duree": round(bornes[i + 1] - bornes[i], 2)}
             for i in range(len(bornes) - 1)]
    moyenne = round(duree / len(plans), 2) if plans else duree
    images = extraire_images(ffmpeg, dossier, choisir_images(duree, coupes), largeur)
    rythme = ("très rapide" if moyenne < 1.5 else "rapide" if moyenne < 3 else "posé" if moyenne < 6
              else "plan quasi unique")
    shots = {
        "duree": duree,
        "seuilScene": SCENE_SEUIL,
        "coupes": coupes,
        "nbCoupes": len(coupes),
        "coupes0a3s": sum(1 for c in coupes if c <= 3),
        "coupes0a10s": sum(1 for c in coupes if c <= 10),
        "dureeMoyennePlan": moyenne,
        "planLePlusLong": max((p["duree"] for p in plans), default=duree),
        "rythme": rythme,
        "plans": plans,
        "largeurImages": largeur,
        "images": images,
        "_note": "Coupes détectées par changement d'image (seuil 0.3) : un zoom brusque ou un texte plein écran "
                 "compte comme une coupe, un fondu lent peut être manqué. Vérifie sur les images.",
    }
    ecrire_json(dossier / "shots.json", shots)
    return shots


# ------------------------------------------------------------------ le clonage
def cloner(source: str, largeur: int, langue, refaire: bool) -> None:
    debut = time.time()
    ffmpeg = binaire("ffmpegPath", "ffmpeg")
    if not ffmpeg:
        arret("ffmpeg est introuvable : c'est un outil de Monteur IA, relance son installation.")
    CLONES.mkdir(exist_ok=True)
    aujourdhui = datetime.date.today().isoformat()
    chemin = pathlib.Path(source.strip().strip("'\"")).expanduser()
    est_fichier = not re.match(r"https?://", source.strip()) and chemin.exists()
    if not est_fichier and not re.match(r"https?://", source.strip()):
        if chemin.suffix.lower() in FICHIER_VIDEO:
            arret(f"Je ne trouve pas ce fichier : {chemin}")
        source = "https://" + source.strip()

    if est_fichier:
        chemin = chemin.resolve()
        dossier = clone_existant(None, None, str(chemin))
        if dossier is None or refaire:
            dossier = dossier or CLONES / f"{aujourdhui}-fichier-{slugifier(chemin.stem)}"
            dossier.mkdir(parents=True, exist_ok=True)
            dire(f"• fichier : {chemin.name}")
            preparer_fichier(chemin, dossier, ffmpeg)
            meta = {"source": str(chemin), "plateforme": "fichier", "id": None, "lien": None,
                    "auteur": None, "compte": None, "titre": chemin.stem, "date": None, "legende": None,
                    "likes": None, "commentaires": None, "vues": None, "partages": None, "musique": None,
                    "hashtags": []}
            ecrire_json(dossier / "meta.json", meta)
        else:
            dire(f"• déjà cloné : je reprends {dossier.name}")
    else:
        url = source.strip()
        plateforme, ident = id_du_lien(url)
        dossier = clone_existant(plateforme, ident, url)
        if dossier is not None and (dossier / "media.mp4").exists() and not refaire:
            dire(f"• déjà téléchargé : je reprends {dossier.name}")
        else:
            dire(f"• téléchargement : {url}")
            t0 = time.time()
            tmp, info = telecharger(url, ffmpeg)
            meta = meta_depuis_info(info, url)
            if dossier is None:
                nom = "-".join(x for x in (aujourdhui, meta["plateforme"], slugifier(meta["compte"] or "", 30),
                                           slugifier(meta["id"] or "", 20)) if x)
                dossier = CLONES / nom
            dossier.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp / "media.mp4"), str(dossier / "media.mp4"))
            shutil.rmtree(tmp, ignore_errors=True)
            ecrire_json(dossier / "meta.json", meta)
            dire(f"  ok ({time.time() - t0:.1f} s)")
            for vieux in ("audio.wav", "transcript.json", "shots.json"):
                (dossier / vieux).unlink(missing_ok=True)

    meta = lire_json(dossier / "meta.json") or {}
    media = sonde(ffmpeg, dossier / "media.mp4")
    if not media["duree"]:
        arret("Cette vidéo semble vide ou abîmée (durée nulle).")

    t0 = time.time()
    if media["audio"]:
        if refaire or not (dossier / "audio.wav").exists():
            extraire_audio(ffmpeg, dossier)
        transcript = lire_json(dossier / "transcript.json")
        if refaire or langue or transcript is None:
            dire("• transcription…")
            transcript = transcrire(dossier, langue)
            dire(f"  ok ({time.time() - t0:.1f} s, langue : {transcript['langue']})")
    else:
        transcript = {"langue": None, "segments": [], "texte": "",
                      "_note": "Vidéo sans piste audio : tout passe par l'image et le texte à l'écran."}
        ecrire_json(dossier / "transcript.json", transcript)

    t0 = time.time()
    shots = lire_json(dossier / "shots.json")
    if refaire or shots is None or shots.get("largeurImages") != largeur or not (dossier / "frames").exists():
        dire("• coupes et images…")
        shots = analyser_plans(dossier, ffmpeg, largeur, media)
        dire(f"  ok ({time.time() - t0:.1f} s)")

    meta.update({"duree": media["duree"], "largeur": media["largeur"], "hauteur": media["hauteur"],
                 "fps": media["fps"], "dossier": str(dossier), "clonéLe": datetime.datetime.now().isoformat(timespec="seconds")})
    ecrire_json(dossier / "meta.json", meta)

    # ---- résumé court (l'IA lit ensuite les fichiers eux-mêmes)
    def n(v):
        return f"{v:,}".replace(",", " ") if isinstance(v, int) else "inconnu"
    dire("")
    dire(f"✅ Reel prêt à analyser : {dossier}")
    dire(f"   {meta.get('plateforme')} · {meta.get('compte') or meta.get('auteur') or '?'} · publié le "
         f"{meta.get('date') or '?'} · {media['duree']:.1f} s")
    dire(f"   vues {n(meta.get('vues'))} · likes {n(meta.get('likes'))} · commentaires {n(meta.get('commentaires'))}")
    dire(f"   {len(transcript.get('segments') or [])} phrases transcrites (langue : {transcript.get('langue')})")
    dire(f"   {shots['nbCoupes']} coupes (dont {shots['coupes0a3s']} sur 0-3 s, {shots['coupes0a10s']} sur 0-10 s), "
         f"plan moyen {shots['dureeMoyennePlan']} s, rythme {shots['rythme']}")
    dire(f"   {len(shots['images'])} images à lire dans frames/ ({largeur} px)")
    premiere = (transcript.get("segments") or [{}])[0].get("texte") if transcript.get("segments") else None
    if premiere:
        dire(f"   première phrase : « {premiere[:140]} »")
    dire(f"   durée totale : {time.time() - debut:.1f} s")
    dire("")
    dire("Étape suivante (pour l'IA) : lis TOUTES les images de frames/ et transcript.json, puis suis le skill reel-cloneur.")


def main() -> None:
    p = argparse.ArgumentParser(description="Reel Cloneur : prépare l'analyse d'un Reel (lien ou fichier).")
    p.add_argument("source", help="lien du Reel / TikTok / Short, chemin d'un fichier vidéo, ou « installer » / « verifier »")
    p.add_argument("--largeur", type=int, default=512, choices=[512, 768], help="largeur des images (512 par défaut)")
    p.add_argument("--langue", help="force la langue parlée (fr, en, es…) ; sinon détectée")
    p.add_argument("--refaire", action="store_true", help="refait tout, même ce qui est déjà prêt")
    a = p.parse_args()
    if a.source == "installer":
        installer()
    elif a.source in ("verifier", "vérifier"):
        sys.exit(verifier())
    else:
        cloner(a.source, a.largeur, a.langue, a.refaire)


if __name__ == "__main__":
    main()
