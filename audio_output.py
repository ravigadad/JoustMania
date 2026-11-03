"""Opens an ALSA sound card for the audio engine and writes mixed blocks to it."""
import logging
import os

import alsaaudio

from audio_samples import OUTPUT_RATE

logger = logging.getLogger(__name__)


class OutputError(Exception):
    """The sound card couldn't be opened or stopped accepting audio."""


PI_HEADPHONE_CARD = "Headphones"


def choose_card(configured_card):
    """Returns the ALSA card id to open, or None for the system default device. Without
    a configured card, a USB adapter comes first, then a Pi 4's headphone jack."""
    if configured_card:
        return configured_card
    card_ids = alsaaudio.cards()
    usb_card = find_usb_card(card_ids)
    if usb_card is not None:
        return usb_card
    if PI_HEADPHONE_CARD in card_ids:
        return PI_HEADPHONE_CARD
    return None


def find_usb_card(card_ids, proc_asound="/proc/asound"):
    # The kernel's USB audio driver gives each of its cards a usbid file, and no other
    # driver does.
    for card_id in card_ids:
        if os.path.exists(os.path.join(proc_asound, card_id, "usbid")):
            return card_id
    return None


def device_name(card_id):
    # A card's "default" device converts rate and format in alsa-lib, which the Pi's
    # HDMI outputs need: their hardware accepts only IEC958 subframes.
    if card_id is None:
        return "default"
    return f"default:CARD={card_id}"


class AlsaOutput:
    def __init__(self, card_id, period_frames):
        try:
            self.pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_PLAYBACK,
                device=device_name(card_id),
                channels=2,
                rate=OUTPUT_RATE,
                format=alsaaudio.PCM_FORMAT_S16_LE,
                periodsize=period_frames,
                periods=4,
            )
        except alsaaudio.ALSAAudioError as error:
            raise OutputError(f"Could not open {device_name(card_id)}: {error}") from error

    def write(self, block):
        """Blocks until the device has room for the block, which paces the engine."""
        try:
            written = self.pcm.write(block.tobytes())
        except alsaaudio.ALSAAudioError as error:
            raise OutputError(f"Could not write audio: {error}") from error
        # pyalsaaudio recovers from an underrun itself and returns -EPIPE.
        if written < 0:
            logger.warning("Audio output underrun")

    def close(self):
        self.pcm.close()
