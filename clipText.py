# -*- coding: utf-8 -*-
import os
import time
import datetime
import api
import ui
from logHandler import log

class ClipTextHandler:
    def __init__(self, clip_manager_instance=None):
        self.clip_manager = clip_manager_instance
        self.base_dir = os.path.dirname(__file__)

    def _get_target_folder(self):
        try:
            today_str = datetime.datetime.now().strftime("%d %m %Y")
            target_path = os.path.join(self.base_dir, "text", today_str)
            if not os.path.exists(target_path):
                os.makedirs(target_path, exist_ok=True)
            return target_path
        except Exception as e:
            log.error(f"Error creating directory: {e}")
            return None

    def _get_next_file_path(self, folder_path, is_append=False):
        try:
            existing_files = [f for f in os.listdir(folder_path) if f.endswith(".txt")]
            count = len(existing_files) + 1
            
            prefix = f"{count:02d}"
            if is_append:
                filename = f"{prefix} text_appended.txt"
            else:
                filename = f"{prefix} text.txt"
                
            return os.path.join(folder_path, filename)
        except Exception as e:
            log.error(f"Error generating file path: {e}")
            return os.path.join(folder_path, "default_text.txt")

    def _get_clipboard_text(self):
        """Clipboard text கிடைக்க 3 முறை முயற்சி செய்யும் Retry Logic"""
        for _ in range(3):
            time.sleep(0.15)  # Windows Clipboard update ஆக அவகாசம்
            try:
                text = api.getClipData()
                if text and isinstance(text, str) and text.strip():
                    return text
            except Exception as e:
                log.error(f"Error getting clipboard data attempt: {e}")
        return ""

    def save_clipboard_text(self):
        text = self._get_clipboard_text()
        if not text:
            ui.message("The text is empty")
            return

        folder = self._get_target_folder()
        if not folder:
            return

        file_path = self._get_next_file_path(folder, is_append=False)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            ui.message("Copied text to clipboard")
            log.info(f"Saved clipboard text to {file_path}")
        except Exception as e:
            log.error(f"Failed to save clipboard text file: {e}")

    def append_clipboard_text(self):
        text = self._get_clipboard_text()
        if not text:
            ui.message("The text is empty")
            return

        folder = self._get_target_folder()
        if not folder:
            return

        file_path = self._get_next_file_path(folder, is_append=True)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            ui.message("Appended text saved to clipboard")
            log.info(f"Saved appended text to {file_path}")
        except Exception as e:
            log.error(f"Failed to save appended text file: {e}")