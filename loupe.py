#!/usr/bin/env python3
"""Loupe : sélectionnez une zone de l'écran, Claude l'analyse.

1. Sélection d'une zone à la souris (outil de capture macOS, Échap pour annuler)
2. Pop-up : Entrée = analyse rapide, ou taper une question
3. Réponse affichée dans un pop-up + copiée dans le presse-papiers
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import anthropic

MODEL = "claude-opus-5-5"
KEYCHAIN_SERVICE = "loupe-claude-api"
QUICK_PROMPT = (
    "Analyse rapide : en quelques lignes, dis ce que montre cette zone et "
    "l'information essentielle à en retenir."
)
MAX_POPUP_CHARS = 1500  # au-delà, le pop-up tronque (texte complet dans le presse-papiers)
SYSTEM = (
    "Tu es une loupe intelligente. L'utilisateur a sélectionné une zone de son écran. "
    "Analyse précisément son contenu (texte, code, graphique, interface, image, erreur...) "
    "et réponds à sa question en français, de façon claire et concise, en texte brut "
    "(pas de Markdown : ta réponse s'affiche dans une petite fenêtre). "
    "Si la zone contient du texte, tu peux le retranscrire quand c'est utile."
)


def osascript(script: str) -> str:
    r = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def notify(msg: str) -> None:
    osascript(f'display notification {json.dumps(msg)} with title "Loupe"')


def get_api_key() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    r = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True, text=True,
    )
    return r.stdout.strip() or None


def capture() -> str | None:
    path = os.path.join(tempfile.gettempdir(), f"loupe-{int(time.time())}.png")
    subprocess.run(["/usr/sbin/screencapture", "-i", "-x", path])
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None  # sélection annulée
    # Réduit les captures Retina (les très grandes images sont redimensionnées de toute façon)
    subprocess.run(["/usr/bin/sips", "-Z", "1800", path], capture_output=True)
    return path


def ask_question() -> str | None:
    """Renvoie la question tapée, "" si Entrée sur un champ vide, None si Annuler/Échap."""
    r = subprocess.run(
        ["/usr/bin/osascript", "-e",
         'set r to display dialog "Entrée = analyse rapide\nou tapez une question :" '
         'default answer "" with title "Loupe" '
         'buttons {"Annuler", "Analyser"} default button "Analyser" cancel button "Annuler"\n'
         'return text returned of r'],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def analyze(api_key: str, image_path: str, question: str, quick: bool) -> str:
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode()
    client = anthropic.Anthropic(api_key=api_key)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "low" if quick else "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                {"type": "text", "text": question},
            ],
        }],
    )
    if response.stop_reason == "refusal":
        return "_Claude a refusé d'analyser cette zone._"
    return "".join(b.text for b in response.content if b.type == "text")


def to_plain(text: str) -> str:
    """Retire le balisage Markdown éventuel pour un affichage propre dans le pop-up."""
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.M)
    return text.strip()


def show(answer: str, title: str) -> None:
    answer = to_plain(answer)
    subprocess.run(["/usr/bin/pbcopy"], input=answer, text=True)
    shown = answer
    if len(shown) > MAX_POPUP_CHARS:
        shown = shown[:MAX_POPUP_CHARS].rstrip() + "…\n\n(Réponse complète dans le presse-papiers)"
    osascript(
        f"display dialog {json.dumps(shown)} with title {json.dumps('Loupe — ' + title)} "
        f'buttons {{"OK"}} default button "OK" with icon note'
    )


def main() -> int:
    api_key = get_api_key()
    if not api_key:
        osascript('display alert "Loupe" message "Clé API introuvable. Relancez install.sh."')
        return 1
    image = capture()
    if not image:
        return 0
    question = ask_question()
    if question is None:
        os.remove(image)
        return 0
    quick = question == ""
    if quick:
        question = QUICK_PROMPT
    notify("Analyse rapide…" if quick else "Analyse en cours…")
    try:
        answer = analyze(api_key, image, question, quick)
    except anthropic.AuthenticationError:
        osascript('display alert "Loupe" message "Clé API refusée. Relancez install.sh avec une clé valide."')
        return 1
    except anthropic.APIConnectionError:
        osascript('display alert "Loupe" message "Impossible de joindre l\'API (connexion internet ?)."')
        return 1
    except anthropic.APIStatusError as e:
        osascript(f'display alert "Loupe" message {json.dumps(f"Erreur API {e.status_code} : {e.message}")}')
        return 1
    show(answer, "Analyse rapide" if quick else question)
    os.remove(image)
    return 0


if __name__ == "__main__":
    sys.exit(main())
