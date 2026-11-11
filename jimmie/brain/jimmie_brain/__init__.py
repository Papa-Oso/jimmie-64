"""Jimmie's brain: facts in, a decision about whether and what to say out.

Layers, each usable alone:
  corpus    real stream turns (retrieval, style fingerprint, training export)
  facts     normalised game events
  memory    what happened and what he actually said aloud
  rules     when a moment deserves a line, and what social move it is
  writer    new words in his voice, checked against the scene
  voice     recordings first, cloned voice for new lines
  director  the pool of ready lines and the plan the game executes instantly
  bridge    the running game <-> this process
"""
__version__ = "0.1.0"
