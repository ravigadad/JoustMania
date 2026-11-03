"""Loads audio files on a background thread so the engine never stalls while reading one."""
import logging
import queue
import threading
from collections import namedtuple

from audio_samples import load_sample

logger = logging.getLogger(__name__)

LoadedSample = namedtuple("LoadedSample", ["path", "tag", "samples"])


class SampleLoader:
    def __init__(self):
        self.requests = queue.Queue()
        self.results = queue.Queue()
        self.thread = threading.Thread(target=self._run, name="SampleLoader", daemon=True)
        self.thread.start()

    def request(self, path, tag):
        """Queues a file to load. The tag comes back with the result, unchanged."""
        self.requests.put((path, tag))

    def completed(self):
        """Returns the loads finished since the last call. Samples are None for a file
        that couldn't be read."""
        loaded = []
        while True:
            try:
                loaded.append(self.results.get_nowait())
            except queue.Empty:
                return loaded

    def stop(self):
        """Finishes the loads already requested, then ends the thread."""
        self.requests.put(None)
        self.thread.join()

    def _run(self):
        while (request := self.requests.get()) is not None:
            path, tag = request
            self.results.put(LoadedSample(path, tag, self._load(path)))

    def _load(self, path):
        try:
            return load_sample(path)
        except (OSError, ValueError) as error:
            logger.error("Could not load audio file %s: %s", path, error)
            return None
