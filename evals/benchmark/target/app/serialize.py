import pickle

import yaml


def load_session(blob: bytes):
    return pickle.loads(blob)


def load_config(text: str):
    return yaml.load(text, Loader=yaml.Loader)


def load_defaults(text: str):
    return yaml.safe_load(text)
