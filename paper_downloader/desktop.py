"""Keep the remote browser window usable on a desktop that has no taskbar.

Chrome draws its own minimize and restore buttons. With no taskbar to bring a minimized window
back, a person could lose the browser, so the watcher restores and re-maximizes it.
"""

from Xlib import X, display, protocol

SOURCE_APPLICATION = 1


def _send(root, window, message_type, data) -> None:
    event = protocol.event.ClientMessage(window=window, client_type=message_type, data=(32, data))
    root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)


def keep_windows_usable(display_name: str) -> int:
    """Restore minimized browser windows and maximize normal ones; returns how many were fixed."""
    d = display.Display(display_name)
    try:
        root = d.screen().root
        atom = d.intern_atom
        clients = root.get_full_property(atom("_NET_CLIENT_LIST"), X.AnyPropertyType)
        hidden, vert, horz = atom("_NET_WM_STATE_HIDDEN"), atom("_NET_WM_STATE_MAXIMIZED_VERT"), atom("_NET_WM_STATE_MAXIMIZED_HORZ")
        normal = atom("_NET_WM_WINDOW_TYPE_NORMAL")
        fixed = 0
        for wid in (clients.value if clients else []):
            window = d.create_resource_object("window", wid)
            wm_class = window.get_wm_class() or ()
            if not any("chrome" in part.lower() for part in wm_class):
                continue
            prop = window.get_full_property(atom("_NET_WM_STATE"), X.AnyPropertyType)
            state = set(prop.value) if prop else set()
            kinds = window.get_full_property(atom("_NET_WM_WINDOW_TYPE"), X.AnyPropertyType)
            is_normal = not kinds or normal in set(kinds.value)
            if hidden in state:
                _send(root, window, atom("_NET_ACTIVE_WINDOW"), [SOURCE_APPLICATION, X.CurrentTime, 0, 0, 0])
                fixed += 1
            elif is_normal and not {vert, horz} <= state:
                _send(root, window, atom("_NET_WM_STATE"), [1, vert, horz, SOURCE_APPLICATION, 0])  # 1 = add
                fixed += 1
        d.flush()
        return fixed
    finally:
        d.close()
