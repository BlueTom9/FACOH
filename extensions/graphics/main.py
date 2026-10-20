import math
import struct
import time

import pygame
from pygame import Vector2, Vector3

# moderngl and PyOpenGL's GL module are expensive to import and are only needed
# once an OpenGL window or the *_api() helpers are used, so they load on first
# use. graphics.moderngl / graphics.GL still resolve to the real modules through
# the module-level __getattr__ below.
_moderngl_module = None
_gl_module = None


def _load_moderngl():
    global _moderngl_module
    if _moderngl_module is None:
        import moderngl as module
        _moderngl_module = module
    return _moderngl_module


def _load_gl():
    global _gl_module
    if _gl_module is None:
        from OpenGL import GL as module
        _gl_module = module
    return _gl_module


def __getattr__(name):
    if name == "moderngl":
        return _load_moderngl()
    if name == "GL":
        return _load_gl()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class GraphicsWindow:
    def __init__(
            self,
            width=800,
            height=600,
            title="FACOH Graphics",
            opengl=False,
            resizable=True,
            fullscreen=False,
            vsync=True,
            gl_version=330,
            depth_bits=24,
            stencil_bits=8,
            samples=0
    ):
        self.width = int(width)
        self.height = int(height)
        if self.width < 1 or self.height < 1:
            raise ValueError("window dimensions must be positive")
        self.title = str(title)
        self.opengl_enabled = bool(opengl)
        self.resizable = bool(resizable)
        self.fullscreen = bool(fullscreen)
        self.vsync = bool(vsync)
        self.closed = False
        self.should_close = False
        self.context = None
        self.clock = pygame.time.Clock()
        self.delta_time = 0.0
        self.elapsed_time = 0.0
        self._last_tick = time.perf_counter()
        self._fonts = {}
        self._images = []
        self._sounds = []

        pygame.init()
        if self.opengl_enabled:
            major = int(gl_version) // 100
            minor = (int(gl_version) % 100) // 10
            pygame.display.gl_set_attribute(
                pygame.GL_CONTEXT_MAJOR_VERSION,
                major
            )
            pygame.display.gl_set_attribute(
                pygame.GL_CONTEXT_MINOR_VERSION,
                minor
            )
            pygame.display.gl_set_attribute(
                pygame.GL_CONTEXT_PROFILE_MASK,
                pygame.GL_CONTEXT_PROFILE_CORE
            )
            pygame.display.gl_set_attribute(
                pygame.GL_DEPTH_SIZE,
                int(depth_bits)
            )
            pygame.display.gl_set_attribute(
                pygame.GL_STENCIL_SIZE,
                int(stencil_bits)
            )
            if samples:
                pygame.display.gl_set_attribute(
                    pygame.GL_MULTISAMPLEBUFFERS,
                    1
                )
                pygame.display.gl_set_attribute(
                    pygame.GL_MULTISAMPLESAMPLES,
                    int(samples)
                )

        self.surface = pygame.display.set_mode(
            (self.width, self.height),
            self._display_flags(),
            vsync=int(self.vsync) if self.opengl_enabled else 0
        )
        pygame.display.set_caption(self.title)

        if self.opengl_enabled:
            self.context = _load_moderngl().create_context(require=int(gl_version))
            self.context.viewport = (0, 0, self.width, self.height)

    @property
    def size(self):
        return self.width, self.height

    @property
    def framebuffer_size(self):
        if self.opengl_enabled:
            return self.context.screen.size
        return self.surface.get_size()

    @property
    def fps(self):
        return self.clock.get_fps()

    @property
    def pygame(self):
        return pygame

    @property
    def gl(self):
        if not self.opengl_enabled:
            raise RuntimeError("OpenGL is not enabled for this window")
        return _load_gl()

    def _ensure_open(self):
        if self.closed:
            raise RuntimeError("graphics window is closed")

    def events(self):
        self._ensure_open()
        results = []
        for event in pygame.event.get():
            event_type = pygame.event.event_name(event.type)
            if event.type == pygame.QUIT:
                self.should_close = True
            if event.type == pygame.VIDEORESIZE:
                self.width = event.w
                self.height = event.h
                if self.opengl_enabled:
                    self.context.viewport = (0, 0, event.w, event.h)

            item = {"type": event.type, "name": event_type}
            for key, value in event.dict.items():
                if key == "type":
                    continue
                if key in ("key", "button") and isinstance(value, int):
                    item[key] = value
                    item[key + "_name"] = (
                        pygame.key.name(value)
                        if key == "key"
                        else value
                    )
                elif key == "unicode":
                    item["text"] = value
                elif isinstance(value, (int, float, str, bool, tuple, list)):
                    item[key] = value
            results.append(item)
        return results

    def keyboard(self):
        self._ensure_open()
        return [
            pygame.key.name(index)
            for index, pressed in enumerate(pygame.key.get_pressed())
            if pressed
        ]

    def key_down(self, key):
        self._ensure_open()
        key_code = pygame.key.key_code(
            key) if isinstance(key, str) else int(key)
        return bool(pygame.key.get_pressed()[key_code])

    def mouse_position(self):
        self._ensure_open()
        return pygame.mouse.get_pos()

    def mouse_buttons(self):
        self._ensure_open()
        return pygame.mouse.get_pressed(5)

    def capture_mouse(self, enabled=True, hide_cursor=False):
        self._ensure_open()
        pygame.event.set_grab(bool(enabled))
        pygame.mouse.set_visible(not hide_cursor)

    def set_title(self, title):
        self._ensure_open()
        self.title = str(title)
        pygame.display.set_caption(self.title)

    def set_icon(self, image):
        self._ensure_open()
        pygame.display.set_icon(image)

    def resize(self, width, height):
        self._ensure_open()
        width = int(width)
        height = int(height)
        if width < 1 or height < 1:
            raise ValueError("window dimensions must be positive")
        if self.fullscreen:
            self.fullscreen = False
        self.width = width
        self.height = height
        self.surface = pygame.display.set_mode(
            (self.width, self.height),
            self._display_flags(),
            vsync=int(self.vsync) if self.opengl_enabled else 0
        )
        if self.opengl_enabled:
            self.context.viewport = (0, 0, self.width, self.height)

    def _display_flags(self):
        flags = 0
        if self.resizable and not self.fullscreen:
            flags |= pygame.RESIZABLE
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
        if self.opengl_enabled:
            flags |= pygame.OPENGL | pygame.DOUBLEBUF
        return flags

    def tick(self, fps_limit=0):
        self._ensure_open()
        self.clock.tick(int(fps_limit))
        current = time.perf_counter()
        self.delta_time = current - self._last_tick
        self.elapsed_time += self.delta_time
        self._last_tick = current
        return self.delta_time

    def present(self):
        self._ensure_open()
        pygame.display.flip()

    def clear(self, red=0, green=0, blue=0, alpha=1, depth=1):
        self._ensure_open()
        if self.opengl_enabled:
            self.context.clear(red, green, blue, alpha, depth=depth)
        else:
            color = tuple(
                round(max(0, min(1, component)) * 255)
                for component in (red, green, blue, alpha)
            )
            self.surface.fill(color)

    def viewport(self, x, y, width, height):
        self._ensure_open()
        if not self.opengl_enabled:
            raise RuntimeError("viewport requires an OpenGL window")
        self.context.viewport = (
            int(x),
            int(y),
            int(width),
            int(height)
        )

    def enable(self, *capabilities):
        self._ensure_gl()
        flags = 0
        for capability in capabilities:
            flags |= int(capability)
        self.context.enable(flags)

    def disable(self, *capabilities):
        self._ensure_gl()
        flags = 0
        for capability in capabilities:
            flags |= int(capability)
        self.context.disable(flags)

    def _ensure_gl(self):
        self._ensure_open()
        if not self.opengl_enabled:
            raise RuntimeError("this operation requires an OpenGL window")

    def buffer(self, data=None, reserve=0, dynamic=False):
        self._ensure_gl()
        return self.context.buffer(data=data, reserve=reserve, dynamic=dynamic)

    def program(self, vertex_shader, fragment_shader, geometry_shader=None,
                varyings=()):
        self._ensure_gl()
        options = {"vertex_shader": vertex_shader,
                   "fragment_shader": fragment_shader}
        if geometry_shader is not None:
            options["geometry_shader"] = geometry_shader
        if varyings:
            options["varyings"] = tuple(varyings)
        return self.context.program(**options)

    def compute_program(self, source):
        self._ensure_gl()
        return self.context.compute_shader(source)

    def vertex_array(self, program, content, index_buffer=None,
                     index_element_size=4):
        self._ensure_gl()
        converted_content = [
            tuple(entry) if isinstance(entry, list) else entry
            for entry in content
        ]
        return self.context.vertex_array(
            program,
            converted_content,
            index_buffer=index_buffer,
            index_element_size=index_element_size
        )

    def simple_vertex_array(self, program, buffer, *attributes, index_buffer=None,
                            index_element_size=4):
        self._ensure_gl()
        return self.context.simple_vertex_array(
            program,
            buffer,
            *attributes,
            index_buffer=index_buffer,
            index_element_size=index_element_size
        )

    def texture(self, width, height, components=4, data=None, dtype="f1",
                alignment=1):
        self._ensure_gl()
        return self.context.texture(
            (int(width), int(height)),
            int(components),
            data=data,
            alignment=int(alignment),
            dtype=dtype
        )

    def texture_from_image(self, path, flip_y=True):
        pixels = load_image_pixels(path, flip_y)
        return self.texture(
            pixels["width"],
            pixels["height"],
            pixels["components"],
            pixels["data"],
            "f1",
            1
        )

    def texture_3d(self, width, height, depth, components=4, data=None,
                   dtype="f1", alignment=1):
        self._ensure_gl()
        return self.context.texture3d(
            (int(width), int(height), int(depth)),
            int(components),
            data=data,
            alignment=int(alignment),
            dtype=dtype
        )

    def texture_array(self, width, height, layers, components=4, data=None,
                      dtype="f1", alignment=1):
        self._ensure_gl()
        return self.context.texture_array(
            (int(width), int(height), int(layers)),
            int(components),
            data=data,
            alignment=int(alignment),
            dtype=dtype
        )

    def texture_cube(self, size, components=4, data=None, dtype="f1",
                     alignment=1):
        self._ensure_gl()
        return self.context.texture_cube(
            int(size),
            int(components),
            data=data,
            alignment=int(alignment),
            dtype=dtype
        )

    def depth_texture(self, width, height, data=None, samples=0,
                      alignment=4):
        self._ensure_gl()
        return self.context.depth_texture(
            (int(width), int(height)),
            data=data,
            samples=int(samples),
            alignment=int(alignment)
        )

    def renderbuffer(self, width, height, components=4, samples=0,
                     dtype="f1"):
        self._ensure_gl()
        return self.context.renderbuffer(
            (int(width), int(height)),
            components=int(components),
            samples=int(samples),
            dtype=dtype
        )

    def framebuffer(self, color_attachments=(), depth_attachment=None):
        self._ensure_gl()
        return self.context.framebuffer(
            color_attachments=list(color_attachments),
            depth_attachment=depth_attachment
        )

    def sampler(self, texture=None, **options):
        self._ensure_gl()
        return self.context.sampler(texture=texture, **options)

    def query(self, **options):
        self._ensure_gl()
        return self.context.query(**options)

    def scope(self, **options):
        self._ensure_gl()
        return self.context.scope(**options)

    def draw_rect(self, color, rectangle, width=0, border_radius=0):
        self._ensure_2d()
        return pygame.draw.rect(
            self.surface,
            color,
            rectangle,
            width=int(width),
            border_radius=int(border_radius)
        )

    def draw_circle(self, color, center, radius, width=0):
        self._ensure_2d()
        return pygame.draw.circle(
            self.surface,
            color,
            center,
            int(radius),
            width=int(width)
        )

    def draw_line(self, color, start, end, width=1):
        self._ensure_2d()
        return pygame.draw.line(
            self.surface,
            color,
            start,
            end,
            int(width)
        )

    def draw_polygon(self, color, points, width=0):
        self._ensure_2d()
        return pygame.draw.polygon(
            self.surface,
            color,
            points,
            width=int(width)
        )

    def draw_text(self, text, x, y, size=24, color=(255, 255, 255),
                  font_name=None, antialias=True):
        self._ensure_2d()
        cache_key = font_name, int(size)
        font = self._fonts.get(cache_key)
        if font is None:
            font = pygame.font.SysFont(font_name, int(size))
            self._fonts[cache_key] = font
        rendered = font.render(str(text), bool(antialias), color)
        return self.surface.blit(rendered, (int(x), int(y)))

    def load_image(self, path, alpha=True):
        self._ensure_open()
        image = pygame.image.load(path)
        image = image.convert_alpha() if alpha else image.convert()
        self._images.append(image)
        return image

    def draw_image(self, image, x, y, width=None, height=None):
        self._ensure_2d()
        if width is not None or height is not None:
            original_width, original_height = image.get_size()
            target_width = original_width if width is None else int(width)
            target_height = original_height if height is None else int(height)
            image = pygame.transform.smoothscale(
                image,
                (target_width, target_height)
            )
        return self.surface.blit(image, (int(x), int(y)))

    def make_surface(self, width, height, alpha=True):
        self._ensure_open()
        flags = pygame.SRCALPHA if alpha else 0
        return pygame.Surface((int(width), int(height)), flags)

    def load_sound(self, path):
        self._ensure_open()
        sound = pygame.mixer.Sound(path)
        self._sounds.append(sound)
        return sound

    def _ensure_2d(self):
        self._ensure_open()
        if self.opengl_enabled:
            raise RuntimeError("Pygame 2D drawing requires opengl=False")

    def close(self):
        if self.closed:
            return False
        self.closed = True
        if self.context is not None:
            self.context.release()
            self.context = None
        self._images.clear()
        self._sounds.clear()
        self._fonts.clear()
        pygame.display.quit()
        pygame.quit()
        return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def vector3(x=0, y=0, z=0):
    return Vector3(float(x), float(y), float(z))


def pack_floats(values):
    values = list(values)
    return struct.pack(f"<{len(values)}f", *values)


def pack_ints(values, bytes_per_value=4, signed=False):
    format_codes = {
        (1, False): "B",
        (1, True): "b",
        (2, False): "H",
        (2, True): "h",
        (4, False): "I",
        (4, True): "i"
    }
    format_code = format_codes.get((int(bytes_per_value), bool(signed)))
    if format_code is None:
        raise ValueError("integer width must be 1, 2, or 4 bytes")
    values = list(values)
    return struct.pack(f"<{len(values)}{format_code}", *values)


def load_image_pixels(path, flip_y=True):
    image = pygame.image.load(path)
    width, height = image.get_size()
    return {
        "width": width,
        "height": height,
        "components": 4,
        "data": pygame.image.tobytes(image, "RGBA", bool(flip_y))
    }


def vector_add(left, right):
    return Vector3(left) + Vector3(right)


def vector_subtract(left, right):
    return Vector3(left) - Vector3(right)


def vector_scale(vector, scale):
    return Vector3(vector) * float(scale)


def vector_dot(left, right):
    return Vector3(left).dot(Vector3(right))


def vector_cross(left, right):
    return Vector3(left).cross(Vector3(right))


def vector_normalize(vector):
    result = Vector3(vector)
    if result.length_squared() == 0:
        raise ValueError("cannot normalize a zero-length vector")
    return result.normalize()


def matrix_identity():
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0]
    ]


def matrix_multiply(left, right):
    if len(left[0]) != len(right):
        raise ValueError("matrix dimensions do not match")
    return [
        [
            sum(left[row][index] * right[index][column]
                for index in range(len(right)))
            for column in range(len(right[0]))
        ]
        for row in range(len(left))
    ]


def matrix_translation(x, y, z):
    matrix = matrix_identity()
    matrix[0][3] = float(x)
    matrix[1][3] = float(y)
    matrix[2][3] = float(z)
    return matrix


def matrix_scale(x, y=None, z=None):
    y = x if y is None else y
    z = x if z is None else z
    return [
        [float(x), 0.0, 0.0, 0.0],
        [0.0, float(y), 0.0, 0.0],
        [0.0, 0.0, float(z), 0.0],
        [0.0, 0.0, 0.0, 1.0]
    ]


def matrix_rotation_x(angle):
    cosine = math.cos(float(angle))
    sine = math.sin(float(angle))
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, cosine, -sine, 0.0],
        [0.0, sine, cosine, 0.0],
        [0.0, 0.0, 0.0, 1.0]
    ]


def matrix_rotation_y(angle):
    cosine = math.cos(float(angle))
    sine = math.sin(float(angle))
    return [
        [cosine, 0.0, sine, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [-sine, 0.0, cosine, 0.0],
        [0.0, 0.0, 0.0, 1.0]
    ]


def matrix_rotation_z(angle):
    cosine = math.cos(float(angle))
    sine = math.sin(float(angle))
    return [
        [cosine, -sine, 0.0, 0.0],
        [sine, cosine, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0]
    ]


def matrix_perspective(field_of_view, aspect, near, far):
    field_of_view = float(field_of_view)
    aspect = float(aspect)
    near = float(near)
    far = float(far)
    if aspect <= 0 or near <= 0 or far <= near:
        raise ValueError("expected aspect > 0 and 0 < near < far")
    focal_length = 1.0 / math.tan(field_of_view / 2.0)
    return [
        [focal_length / aspect, 0.0, 0.0, 0.0],
        [0.0, focal_length, 0.0, 0.0],
        [0.0, 0.0, (far + near) / (near - far),
         (2.0 * far * near) / (near - far)],
        [0.0, 0.0, -1.0, 0.0]
    ]


def matrix_orthographic(left, right, bottom, top, near, far):
    if right == left or top == bottom or far == near:
        raise ValueError("orthographic bounds must have nonzero size")
    return [
        [2 / (right - left), 0, 0, -(right + left) / (right - left)],
        [0, 2 / (top - bottom), 0, -(top + bottom) / (top - bottom)],
        [0, 0, -2 / (far - near), -(far + near) / (far - near)],
        [0, 0, 0, 1]
    ]


def matrix_look_at(eye, target, up):
    eye = Vector3(eye)
    forward = vector_normalize(Vector3(target) - eye)
    side = vector_normalize(forward.cross(Vector3(up)))
    corrected_up = side.cross(forward)
    return [
        [side.x, side.y, side.z, -side.dot(eye)],
        [corrected_up.x, corrected_up.y, corrected_up.z,
         -corrected_up.dot(eye)],
        [-forward.x, -forward.y, -forward.z, forward.dot(eye)],
        [0.0, 0.0, 0.0, 1.0]
    ]


def matrix_bytes(matrix):
    size = len(matrix)
    if any(len(row) != size for row in matrix):
        raise ValueError("matrix_bytes expects a square matrix")
    values = [float(matrix[row][column])
              for column in range(size)
              for row in range(size)]
    return struct.pack(f"{len(values)}f", *values)


def pygame_api():
    return pygame


def moderngl_api():
    return _load_moderngl()


def opengl_api():
    return _load_gl()


def create_window(width=800, height=600, title="FACOH Graphics", **options):
    return GraphicsWindow(width, height, title, **options)


FUNCTIONS = {
    "create_window": create_window,
    "pack_floats": pack_floats,
    "pack_ints": pack_ints,
    "load_image_pixels": load_image_pixels,
    "vector3": vector3,
    "vector_add": vector_add,
    "vector_subtract": vector_subtract,
    "vector_scale": vector_scale,
    "vector_dot": vector_dot,
    "vector_cross": vector_cross,
    "vector_normalize": vector_normalize,
    "matrix_identity": matrix_identity,
    "matrix_multiply": matrix_multiply,
    "matrix_translation": matrix_translation,
    "matrix_scale": matrix_scale,
    "matrix_rotation_x": matrix_rotation_x,
    "matrix_rotation_y": matrix_rotation_y,
    "matrix_rotation_z": matrix_rotation_z,
    "matrix_perspective": matrix_perspective,
    "matrix_orthographic": matrix_orthographic,
    "matrix_look_at": matrix_look_at,
    "matrix_bytes": matrix_bytes,
    "pygame_api": pygame_api,
    "moderngl_api": moderngl_api,
    "opengl_api": opengl_api
}

OBJECTS = {
    "GraphicsWindow": GraphicsWindow,
    "Vector2": Vector2,
    "Vector3": Vector3
}
