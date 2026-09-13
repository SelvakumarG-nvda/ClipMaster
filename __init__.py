# -*- coding: utf-8 -*-
import os
import sys
import time
import wx
import globalPluginHandler
import scriptHandler
import ui
from logHandler import log

dir_path = os.path.dirname(__file__)
if dir_path not in sys.path:
    sys.path.insert(0, dir_path)

# Importing ClipManager, ClipSpeak, ClipAnnounce, and ClipText modules
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


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = "ClipSpeakPlus"

    def __init__(self, *args, **kwargs):
        super(GlobalPlugin, self).__init__(*args, **kwargs)

        # Master toggle flag for ClipSpeakPlus add-on
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

        # Timer constant to prevent re-saving within 0.5 seconds (500ms)
        self._last_record_time = 0
        self.record_cooldown = 0.5  

        self.bind_custom_shortcut()

    def bind_custom_shortcut(self):
        """Binds dynamic shortcut for toggling clipboard history."""
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
        # Skip if called again within 0.5 seconds from the last recording
        if current_time - self._last_record_time < self.record_cooldown:
            return
        
        self._last_record_time = current_time

        if self.clip_manager_instance:
            try:
                self.clip_manager_instance.record_current_clipboard()
            except Exception as e:
                log.error(f"Trigger record clipboard error: {e}")

    @scriptHandler.script(
        gestures=["kb:nvda+control+numpadDelete", "kb:nvda+control+numpadDecimal"],
        description="Toggles ClipSpeak master state ON/OFF"
    )
    def script_toggleClipSpeakPlus(self, gesture):
        self.addon_enabled = not self.addon_enabled
        if self.addon_enabled:
            ui.message("ClipSpeak Activate")
        else:
            ui.message("ClipSpeak Deactivate")

    @scriptHandler.script(description="Toggles Clipboard History ON/OFF")
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

    @scriptHandler.script(gesture="kb:control+c", description="Copy content")
    def script_clipSpeakCopy(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.copy(gesture)
            wx.CallLater(300, self._trigger_record_clipboard)
        else:
            gesture.send()

    @scriptHandler.script(gesture="kb:control+v", description="Paste content")
    def script_clipSpeakPaste(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.paste(gesture)
        else:
            gesture.send()

    @scriptHandler.script(gesture="kb:control+x", description="Cut content")
    def script_clipSpeakCut(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.cut(gesture)
            wx.CallLater(300, self._trigger_record_clipboard)
        else:
            gesture.send()

    @scriptHandler.script(gesture="kb:control+shift+c", description="Append text")
    def script_clipSpeakAppend(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.append(gesture)
            if self.clip_manager_instance:
                wx.CallLater(300, self.clip_manager_instance.append_clipboard)
        else:
            gesture.send()

    @scriptHandler.script(gesture="kb:control+z", description="Undo operation")
    def script_clipSpeakUndo(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.undo(gesture)
        else:
            gesture.send()

    @scriptHandler.script(gesture="kb:control+y", description="Redo operation")
    def script_clipSpeakRedo(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.redo(gesture)
        else:
            gesture.send()

    @scriptHandler.script(gesture="kb:control+s", description="Save content")
    def script_clipSpeakSave(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.save(gesture)
        else:
            gesture.send()

    @scriptHandler.script(gesture="kb:control+shift+s", description="Save As content")
    def script_clipSpeakSaveAs(self, gesture):
        if self.addon_enabled and self.clip_speak_handler:
            self.clip_speak_handler.saveAll(gesture)
        else:
            gesture.send()

    @scriptHandler.script(gesture="kb:nvda+control+shift+/", description="Open Clipboard History UI Window")
    def script_openClipboardHistory(self, gesture):
        if self.addon_enabled and self.clip_manager_instance:
            self.clip_manager_instance.script_show_history_dialog(gesture)
        else:
            gesture.send()

    @scriptHandler.script(gesture="kb:nvda+control+\\", description="Shows detailed properties of focused file, folder, or drive in an Edit Box")
    def script_announceFileInfo(self, gesture):
        if self.addon_enabled and self.clip_announce_handler:
            self.clip_announce_handler.announce_file_info()
        else:
            gesture.send()