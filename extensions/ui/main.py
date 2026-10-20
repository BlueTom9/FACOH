import queue
import re
import threading
from pathlib import Path
from tkinter import TclError, messagebox

import customtkinter as ctk
from PIL import Image as PillowImage


class UI:
    def __init__(
        self,
        title="FACOH Window",
        width=800,
        height=600,
        theme="system",
        color="blue",
        resizable=True,
        resource_directory=None
    ):
        self._closed = False
        self._destroyed = False
        self._close_scheduled = False
        self._ui_thread_id = threading.get_ident()
        self._images = []
        self._variables = []
        self._pending_actions = queue.Queue()
        self._resource_directory = Path(
            resource_directory or Path.cwd()
        ).resolve()
        self._set_theme(theme, color)
        self.root = ctk.CTk()
        self.root.title(title)
        self.resize(width, height)
        self.root.resizable(resizable, resizable)
        self._close_action = None
        self.root.after(10, self._drain_actions)

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("This UI window has already been closed")
        if threading.get_ident() != self._ui_thread_id:
            raise RuntimeError(
                "UI operations must run on the UI thread; "
                "use call_soon() to schedule this operation"
            )
        try:
            exists = bool(self.root.winfo_exists())
        except TclError:
            exists = False
        if not exists:
            self._closed = True
            raise RuntimeError("This UI window has already been closed")

    @staticmethod
    def _validate_layout(layout):
        if layout not in ("pack", "grid", "place", "none"):
            raise ValueError("layout must be pack, grid, place, or none")

    def _drain_actions(self):
        if self._closed:
            return
        for _ in range(100):
            try:
                action, arguments, keyword_arguments = (
                    self._pending_actions.get_nowait()
                )
            except queue.Empty:
                break
            try:
                action(*arguments, **keyword_arguments)
            except Exception as error:  # noqa: BLE001
                self.root.report_callback_exception(
                    type(error),
                    error,
                    error.__traceback__
                )
            if self._closed:
                return
        try:
            self.root.after(10, self._drain_actions)
        except TclError:
            self._closed = True

    def _set_theme(self, theme, color):
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme(color)

    def _parent(self, parent):
        self._ensure_open()
        if parent is None:
            return self.root
        if isinstance(parent, UI):
            parent._ensure_open()
            return parent.root
        return parent

    def _create(self, widget_type, parent, layout, layout_options, **options):
        self._ensure_open()
        self._validate_layout(layout)
        normalized_options = (
            {} if layout_options is None else dict(layout_options)
        )
        widget = widget_type(self._parent(parent), **options)
        self.add(widget, layout, normalized_options)
        return widget

    def Button(
        self,
        text,
        action=None,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        return self._create(
            ctk.CTkButton,
            parent,
            layout,
            layout_options,
            text=text,
            command=action,
            **style
        )

    def Label(
        self,
        text,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        return self._create(
            ctk.CTkLabel,
            parent,
            layout,
            layout_options,
            text=text,
            **style
        )

    def Input(
        self,
        placeholder="",
        value="",
        on_change=None,
        on_enter=None,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        self._ensure_open()
        variable = ctk.StringVar(master=self.root, value=str(value))
        field = self._create(
            ctk.CTkEntry,
            parent,
            layout,
            layout_options,
            placeholder_text=placeholder,
            textvariable=variable,
            **style
        )
        self._variables.append(variable)
        if on_change is not None:
            variable.trace_add(
                "write",
                lambda *_: on_change(variable.get())
            )
        if on_enter is not None:
            def handle_enter(_event):
                on_enter()
                return "break"

            field.bind("<Return>", handle_enter)
        return field

    def Text(
        self,
        value="",
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        box = self._create(
            ctk.CTkTextbox,
            parent,
            layout,
            layout_options,
            **style
        )
        if value:
            box.insert("1.0", str(value))
        return box

    def Panel(
        self,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        return self._create(
            ctk.CTkFrame,
            parent,
            layout,
            layout_options,
            **style
        )

    def ScrollPanel(
        self,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        return self._create(
            ctk.CTkScrollableFrame,
            parent,
            layout,
            layout_options,
            **style
        )

    def Check(
        self,
        text,
        value=False,
        on_change=None,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        variable = ctk.BooleanVar(master=self.root, value=value)
        self._variables.append(variable)
        return self._create(
            ctk.CTkCheckBox,
            parent,
            layout,
            layout_options,
            text=text,
            variable=variable,
            onvalue=True,
            offvalue=False,
            command=(
                None if on_change is None
                else lambda: on_change(variable.get())
            ),
            **style
        )

    def Switch(
        self,
        text,
        value=False,
        on_change=None,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        variable = ctk.BooleanVar(master=self.root, value=value)
        self._variables.append(variable)
        return self._create(
            ctk.CTkSwitch,
            parent,
            layout,
            layout_options,
            text=text,
            variable=variable,
            command=(
                None if on_change is None
                else lambda: on_change(variable.get())
            ),
            **style
        )

    def Slider(
        self,
        minimum=0,
        maximum=1,
        value=0,
        on_change=None,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        slider = self._create(
            ctk.CTkSlider,
            parent,
            layout,
            layout_options,
            from_=minimum,
            to=maximum,
            command=on_change,
            **style
        )
        slider.set(value)
        return slider

    def Select(
        self,
        options,
        value=None,
        on_change=None,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        choices = list(options)
        if value is None:
            value = choices[0] if choices else ""
        return self._create(
            ctk.CTkOptionMenu,
            parent,
            layout,
            layout_options,
            values=choices,
            variable=ctk.StringVar(master=self.root, value=str(value)),
            command=on_change,
            **style
        )

    def Combo(
        self,
        options,
        value=None,
        on_change=None,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        choices = list(options)
        if value is None:
            value = choices[0] if choices else ""
        combo = self._create(
            ctk.CTkComboBox,
            parent,
            layout,
            layout_options,
            values=choices,
            command=on_change,
            **style
        )
        combo.set(value)
        return combo

    def Progress(
        self,
        value=0,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        progress = self._create(
            ctk.CTkProgressBar,
            parent,
            layout,
            layout_options,
            **style
        )
        progress.set(value)
        return progress

    def Tabs(
        self,
        names=(),
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        tabs = self._create(
            ctk.CTkTabview,
            parent,
            layout,
            layout_options,
            **style
        )
        for name in names:
            tabs.add(name)
        return tabs

    def Image(
        self,
        path,
        width,
        height,
        dark_path=None,
        parent=None,
        layout="pack",
        layout_options=None,
        **style
    ):
        self._ensure_open()
        self._validate_layout(layout)
        light_path = self._resolve_image_path(path)
        with PillowImage.open(light_path) as source_image:
            light_image = source_image.convert("RGBA")
        if dark_path is None:
            dark_image = light_image
        else:
            resolved_dark_path = self._resolve_image_path(dark_path)
            with PillowImage.open(resolved_dark_path) as source_image:
                dark_image = source_image.convert("RGBA")
        image = ctk.CTkImage(
            light_image=light_image,
            dark_image=dark_image,
            size=(width, height)
        )
        widget = self._create(
            ctk.CTkLabel,
            parent,
            layout,
            layout_options,
            image=image,
            text="",
            **style
        )
        self._images.append((light_image, dark_image, image))
        return widget

    def _resolve_image_path(self, path):
        image_path = Path(path)
        if not image_path.is_absolute():
            image_path = self._resource_directory / image_path
        return image_path.resolve()

    def add(self, widget, layout="pack", options=None):
        self._ensure_open()
        self._validate_layout(layout)
        layout_options = {} if options is None else dict(options)
        if layout == "pack":
            layout_options.setdefault("padx", 8)
            layout_options.setdefault("pady", 6)
            widget.pack(**layout_options)
        elif layout == "grid":
            layout_options.setdefault("padx", 8)
            layout_options.setdefault("pady", 6)
            layout_options.setdefault("sticky", "ew")
            widget.grid(**layout_options)
        elif layout == "place":
            dimensions = {}
            for name in ("width", "height"):
                if name in layout_options:
                    dimensions[name] = layout_options.pop(name)
            if dimensions:
                widget.configure(**dimensions)
            widget.place(**layout_options)
            widget.lift()
        return widget

    def remove(self, widget):
        self._ensure_open()
        manager = widget.winfo_manager()
        if manager == "pack":
            widget.pack_forget()
        elif manager == "grid":
            widget.grid_forget()
        elif manager == "place":
            widget.place_forget()

    def clear(self, parent=None):
        self._ensure_open()
        container = self._parent(parent)
        for child in container.winfo_children():
            child.destroy()

    def row_weight(self, row, weight=1, parent=None):
        self._ensure_open()
        self._parent(parent).grid_rowconfigure(row, weight=weight)

    def column_weight(self, column, weight=1, parent=None):
        self._ensure_open()
        self._parent(parent).grid_columnconfigure(column, weight=weight)

    def set_title(self, title):
        self._ensure_open()
        self.root.title(title)

    def resize(self, width, height):
        if hasattr(self, "root"):
            self._ensure_open()
        self.root.geometry(f"{int(width)}x{int(height)}")

    def center(self):
        self._ensure_open()
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def set_theme(self, mode="system", color="blue"):
        self._ensure_open()
        self._set_theme(mode, color)

    def on_close(self, action):
        self._ensure_open()
        self._close_action = action
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

    def _handle_close(self):
        if self._close_scheduled or self._destroyed:
            return
        self._close_scheduled = True
        try:
            if self._close_action is not None:
                self._close_action()
        finally:
            self.close()

    def after(self, milliseconds, action):
        self._ensure_open()
        return self.root.after(milliseconds, action)

    def call_soon(self, action, *arguments, **keyword_arguments):
        """Schedule a callback on the UI thread; safe from worker threads."""
        if self._closed:
            raise RuntimeError("This UI window has already been closed")
        if not callable(action):
            raise TypeError("action must be callable")
        self._pending_actions.put((action, arguments, keyword_arguments))

    def ask(self, prompt, title="Input"):
        self._ensure_open()
        dialog = ctk.CTkInputDialog(text=prompt, title=title)
        return dialog.get_input()

    def message(self, text, title="Message"):
        self._ensure_open()
        return messagebox.showinfo(title, text, parent=self.root)

    def confirm(self, text, title="Confirm"):
        self._ensure_open()
        return messagebox.askyesno(title, text, parent=self.root)

    def hide(self):
        self._ensure_open()
        self.root.withdraw()

    def show(self):
        self._ensure_open()
        self.root.deiconify()

    def run(self):
        self._ensure_open()
        try:
            self.root.mainloop()
        finally:
            self._closed = True
            self._destroy()

    def close(self):
        if not self._closed:
            self._closed = True
            if threading.get_ident() != self._ui_thread_id:
                self._pending_actions.put((self.close, (), {}))
                self._closed = False
                return
            self._destroy()

    def _destroy(self):
        if self._destroyed:
            return
        self._closed = True
        self._destroyed = True
        try:
            self._cancel_shutdown_callbacks()
        except TclError:
            pass
        try:
            self.root.quit()
        except TclError:
            pass
        try:
            self.root.destroy()
        except TclError:
            pass
        finally:
            self._images.clear()
            self._variables.clear()

    def _cancel_shutdown_callbacks(self):
        callback_ids = self.root.tk.splitlist(
            self.root.tk.call("after", "info")
        )
        shutdown_callback = re.compile(
            r"(?<!\w)\d+_?(?:drain_actions|update|check_dpi_scaling)(?!\w)"
        )
        for callback_id in callback_ids:
            try:
                callback_info = self.root.tk.call(
                    "after", "info", callback_id
                )
            except TclError:
                continue
            callback_script = (
                callback_info[0]
                if isinstance(callback_info, (tuple, list))
                else callback_info
            )
            if not shutdown_callback.search(str(callback_script)):
                continue
            try:
                self.root.after_cancel(callback_id)
            except TclError:
                pass


def create_window(
    title="FACOH Window",
    width=800,
    height=600,
    theme="system",
    color="blue",
    resource_directory=None
):
    return UI(
        title,
        width,
        height,
        theme,
        color,
        resource_directory=resource_directory
    )


FUNCTIONS = {
    "create_window": create_window
}

OBJECTS = {
    "UI": UI
}
