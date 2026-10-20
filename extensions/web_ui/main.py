import html
import re

_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr"
}


class HTMLFragment(str):
    pass


def _attributes(attributes):
    rendered = []
    for name, value in attributes.items():
        if value is None or value is False:
            continue
        if name == "class_name":
            name = "class"
        if not re.fullmatch(r"[A-Za-z_:][A-Za-z0-9_.:-]*", name):
            raise ValueError(f"invalid HTML attribute name: {name}")
        if value is True:
            rendered.append(name)
        else:
            rendered.append(
                f'{name}="{html.escape(str(value), quote=True)}"'
            )
    return "" if not rendered else " " + " ".join(rendered)


class WebPage:
    def __init__(self, title="FACOH page", language="en"):
        self.title = str(title)
        self.language = str(language)
        self._body = []
        self._styles = []
        self._scripts = []
        self._head = []

    def add(self, content):
        if isinstance(content, HTMLFragment):
            self._body.append(str(content))
        else:
            self._body.append(html.escape(str(content)))
        return self

    def raw(self, markup):
        self._body.append(str(markup))
        return self

    def element(self, tag, content="", attributes=None):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", tag):
            raise ValueError("invalid HTML element name")
        values = {} if attributes is None else dict(attributes)
        opening = f"<{tag}{_attributes(values)}>"
        if tag.lower() in _VOID_ELEMENTS:
            if content:
                raise ValueError(f"{tag} cannot contain content")
            return HTMLFragment(opening)
        if isinstance(content, HTMLFragment):
            body = str(content)
        else:
            body = html.escape(str(content))
        return HTMLFragment(f"{opening}{body}</{tag}>")

    def heading(self, text, level=1, attributes=None):
        if level not in range(1, 7):
            raise ValueError("heading level must be between 1 and 6")
        return self.add(self.element(f"h{level}", text, attributes))

    def paragraph(self, text, attributes=None):
        return self.add(self.element("p", text, attributes))

    def link(self, text, url, attributes=None):
        values = {} if attributes is None else dict(attributes)
        values["href"] = url
        return self.add(self.element("a", text, values))

    def button(self, text, action=None, attributes=None):
        values = {} if attributes is None else dict(attributes)
        values.setdefault("type", "button")
        if action is not None:
            values["data-action"] = action
        return self.add(self.element("button", text, values))

    def input(self, name, input_type="text", value=None, placeholder=None,
              attributes=None):
        values = {} if attributes is None else dict(attributes)
        values.update({"name": name, "type": input_type})
        if value is not None:
            values["value"] = value
        if placeholder is not None:
            values["placeholder"] = placeholder
        return self.add(self.element("input", attributes=values))

    def image(self, source, alternative="", attributes=None):
        values = {} if attributes is None else dict(attributes)
        values.update({"src": source, "alt": alternative})
        return self.add(self.element("img", attributes=values))

    def form(self, content, action="", method="post", attributes=None):
        values = {} if attributes is None else dict(attributes)
        values.update({"action": action, "method": method})
        fragment = content if isinstance(content, HTMLFragment) else HTMLFragment(
            html.escape(str(content))
        )
        return self.add(self.element("form", fragment, values))

    def style(self, css):
        self._styles.append(str(css).replace("</style", "<\\/style"))
        return self

    def script(self, javascript):
        self._scripts.append(
            str(javascript).replace("</script", "<\\/script")
        )
        return self

    def stylesheet(self, url):
        self._head.append(
            str(self.element("link", attributes={
                "rel": "stylesheet",
                "href": url
            }))
        )
        return self

    def render(self):
        head = [
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            str(self.element("title", self.title)),
            *self._head
        ]
        if self._styles:
            head.append("<style>" + "\n".join(self._styles) + "</style>")
        body = "\n".join(self._body)
        if self._scripts:
            body += "\n<script>" + "\n".join(self._scripts) + "</script>"
        return (
            "<!doctype html>\n"
            f'<html lang="{html.escape(self.language, quote=True)}">\n'
            "<head>\n" + "\n".join(head) + "\n</head>\n"
            "<body>\n" + body + "\n</body>\n</html>"
        )

    def __str__(self):
        return self.render()


def create_page(title="FACOH page", language="en"):
    return WebPage(title, language)


FUNCTIONS = {
    "create_page": create_page,
    "escape_html": html.escape
}

OBJECTS = {
    "WebPage": WebPage,
    "HTMLFragment": HTMLFragment
}
