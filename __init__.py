# -*- coding: utf-8 -*-
import os
import sys
import time
import wx
import globalPluginHandler
import scriptHandler
import ui
import inputCore
from logHandler import log

dir_path = os.path.dirname(__file__)
if dir_path not in sys.path:
    sys.path.insert(0, dir_path)

# Safe imports for ClipMaster modules
clipManagerModule = None
try:
    import clipManager as clipManagerModule
except Exception as e:
    log.error(f"clipManager loading error: {e}")

clipSpeakModule = None
try:
    import clipSpeak as clipSpeakModule
except Exception as e:
    log.error(f"clipSpeak loading error: {e}")

clipAnnounceModule = None
try:
    import clipAnnounce as clipAnnounceModule
except Exception as e:
    log.error(f"clipAnnounce loading error: {e}")

clipTextModule = None
try:
    import clipText as clipTextModule
except Exception as e:
    log.error(f"clipText loading error: {e}")


# Numpad ON <-> OFF mappings (Handles both directions)
NUMPAD_PAIRS = {
    "numpaddelete": "numpaddecimal",
    "numpaddecimal": "numpaddelete",
    "numpadinsert": "numpad0",
    "numpad0": "numpadinsert",
    "numpadend": "numpad1",
    "numpad1": "numpadend",
    "numpaddown": "numpad2",
    "numpad2": "numpaddown",
    "numpadpagedown": "numpad3",
    "numpad3": "numpadpagedown",
    "numpadleft": "numpad4",
    "numpad4": "numpadleft",
    "numpadclear": "numpad5",
    "numpad5": "numpadclear",
    "numpadright": "numpad6",
    "numpad6": "numpadright",
    "numpadhome": "numpad7",
    "numpad7": "numpadhome",
    "numpadup": "numpad8",
    "numpad8": "numpadup",
    "numpadpageup": "numpad9",
    "numpad9": "numpadpageup"
}


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = "ClipMaster"

    # Default Gestures: NVDA Input Gestures Dialog dynamic overrides respect this list
    __gestures = {
        "kb:nvda+control+/": "toggleClipMaster",
        "kb:nvda+control+shift+\\": "toggleClipboardHistory",
        "kb:control+c": "clipSpeakCopy",
        "kb:control+v": "clipSpeakPaste",
        "kb:control+x": "clipSpeakCut",
        "kb:control+shift+c": "clipSpeakAppend",
        "kb:control+a": "clipSpeakSelectAll",
        "kb:control+z": "clipSpeakUndo",
        "kb:control+y": "clipSpeakRedo",
        "kb:control+s": "clipSpeakSave",
        "kb:control+shift+s": "clipSpeakSaveAs",
        "kb:nvda+control+shift+/": "openClipboardHistory",
        "kb:nvda+control+\\": "announceFileInfo",
    }

    def __init__(self, *args, **kwargs):
        super(GlobalPlugin, self).__init__(*args, **kwargs)

        self.addon_enabled = True

        self.clip_manager_instance = None
        if clipManagerModule and hasattr(clipManagerModule, 'ClipManager'):
            try:
                self.clip_manager_instance = clipManagerModule.ClipManager(plugin_instance=self)
            except Exception as e:
                log.error(f"ClipManager Init Error: {e}")

        self.clip_speak_handler = None
        if clipSpeakModule and hasattr(clipSpeakModule, 'ClipSpeakActions'):
            try:
                self.clip_speak_handler = clipSpeakModule.ClipSpeakActions(self.clip_manager_instance)
            except Exception as e:
                log.error(f"ClipSpeak Init Error: {e}")

        self.clip_announce_handler = None
        if clipAnnounceModule and hasattr(clipAnnounceModule, 'ClipAnnounceHandler'):
            try:
                self.clip_announce_handler = clipAnnounceModule.ClipAnnounceHandler(self.clip_manager_instance)
            except Exception as e:
                log.error(f"ClipAnnounce Init Error: {e}")

        self._last_record_time = 0
        self.record_cooldown = 0.5  

        self.bind_custom_shortcut()

    def getScript(self, gesture):
        """
        Dynamically searches script for pressed gesture.
        If NumLock state differs (ON vs OFF), auto-converts Numpad key to find bound script.
        """
        script = super(GlobalPlugin, self).getScript(gesture)
        if script:
            return script

        # Extract gesture identifiers
        try:
            identifiers = list(gesture.identifiers)
        except Exception:
            identifiers = []

        for identifier in identifiers:
            id_lower = identifier.lower()
            for off_k, on_k in NUMPAD_PAIRS.items():
                if off_k in id_lower:
                    # Swap NumLock state name in identifier string
                    alt_id = id_lower.replace(off_k, on_k)
                    try:
                        alt_gesture = inputCore.strToInputGesture(alt_id)
                        if alt_gesture:
                            script = super(GlobalPlugin, self).getScript(alt_gesture)
                            if script:
                                return script
                    except Exception:
                        pass
        return None

    def bind_custom_shortcut(self):
        """Binds dynamic custom shortcut configured in ClipManager settings."""
        if self.clip_manager_instance and hasattr(self.clip_manager_instance, 'toggle_shortcut'):
            sc = self.clip_manager_instance.toggle_shortcut.strip().lower()
            if sc:
                gesture_str = f"kb:{sc}"
                try:
                    self.bindGesture(gesture_str, "toggleClipboardHistory")
                except Exception as e:
                    log.error(f"Failed to bind custom gesture {gesture_str}: {e}")

    def _trigger_record_clipboard(self):
        """Safely retrieves and saves text/file in the background (with Duplicate Preventer)"""
        if not self.addon_enabled:
            return

        current_time = time.time()
        if current_time - self._last_record_time < self.record_cooldown:
            return
        
        self._last_record_time = current_time

        if self.clip_manager_instance:
            try:
                self.clip_manager_instance.record_current_clipboard()
            except Exception as e:
                log.error(f"Trigger record clipboard error: {e}")

    @scriptHandler.script(
        description="Toggles ClipMaster master state ON/OFF"
    )
    def script_toggleClipMaster(self, gesture):
        self.addon_enabled = not self.addon_enabled
        if self.addon_enabled:
            ui.message("ClipMaster Activate")
        else:
            ui.message("ClipMaster Deactivate")

    @scriptHandler.script(
        description="Toggles Clipboard History recording ON/OFF"
    )
    def script_toggleClipboardHistory(self, gesture):
        if not self.addon_enabled:
            gesture.send()
            return

        if self.clip_manager_instance:
            self.clip_manager_instance.history_enabled = not self.clip_manager_instance.history_enabled
            if self.clip_manager_instance.history_enabled:
                ui.message("Clipboard History On")
            else:
                ui.message("Clipboard History Off")
        else:
            gesture.send()

    @scriptHandler.script(
        description="Copies selected content and announces clip type"
    )
    def script_clipSpeakCopy(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.copy(gesture)
            wx.CallLater(300, self._trigger_record_clipboard)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Pastes clipboard content and announces action"
    )
    def script_clipSpeakPaste(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.paste(gesture)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Cuts selected content and announces action"
    )
    def script_clipSpeakCut(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.cut(gesture)
            wx.CallLater(300, self._trigger_record_clipboard)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Appends selected text to current clipboard content"
    )
    def script_clipSpeakAppend(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.append(gesture)
            if self.clip_manager_instance:
                wx.CallLater(300, self.clip_manager_instance.append_clipboard)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Selects all text or items and announces total count"
    )
    def script_clipSpeakSelectAll(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.selectAll(gesture)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Performs undo operation with announcement"
    )
    def script_clipSpeakUndo(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.undo(gesture)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Performs redo operation with announcement"
    )
    def script_clipSpeakRedo(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.redo(gesture)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Saves current file/document with announcement"
    )
    def script_clipSpeakSave(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.save(gesture)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Performs Save As operation with announcement"
    )
    def script_clipSpeakSaveAs(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.saveAll(gesture)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Opens the main Clipboard History user interface window"
    )
    def script_openClipboardHistory(self, gesture):
        if self.addon_enabled and self.clip_manager_instance:
            self.clip_manager_instance.script_show_history_dialog(gesture)
        else:
            gesture.send()

    @scriptHandler.script(
        description="Displays detailed properties of the focused item, folder, or drive"
    )
    def script_announceFileInfo(self, gesture):
        if self.addon_enabled and self.clip_announce_handler:
            self.clip_announce_handler.announce_file_info()
        else:
            gesture.send()