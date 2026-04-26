# RenPy MCP Bridge v2 — File-based IPC for live game control
# Place this file in your game/ directory to enable MCP live integration.
# The MCP server communicates via JSON files in game/_mcp/

init -999 python:
    import os as _mcp_os
    import json as _mcp_json
    import time as _mcp_time
    import traceback as _mcp_tb

    _mcp_dir = _mcp_os.path.join(renpy.config.gamedir, "_mcp")
    _mcp_cmd_file = _mcp_os.path.join(_mcp_dir, "cmd.json")
    _mcp_status_file = _mcp_os.path.join(_mcp_dir, "status.json")
    _mcp_last_poll = 0
    _mcp_poll_interval = 0.5  # seconds between polls
    _mcp_last_heartbeat = 0
    _mcp_heartbeat_interval = 3.0  # seconds between heartbeats

    # Playtest tracking state
    _mcp_tracking = {"active": False, "sessions": []}
    _mcp_last_tracked_label = None

    def _mcp_ensure_dir():
        if not _mcp_os.path.exists(_mcp_dir):
            _mcp_os.makedirs(_mcp_dir)

    def _mcp_write_status(data):
        """Write status JSON for MCP server to read."""
        _mcp_ensure_dir()
        try:
            tmp = _mcp_status_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _mcp_json.dump(data, f, ensure_ascii=False)
            # Atomic replace (os.replace is atomic on all platforms)
            _mcp_os.replace(tmp, _mcp_status_file)
        except Exception:
            renpy.log("MCP bridge: failed to write status: {}".format(
                _mcp_tb.format_exc()))

    def _mcp_read_command():
        """Read and consume a command from MCP server."""
        if not _mcp_os.path.exists(_mcp_cmd_file):
            return None
        try:
            with open(_mcp_cmd_file, "r", encoding="utf-8") as f:
                cmd = _mcp_json.load(f)
            _mcp_os.remove(_mcp_cmd_file)
            return cmd
        except Exception:
            renpy.log("MCP bridge: failed to read command: {}".format(
                _mcp_tb.format_exc()))
            return None

    def _mcp_handle_command(cmd):
        """Execute a command from MCP server."""
        action = cmd.get("action", "")
        result = {"action": action, "success": False, "time": _mcp_time.time()}

        if action == "ping":
            result["success"] = True
            result["message"] = "pong"

        elif action == "get_state":
            try:
                result["success"] = True
                result["current_label"] = renpy.get_filename_line()
                result["variables"] = {}

                def _mcp_serialize(val, depth=0):
                    if depth > 3:
                        return repr(val)
                    if isinstance(val, (bool, int, float, str, type(None))):
                        return val
                    if isinstance(val, type):
                        return repr(val)
                    # Duck-type check for dict-like (Ren'Py rebinds dict to RevertableDict)
                    if hasattr(val, "keys") and hasattr(val, "items"):
                        try:
                            return {"_type": "dict", "items": {str(k): _mcp_serialize(v, depth+1) for k, v in list(val.items())[:50]}}
                        except Exception:
                            renpy.log("MCP bridge: failed to serialize dict-like value: {}".format(_mcp_tb.format_exc()))
                            return repr(val)
                    # Duck-type for set-like
                    tn = type(val).__name__
                    if tn in ("set", "frozenset", "RevertableSet"):
                        try:
                            return {"_type": "set", "items": [_mcp_serialize(v, depth+1) for v in list(val)[:50]]}
                        except Exception:
                            renpy.log("MCP bridge: failed to serialize set-like value: {}".format(_mcp_tb.format_exc()))
                            return repr(val)
                    # Duck-type for list/tuple-like
                    if hasattr(val, "__iter__") and hasattr(val, "__len__") and not isinstance(val, (str, bytes)):
                        try:
                            t = "tuple" if tn == "tuple" else "list"
                            return {"_type": t, "items": [_mcp_serialize(v, depth+1) for v in list(val)[:50]]}
                        except Exception:
                            renpy.log("MCP bridge: failed to serialize list-like value: {}".format(_mcp_tb.format_exc()))
                            return repr(val)
                    return repr(val)

                import types as _mcp_types
                _mcp_skip = {"say", "menu", "renpy", "store", "config", "library",
                             "style", "persistent", "preferences", "define",
                             "os", "sys", "im", "ui", "audio", "gui", "build",
                             "achievement", "bubble", "director", "iap", "icon",
                             "layeredimage", "textshader", "updater", "anim"}
                for name in dir(store):
                    if name.startswith("_") or name in _mcp_skip:
                        continue
                    val = getattr(store, name, None)
                    if isinstance(val, (_mcp_types.ModuleType, _mcp_types.FunctionType,
                                        _mcp_types.BuiltinFunctionType, type)):
                        continue
                    # Skip non-data callables (partials, classes, etc.)
                    # but keep dict-likes (have keys) and primitives
                    if callable(val):
                        if isinstance(val, (bool, int, float, str)):
                            pass  # keep primitives
                        elif hasattr(val, "keys") and hasattr(val, "items"):
                            pass  # keep dict-like
                        else:
                            continue
                    try:
                        result["variables"][name] = _mcp_serialize(val)
                    except Exception:
                        renpy.log("MCP bridge: failed to serialize variable '{}': {}".format(name, _mcp_tb.format_exc()))
                        result["variables"][name] = repr(val)[:200]
            except Exception as e:
                renpy.log("MCP bridge: failed to get_state: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "screenshot":
            try:
                _mcp_ensure_dir()
                target = _mcp_os.path.join(_mcp_dir, "screenshot.png")
                iface = renpy.game.interface
                if getattr(iface, 'surftree', None):
                    iface.save_screenshot(target)
                    result["success"] = True
                    result["path"] = target
                else:
                    result["error"] = "Display not ready (no surftree)"
            except Exception as e:
                renpy.log("MCP bridge: failed to take screenshot: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "eval":
            expr = cmd.get("expression", "")
            try:
                try:
                    val = eval(expr)
                    result["success"] = True
                    result["result"] = repr(val)
                except SyntaxError:
                    exec(expr, vars(store))
                    result["success"] = True
                    result["result"] = "OK"
            except Exception as e:
                renpy.log("MCP bridge: failed to evaluate expression '{}': {}".format(expr, _mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "notify":
            message = cmd.get("message", "MCP")
            try:
                renpy.notify(message)
                result["success"] = True
            except Exception as e:
                renpy.log("MCP bridge: failed to notify: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "jump":
            label = cmd.get("label", "start")
            try:
                target_node = renpy.game.script.namemap.get(label)
                if target_node is None:
                    result["error"] = "Label '{}' not found".format(label)
                else:
                    # Build warp spec (filename:line) for Ren'Py's built-in warp
                    fname = target_node.filename
                    if fname.startswith("game/"):
                        fname = fname[5:]
                    spec = "{}:{}".format(fname, target_node.linenumber)
                    renpy.session["_mcp_pending_warp_spec"] = spec
                    result["success"] = True
                    result["message"] = "Warp to '{}' ({}) queued".format(label, spec)
            except Exception as e:
                renpy.log("MCP bridge: failed to warp to '{}': {}".format(label, _mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "set_variable":
            name = cmd.get("name", "")
            value_str = cmd.get("value", "")
            try:
                if not name.isidentifier() or name.startswith("_"):
                    result["error"] = "Invalid variable name: {}".format(name)
                else:
                    # Use ast.literal_eval for safe parsing of Python literals
                    import ast as _mcp_ast
                    val = _mcp_ast.literal_eval(value_str)
                    setattr(store, name, val)
                    result["success"] = True
                    result["result"] = "{} = {}".format(name, repr(getattr(store, name)))
            except (ValueError, SyntaxError) as e:
                result["error"] = "Invalid value (must be a Python literal): {}".format(e)
            except Exception as e:
                renpy.log("MCP bridge: failed to set variable '{}': {}".format(name, _mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "get_styles":
            target = cmd.get("target", "")
            try:
                if target:
                    s = getattr(style, target, None)
                    if s is None:
                        result["error"] = "Style '{}' not found".format(target)
                    else:
                        props = {}
                        for prop in s.properties():
                            try:
                                props[prop] = repr(getattr(s, prop))
                            except Exception:
                                renpy.log("MCP bridge: failed to read style property '{}': {}".format(prop, _mcp_tb.format_exc()))
                                pass
                        result["success"] = True
                        result["style"] = target
                        result["properties"] = props
                else:
                    styles = [s for s in dir(style) if not s.startswith('_') and not callable(getattr(style, s, None))]
                    result["success"] = True
                    result["styles"] = styles[:200]
            except Exception as e:
                renpy.log("MCP bridge: failed to get_styles: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "list_saves":
            try:
                slots = renpy.loadsave.list_slots(None)
                saves = []
                for slot in slots[:50]:
                    info = {"slot": slot}
                    json_data = renpy.loadsave.slot_json(slot)
                    if json_data:
                        info["data"] = json_data
                    mtime = renpy.loadsave.slot_mtime(slot)
                    if mtime:
                        info["mtime"] = mtime
                    saves.append(info)
                result["success"] = True
                result["saves"] = saves
            except Exception as e:
                renpy.log("MCP bridge: failed to list_saves: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "load_save_info":
            slot = cmd.get("slot", "")
            try:
                json_data = renpy.loadsave.slot_json(slot)
                screenshot_data = None
                ss = renpy.loadsave.slot_screenshot(slot)
                if ss:
                    import io as _mcp_io
                    import base64 as _mcp_b64
                    buf = _mcp_io.BytesIO()
                    renpy.display.pgrender.save_png(ss, buf)
                    screenshot_data = _mcp_b64.b64encode(buf.getvalue()).decode("ascii")
                result["success"] = True
                result["slot"] = slot
                result["json_data"] = json_data
                if screenshot_data:
                    result["screenshot_b64"] = screenshot_data
            except Exception as e:
                renpy.log("MCP bridge: failed to load_save_info: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "screen_hierarchy":
            screen_name = cmd.get("screen", "")
            try:
                if screen_name:
                    scr = renpy.get_screen(screen_name)
                    if scr:
                        def _dump_displayable(d, depth=0):
                            items = []
                            name = type(d).__name__
                            info = {"type": name, "depth": depth}
                            if hasattr(d, "style") and hasattr(d.style, "name"):
                                info["style"] = str(d.style.name) if d.style.name else ""
                            items.append(info)
                            children = []
                            if hasattr(d, "children"):
                                children = d.children
                            elif hasattr(d, "child") and d.child:
                                children = [d.child]
                            for c in children:
                                if c is not None:
                                    items.extend(_dump_displayable(c, depth + 1))
                            return items
                        tree = _dump_displayable(scr)
                        result["success"] = True
                        result["screen"] = screen_name
                        result["widget_count"] = len(tree)
                        result["tree"] = tree[:200]
                    else:
                        result["error"] = "Screen '{}' not currently shown".format(screen_name)
                else:
                    shown = []
                    layer = renpy.get_showing_tags("screens") if hasattr(renpy, "get_showing_tags") else []
                    for tag in layer:
                        shown.append(str(tag))
                    result["success"] = True
                    result["shown_screens"] = shown
            except Exception as e:
                renpy.log("MCP bridge: failed to read screen hierarchy: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "start_tracking":
            try:
                _mcp_tracking["active"] = True
                _mcp_tracking["sessions"].append({
                    "start_time": _mcp_time.time(),
                    "events": [],
                })
                result["success"] = True
                result["message"] = "Tracking started"
            except Exception as e:
                renpy.log("MCP bridge: failed to start_tracking: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "stop_tracking":
            try:
                _mcp_tracking["active"] = False
                # Close current session
                if _mcp_tracking["sessions"]:
                    _mcp_tracking["sessions"][-1]["end_time"] = _mcp_time.time()
                result["success"] = True
                result["message"] = "Tracking stopped"
            except Exception as e:
                renpy.log("MCP bridge: failed to stop_tracking: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "get_tracking":
            try:
                result["success"] = True
                result["active"] = _mcp_tracking["active"]
                result["sessions"] = _mcp_tracking["sessions"]
            except Exception as e:
                renpy.log("MCP bridge: failed to get_tracking: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        elif action == "clear_tracking":
            try:
                _mcp_tracking["active"] = False
                _mcp_tracking["sessions"] = []
                result["success"] = True
                result["message"] = "Tracking data cleared"
            except Exception as e:
                renpy.log("MCP bridge: failed to clear_tracking: {}".format(_mcp_tb.format_exc()))
                result["error"] = str(e)

        else:
            result["error"] = f"Unknown action: {action}"

        _mcp_write_status(result)

    def _mcp_poll_callback():
        """Called every interaction frame by RenPy — polls for MCP commands.

        periodic_callbacks are called with no arguments, every frame.
        We throttle to _mcp_poll_interval to avoid filesystem overhead.
        """
        global _mcp_last_poll, _mcp_last_heartbeat
        now = _mcp_time.time()
        if now - _mcp_last_poll < _mcp_poll_interval:
            return
        _mcp_last_poll = now

        cmd = _mcp_read_command()
        if cmd:
            _mcp_handle_command(cmd)
        elif now - _mcp_last_heartbeat >= _mcp_heartbeat_interval:
            _mcp_last_heartbeat = now
            _mcp_write_status({
                "action": "heartbeat",
                "success": True,
                "time": now,
                "message": "MCP bridge active",
            })

    # Register the polling callback using periodic_callbacks (called in event loop)
    config.periodic_callbacks.append(_mcp_poll_callback)

    def _mcp_tracking_callback():
        """Track label visits when tracking is active."""
        global _mcp_last_tracked_label
        if not _mcp_tracking["active"] or not _mcp_tracking["sessions"]:
            return
        try:
            loc = renpy.get_filename_line()
            if not loc:
                return
            # loc is (filename, line) — extract label from current node
            node = renpy.game.context().current
            label = getattr(node, "name", None) if node else None
            if not label:
                # Try to get label from filename_line
                label = str(loc)

            if label != _mcp_last_tracked_label:
                _mcp_last_tracked_label = label
                session = _mcp_tracking["sessions"][-1]
                session["events"].append({
                    "type": "label",
                    "label": str(label),
                    "time": _mcp_time.time(),
                })
        except Exception:
            renpy.log("MCP bridge: failed to record tracking callback: {}".format(_mcp_tb.format_exc()))
            pass

    config.interact_callbacks.append(_mcp_tracking_callback)

    # Warp-style jump via periodic_callbacks — uses Ren'Py's built-in
    # warp mechanism (renpy.warp.warp()) which executes scene/show nodes
    # along the path for correct visual state (backgrounds, sprites, etc.)
    def _mcp_warp_check():
        spec = renpy.session.get("_mcp_pending_warp_spec")
        if spec:
            del renpy.session["_mcp_pending_warp_spec"]
            renpy.warp.warp_spec = spec
            raise renpy.game.FullRestartException(reason=(None, "_invoke_main_menu", "_main_menu"))

    config.periodic_callbacks.append(_mcp_warp_check)

    # Enable autoreload — detects .rpy changes every ~1.5s via mtime polling
    renpy.set_autoreload(True)

    # Add _mcp/ to autoreload blacklist to avoid reload loops from IPC files
    _mcp_blacklist_ext = [".json", ".json.tmp", ".png"]
    for ext in _mcp_blacklist_ext:
        if ext not in config.autoreload_blacklist:
            config.autoreload_blacklist.append(ext)

    # Write initial status
    _mcp_ensure_dir()
    _mcp_write_status({
        "action": "init",
        "success": True,
        "time": _mcp_time.time(),
        "message": "MCP bridge active",
        "autoreload": True,
        "poll_interval": _mcp_poll_interval,
    })
