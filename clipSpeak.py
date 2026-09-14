# -*- coding: utf-8 -*-
import os
from typing import Optional, Tuple
import ui
import wx
import core
import api
import textInfos
from logHandler import log

try:
    import comtypes.client
except Exception:
    pass


def safe_get_clipboard_text() -> str:
    """Safely retrieves clipboard text via NVDA's native API."""
    try:
        text = api.getClipData()
        if text and isinstance(text, str):
            return text.strip()
    except Exception as e:
        log.error(f"ClipSpeak safe_get_clipboard_text error: {e}")
    return ""


def safe_set_clipboard_text(text: str) -> bool:
    """Safely sets clipboard text via wx.TheClipboard."""
    try:
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            return True
    except Exception as e:
        log.error(f"ClipSpeak safe_set_clipboard_text error: {e}")
    return False


class ClipSpeakActions(object):
    """
    Handles ClipSpeak keyboard shortcuts, smart dynamic announcements,
    universal append logic, and line/file count tracking.
    """
    def __init__(self, clip_manager_instance=None) -> None:
        self.clip_manager = clip_manager_instance

        self.audio_exts = {
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', 
            '.opus', '.m4b', '.caf', '.aiff', '.aif', '.amr', '.mid'
        }
        self.video_exts = {
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', 
            '.webm', '.3gp', '.m4v', '.mpg', '.mpeg', '.ts'
        }
        self.image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico', '.svg', '.tif', '.tiff'}
        self.ppt_exts = {'.ppt', '.pptx', '.pps', '.ppsx'}
        self.doc_exts = {'.doc', '.docx', '.rtf', '.odt'}
        self.excel_exts = {'.xls', '.xlsx', '.csv', '.ods'}

    def _is_clipspeak_enabled(self) -> bool:
        """Checks if ClipSpeak functionality is enabled in ClipManager config/settings."""
        if self.clip_manager and hasattr(self.clip_manager, 'clipspeak_enabled'):
            return self.clip_manager.clipspeak_enabled
        return True

    def _classify_extension(self, ext: str) -> str:
        ext = ext.lower()
        if ext == '.py':
            return ".py file"
        elif ext == '.lnk':
            return ".lnk file"
        elif ext == '.dll':
            return ".dll file"
        elif ext == '.txt':
            return "text file"
        elif ext in self.audio_exts:
            return "audio"
        elif ext in self.video_exts:
            return "video"
        elif ext in self.image_exts:
            return "image"
        elif ext in self.ppt_exts:
            return "PowerPoint presentation"
        elif ext in self.doc_exts:
            return "Word document"
        elif ext in self.excel_exts:
            return "Excel sheet"
        elif ext == '.pdf':
            return "PDF file"
        elif ext:
            return f"{ext} file"
        return "file"

    def _get_focused_file_type(self) -> Tuple[str, Optional[str]]:
        """Inspects current focused UI element to identify folders (with name) or file extensions."""
        try:
            obj = api.getFocusObject()
            if obj and hasattr(obj, 'name') and obj.name:
                name = obj.name.strip()
                # Check if focused item is a folder path or folder item
                if os.path.exists(name) and os.path.isdir(name):
                    folder_name = os.path.basename(os.path.normpath(name))
                    return f"{folder_name} folder", folder_name
                ext = os.path.splitext(name)[1].lower()
                if ext:
                    return self._classify_extension(ext), None
        except Exception as e:
            log.debug(f"Error getting focused file type: {e}")
        return "text", None

    def _get_clipboard_type_description(self) -> str:
        """
        Accurately inspects current Clipboard data to determine if it contains
        Folders (with Folder Name), specific File extensions, URL, or pure Text.
        """
        # 1. Check Native Explorer Files or Folders from ClipManager drop files handler
        if self.clip_manager and hasattr(self.clip_manager, '_get_native_clipboard_files'):
            try:
                native_files = self.clip_manager._get_native_clipboard_files()
                if native_files:
                    first_file = native_files[0]
                    if os.path.isdir(first_file):
                        folder_name = os.path.basename(os.path.normpath(first_file))
                        return f"{folder_name} folder" if folder_name else "folder"
                    ext = os.path.splitext(first_file)[1].lower()
                    return self._classify_extension(ext)
            except Exception as e:
                log.debug(f"Error checking native clipboard files: {e}")

        # 2. Inspect Text content (handles copied path strings and URLs)
        try:
            text_val = safe_get_clipboard_text()
            if text_val:
                clean_val = text_val.strip('"').strip("'").strip()
                if os.path.exists(clean_val):
                    if os.path.isdir(clean_val):
                        folder_name = os.path.basename(os.path.normpath(clean_val))
                        return f"{folder_name} folder" if folder_name else "folder"
                    ext = os.path.splitext(clean_val)[1].lower()
                    return self._classify_extension(ext)
                
                # Dynamic Web URL detection
                if clean_val.startswith(('http://', 'https://', 'www.')):
                    return "URL link"

                return "text"
        except Exception as e:
            log.error(f"ClipSpeak inspection error: {e}")

        # 3. Fallback to focused UI object
        focused_type, _ = self._get_focused_file_type()
        return focused_type if focused_type else "text"

    def copy(self, gesture) -> None:
        gesture.send()
        if not self._is_clipspeak_enabled():
            return

        history_active = getattr(self.clip_manager, 'history_enabled', False) if self.clip_manager else False

        def _announce():
            content_type = self._get_clipboard_type_description()
            msg = f"Copied {content_type} to clipboard history" if history_active else f"Copied {content_type}"
            ui.message(msg)

        core.callLater(200, _announce)

    def cut(self, gesture) -> None:
        gesture.send()
        if not self._is_clipspeak_enabled():
            return

        def _announce():
            content_type = self._get_clipboard_type_description()
            ui.message(f"Cut {content_type}")

        core.callLater(200, _announce)

    def paste(self, gesture) -> None:
        gesture.send()
        if not self._is_clipspeak_enabled():
            return

        def _announce():
            content_type = self._get_clipboard_type_description()
            ui.message(f"Pasted {content_type}")

        core.callLater(200, _announce)

    def undo(self, gesture) -> None:
        gesture.send()
        if self._is_clipspeak_enabled():
            ui.message("Undo")

    def redo(self, gesture) -> None:
        gesture.send()
        if self._is_clipspeak_enabled():
            ui.message("Redo")

    def selectAll(self, gesture) -> None:
        gesture.send()
        if not self._is_clipspeak_enabled():
            return

        def _announce():
            # 1. Text Editors (Notepad, Word, Edit Fields) -> Line Count
            try:
                obj = api.getFocusObject()
                if obj and hasattr(obj, 'textInfo'):
                    info = obj.textInfo(textInfos.POSITION_ALL)
                    text = info.text
                    if text:
                        lines = text.splitlines()
                        count = len(lines) if lines else 1
                        ui.message(f"Selected {count} lines")
                        return
            except Exception as e:
                log.debug(f"Error checking textInfo: {e}")

            # 2. Windows Explorer / Drives / Folders -> File & Folder Count
            try:
                shell = comtypes.client.CreateObject("Shell.Application")
                for window in shell.Windows():
                    try:
                        selected_items = window.Document.SelectedItems()
                        if selected_items and selected_items.Count > 0:
                            count = selected_items.Count
                            msg = f"Selected {count} item" if count == 1 else f"Selected {count} items"
                            ui.message(msg)
                            return
                    except Exception:
                        continue
            except Exception as e:
                log.debug(f"Error checking Shell Windows: {e}")

            ui.message("Selected All")

        core.callLater(150, _announce)

    def save(self, gesture) -> None:
        gesture.send()
        if self._is_clipspeak_enabled():
            focused_type, _ = self._get_focused_file_type()
            ui.message(f"Saved {focused_type}")

    def saveAll(self, gesture) -> None:
        gesture.send()
        if self._is_clipspeak_enabled():
            focused_type, _ = self._get_focused_file_type()
            ui.message(f"Save as {focused_type}")

    def append(self, gesture) -> None:
        if not self._is_clipspeak_enabled():
            gesture.send()
            return

        old_text = safe_get_clipboard_text()
        gesture.send()  # Perform normal copy/append trigger

        def _process_append():
            new_text = safe_get_clipboard_text()
            
            # Universal Appending for Unigram, Telegram, WhatsApp, Web, etc.
            if old_text and new_text and old_text != new_text and not new_text.startswith(old_text):
                combined_text = f"{old_text}\r\n{new_text}"
                safe_set_clipboard_text(combined_text)

            history_active = getattr(self.clip_manager, 'history_enabled', False) if self.clip_manager else False
            if self.clip_manager and hasattr(self.clip_manager, 'append_clipboard'):
                self.clip_manager.append_clipboard()

            content_type = self._get_clipboard_type_description()
            msg = f"Appended {content_type} to clipboard history" if history_active else f"Appended {content_type}"
            ui.message(msg)

        core.callLater(200, _process_append)