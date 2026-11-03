"""Describes the Linux sound outputs for the web UI's audio output choice."""
import os
import re

import runtime_platform

# A card's first line in /proc/asound/cards: index, [id], driver, then the card's name.
CARD_LINE = re.compile(r"^\s*\d+\s+\[(\S+)\s*\]:\s+(\S+)\s+-\s+(.+)$")


def status(selected_card):
    """Returns what the debug page shows: every output, the saved choice ("" for
    automatic), the card that is playing right now, and a sentence describing that."""
    if not runtime_platform.is_linux():
        return {"supported": False}
    outputs = list_outputs()
    playing = playing_card([output["card"] for output in outputs])
    return {
        "supported": True,
        "selected": selected_card or "",
        "outputs": outputs,
        "playing": playing,
        "message": status_message(selected_card, outputs, playing),
    }


def list_outputs(proc_asound="/proc/asound"):
    try:
        with open(os.path.join(proc_asound, "cards")) as cards:
            lines = cards.read().splitlines()
    except FileNotFoundError:
        return []
    outputs = []
    for line in lines:
        match = CARD_LINE.match(line)
        if match:
            card_id, driver, name = match.groups()
            outputs.append({"card": card_id, "driver": driver, "label": output_label(card_id, driver, name)})
    return outputs


def status_message(selected_card, outputs, playing):
    outputs_by_card = {output["card"]: output for output in outputs}
    if playing:
        return "Playing through " + outputs_by_card[playing]["label"]
    if not selected_card:
        return "No output is open"
    selected_output = outputs_by_card.get(selected_card)
    if selected_output is None:
        return f"Waiting for {selected_card}, which is not connected"
    if selected_output["driver"] == "vc4-hdmi":
        # The Pi's HDMI driver refuses to open a port with no display attached.
        return f"Waiting for {selected_output['label']}. An HDMI port plays sound only while a display is connected to it."
    return "Waiting for " + selected_output["label"]


def output_label(card_id, driver, name):
    if driver == "vc4-hdmi":
        return "HDMI " + card_id.removeprefix("vc4hdmi")
    if driver == "USB-Audio":
        return "USB: " + name
    if card_id == "Headphones":
        return "Headphone jack"
    return name


def playing_card(card_ids, proc_asound="/proc/asound"):
    """Returns the card whose playback stream is running, which is the card the audio
    engine actually opened, whatever was chosen."""
    for card_id in card_ids:
        try:
            with open(os.path.join(proc_asound, card_id, "pcm0p", "sub0", "status")) as playback:
                if "state: RUNNING" in playback.read():
                    return card_id
        except FileNotFoundError:
            continue
    return None
