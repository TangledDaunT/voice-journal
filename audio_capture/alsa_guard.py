"""Read a named ALSA jack control without opening another recording stream."""

import ctypes
import ctypes.util
from functools import lru_cache


@lru_cache(maxsize=1)
def _alsa_library():
    lib = ctypes.CDLL(ctypes.util.find_library("asound") or "libasound.so.2")
    pointer = ctypes.c_void_p
    lib.snd_ctl_open.argtypes = [ctypes.POINTER(pointer), ctypes.c_char_p, ctypes.c_int]
    lib.snd_ctl_elem_value_malloc.argtypes = [ctypes.POINTER(pointer)]
    for name in ("snd_ctl_close", "snd_ctl_elem_value_free"):
        getattr(lib, name).argtypes = [pointer]
    lib.snd_ctl_elem_value_set_interface.argtypes = [pointer, ctypes.c_int]
    lib.snd_ctl_elem_value_set_name.argtypes = [pointer, ctypes.c_char_p]
    lib.snd_ctl_elem_read.argtypes = [pointer, pointer]
    lib.snd_ctl_elem_value_get_boolean.argtypes = [pointer, ctypes.c_uint]
    return lib


def jack_connected(card, control):
    lib = _alsa_library()
    pointer = ctypes.c_void_p
    ctl, value = pointer(), pointer()
    if lib.snd_ctl_open(ctypes.byref(ctl), f"hw:{card}".encode(), 0) < 0:
        return False
    try:
        if lib.snd_ctl_elem_value_malloc(ctypes.byref(value)) < 0:
            return False
        lib.snd_ctl_elem_value_set_interface(value, 0)  # SND_CTL_ELEM_IFACE_CARD
        lib.snd_ctl_elem_value_set_name(value, control.encode())
        if lib.snd_ctl_elem_read(ctl, value) < 0:
            return False
        return bool(lib.snd_ctl_elem_value_get_boolean(value, 0))
    finally:
        if value:
            lib.snd_ctl_elem_value_free(value)
        lib.snd_ctl_close(ctl)
