"""Compare colour maps on one image, with a split loupe.

Usage:

    python tools/compare_images.py IMAGE [--maps DIR] [--height ROWS]

IMAGE is a raw image (a 16-bit TIFF from the microscope, or any grey image).
It is scaled to [0, 1] (square root by default, which makes shot noise equal
at every level) and shown through two colour maps, A and B, chosen from the
lists at the top of the window. The maps are those of matplotlib named in
BUILTIN, the maps shipped with cmapkit.hdrmaps, and every lookup table (an
.npy array of sRGB values, n x 3, in [0, 1]) in the directories given with
--maps.

The whole image is shown through A. Under the pointer a loupe shows the
region about the pointer, divided down the middle: A on the left and B on
the right, both of the same region, so that features run continuously across
the division. Below the image are, for A and for B, the histogram of the
scaled data with each bar in the colour the map gives it, above the map
itself; a line on each marks the value under the pointer.

Each map may be shown without blur (the default), with a fixed Gaussian
blur, or with the blur at which it shows the noise at T colour differences per noise standard
deviation (cmapkit.hdrmaps.noise): a long map then gets more blur than a
short one.

Keys (with the pointer over the figure):

    w              exchange A and B
    m              show A or B in the main view
    scroll wheel   magnify or reduce in the loupe (starts at 1:1)
    +, -           larger or smaller loupe
"""

import argparse
import sys
from pathlib import Path

import numpy as np

# Run from a checkout without installing: the package is one level up.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BUILTIN = ["gray", "viridis", "cividis", "magma", "turbo", "jet"]


# Data and maps.

def load_raw(path, height=None):
    path = Path(path)
    if path.suffix.lower() in {".tif", ".tiff"}:
        import tifffile
        a = tifffile.imread(path)
    else:
        from PIL import Image
        a = np.asarray(Image.open(path).convert("L"))
    a = np.asarray(a, float)
    if a.ndim == 3:
        a = a.mean(-1)
    return a[:height] if height else a


def load_maps(dirs):
    import matplotlib.pyplot as plt
    maps = {}
    for name in BUILTIN:
        cm = plt.get_cmap(name)
        n = cm.N if hasattr(cm, "colors") else 1024
        maps[name] = cm(np.linspace(0, 1, n))[:, :3].astype(np.float32)
    from cmapkit.hdrmaps import names, path_map
    for name in names():
        maps[name] = path_map(name).lut.astype(np.float32)
    for d in dirs:
        for f in sorted(Path(d).glob("*.npy")):
            lut = np.load(f).astype(np.float32)
            if lut.max() > 1.5:
                lut = lut / 255.0
            maps[f.stem] = lut[:, :3]
    return maps


def crop(img, y0, x0, h, w, fill=128):
    """img[y0:y0+h, x0:x0+w], padded with grey where it leaves the image."""
    out = np.full((h, w, 3), fill, np.uint8)
    H, W = img.shape[:2]
    ya, yb, xa, xb = max(y0, 0), min(y0 + h, H), max(x0, 0), min(x0 + w, W)
    if ya < yb and xa < xb:
        out[ya - y0:yb - y0, xa - x0:xb - x0] = img[ya:yb, xa:xb]
    return out


class Renderer:
    """Scaled data at each blur, and the images and histograms of the maps,
    computed when first asked for and kept."""

    def __init__(self, raw, kind="sqrt"):
        from cmapkit.hdrmaps import scale
        from cmapkit.hdrmaps.noise import noise_sd
        self.raw, self.kind = raw, kind
        self.t = {0.0: scale(raw, kind).astype(np.float32)}
        self.sigma0 = noise_sd(self.t[0.0])
        self.images = {}

    def data(self, blur):
        blur = round(float(blur), 2)
        if blur not in self.t:
            # The blur is applied to the scaled data, in which the noise model
            # of cmapkit.hdrmaps.noise holds, as in cmapkit.hdrmaps.render.
            from scipy.ndimage import gaussian_filter
            self.t[blur] = gaussian_filter(self.t[0.0], blur)
        return self.t[blur]

    def image(self, name, lut, blur):
        key = (name, round(float(blur), 2))
        if key not in self.images:
            t = self.data(blur)
            idx = (t * (len(lut) - 1) + 0.5).astype(np.int32)
            self.images[key] = (lut[idx] * 255 + 0.5).astype(np.uint8)
            if len(self.images) > 12:        # keep memory bounded
                self.images.pop(next(iter(self.images)))
        return self.images[key]


# The window.

class Viewer:
    def __init__(self, raw, maps, title="", size=440):
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.backends.qt_compat import QtCore, QtWidgets
        from matplotlib.figure import Figure
        from matplotlib.lines import Line2D
        from matplotlib.patches import Rectangle
        from cmapkit.hdrmaps.noise import map_length

        self.QtCore = QtCore
        self.maps = maps
        self.names = list(maps)
        self.lengths = {k: map_length(v)[0] for k, v in maps.items()}
        self.render = Renderer(raw)
        self.size, self.zoom = size, 1.0
        self.main_is_a = True
        self.pointer = None
        self.background = None

        # Controls.
        self.win = QtWidgets.QMainWindow()
        self.win.setWindowTitle(f"Compare colour maps: {title}")
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        bar = QtWidgets.QHBoxLayout()
        self.box_a, self.box_b = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        for box in (self.box_a, self.box_b):
            for k in self.names:
                box.addItem(f"{k}   (L {self.lengths[k]:.0f})", k)
        self.box_a.setCurrentIndex(self.names.index("viridis") if "viridis" in maps else 0)
        self.box_b.setCurrentIndex(len(self.names) - 1)
        self.blur_mode = QtWidgets.QComboBox()
        self.blur_mode.addItems(["no blur", "blur matched to noise", "fixed blur"])
        self.blur_mode.setCurrentIndex(0)
        self.spin_t = QtWidgets.QDoubleSpinBox(minimum=0.5, maximum=50, value=3.0, singleStep=0.5)
        self.spin_s = QtWidgets.QDoubleSpinBox(minimum=0.0, maximum=10, value=1.5, singleStep=0.25)
        for text, w in [("A", self.box_a), ("B", self.box_b), ("", self.blur_mode),
                        ("T (dE per noise sd)", self.spin_t), ("blur (px)", self.spin_s)]:
            if text:
                bar.addWidget(QtWidgets.QLabel(text))
            bar.addWidget(w)
        swap = QtWidgets.QPushButton("swap A, B")
        bar.addWidget(swap)
        bar.addStretch(1)
        lay.addLayout(bar)

        # Figure: the image across the top; histogram over map for A and B.
        self.fig = fig = Figure(figsize=(15, 11), facecolor="0.15")
        self.canvas = FigureCanvasQTAgg(fig)
        self.canvas.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        lay.addWidget(self.canvas, 1)
        self.win.setCentralWidget(central)
        self.status = self.win.statusBar()

        gs = fig.add_gridspec(3, 2, height_ratios=[5.2, 1.2, 0.16], left=0.04, right=0.99,
                              top=0.99, bottom=0.035, hspace=0.04, wspace=0.08)
        self.ax = fig.add_subplot(gs[0, :])
        self.ax.set_axis_off()
        self.main = self.ax.imshow(np.zeros((2, 2, 3), np.uint8), interpolation="antialiased")
        self.hist = [fig.add_subplot(gs[1, c]) for c in range(2)]
        self.cbar = [fig.add_subplot(gs[2, c], sharex=self.hist[c]) for c in range(2)]
        self.marks = []

        self.lax = lax = fig.add_axes([0, 0, 0.1, 0.1])
        lax.set_axis_off()
        lax.set_xlim(0, 1)
        lax.set_ylim(1, 0)
        box = dict(facecolor="black", alpha=0.6, edgecolor="none", pad=2)
        self.loupe = lax.imshow(np.zeros((2, 2, 3), np.uint8), extent=(0, 1, 1, 0),
                                aspect="auto", interpolation="nearest", animated=True)
        self.text_a = lax.text(0.01, 0.99, "", color="white", fontsize=9, va="top",
                               transform=lax.transAxes, bbox=box, animated=True)
        self.text_b = lax.text(0.99, 0.99, "", color="white", fontsize=9, va="top", ha="right",
                               transform=lax.transAxes, bbox=box, animated=True)
        self.text_z = lax.text(0.5, 0.01, "", color="white", fontsize=8, va="bottom", ha="center",
                               transform=lax.transAxes, bbox=box, animated=True)
        self.loupe_parts = [
            self.loupe,
            lax.add_line(Line2D([0.5, 0.5], [0, 1], color="white", lw=1.5, animated=True)),
            lax.add_patch(Rectangle((0, 0), 1, 1, fill=False, ec="white", lw=2,
                                    transform=lax.transAxes, animated=True)),
            self.text_a, self.text_b, self.text_z,
        ]
        lax.set_visible(False)

        c = self.canvas
        c.mpl_connect("draw_event", self.on_draw)
        c.mpl_connect("motion_notify_event", self.on_move)
        c.mpl_connect("axes_leave_event", self.on_leave)
        c.mpl_connect("figure_leave_event", self.on_leave)
        c.mpl_connect("scroll_event", self.on_scroll)
        c.mpl_connect("key_press_event", self.on_key)
        for w in (self.box_a, self.box_b, self.blur_mode):
            w.currentIndexChanged.connect(self.refresh)
        for w in (self.spin_t, self.spin_s):
            w.valueChanged.connect(self.refresh)
        swap.clicked.connect(self.swap)

        self.refresh()
        self.win.resize(1500, 1150)

    # State.

    def chosen(self):
        return self.box_a.currentData(), self.box_b.currentData()

    def blur_for(self, name):
        mode = self.blur_mode.currentIndex()
        if mode == 0:
            return 0.0
        if mode == 2:
            return self.spin_s.value()
        from cmapkit.hdrmaps.noise import blur_for_length
        return blur_for_length(self.render.sigma0, self.lengths[name], self.spin_t.value())

    def refresh(self, *_):
        QtWidgets = __import__("matplotlib.backends.qt_compat", fromlist=["QtWidgets"]).QtWidgets
        QtWidgets.QApplication.setOverrideCursor(self.QtCore.Qt.CursorShape.WaitCursor)
        try:
            names = self.chosen()
            self.blurs = [self.blur_for(k) for k in names]
            self.rgb = [self.render.image(k, self.maps[k], s) for k, s in zip(names, self.blurs)]
            self.t = [self.render.data(s) for s in self.blurs]
            self.main.set_data(self.rgb[0 if self.main_is_a else 1])
            self.main.set_extent((-0.5, self.rgb[0].shape[1] - 0.5, self.rgb[0].shape[0] - 0.5, -0.5))
            self.ax.set_xlim(-0.5, self.rgb[0].shape[1] - 0.5)
            self.ax.set_ylim(self.rgb[0].shape[0] - 0.5, -0.5)
            self.draw_panels(names)
            shown = "A" if self.main_is_a else "B"
            self.status.showMessage(
                f"main view: {shown}.   Noise sd {self.render.sigma0:.4f} of the range, "
                f"so D(0) = {1 / self.render.sigma0:.0f}.   "
                "Keys over the figure: w swap, m main view A/B, scroll loupe zoom, +/- loupe size.")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.canvas.draw_idle()
        self.canvas.setFocus()

    def draw_panels(self, names):
        from matplotlib.lines import Line2D
        from cmapkit.hdrmaps.noise import kernel_gain
        self.marks = []
        bins = 256
        for c, (k, s, t) in enumerate(zip(names, self.blurs, self.t)):
            lut = self.maps[k]
            h, edges = np.histogram(t[::2, ::2], bins=bins, range=(0, 1))
            mid = 0.5 * (edges[:-1] + edges[1:])
            col = lut[np.clip((mid * (len(lut) - 1) + 0.5).astype(int), 0, len(lut) - 1)]
            ax = self.hist[c]
            ax.cla()
            ax.bar(mid, np.maximum(h, 0.8), width=1 / bins, color=col, log=True, linewidth=0)
            ax.set_xlim(0, 1)
            ax.set_facecolor("0.2")
            ax.tick_params(colors="0.75", labelsize=8, labelbottom=False)
            for sp in ax.spines.values():
                sp.set_color("0.4")
            shown = self.lengths[k] * self.render.sigma0 * kernel_gain(s)
            ax.set_title(f"{'AB'[c]}: {k}   length {self.lengths[k]:.0f},   blur {s:.2f} px,   "
                         f"noise shown at {shown:.1f} dE per sd",
                         color="0.9", fontsize=9, loc="left")
            cb = self.cbar[c]
            cb.cla()
            cb.imshow(lut[None], extent=(0, 1, 0, 1), aspect="auto", interpolation="nearest")
            cb.set_yticks([])
            cb.tick_params(colors="0.75", labelsize=8)
            cb.set_xlabel("scaled value (square root of the signal)", color="0.75", fontsize=8)
            for a in (ax, cb):
                self.marks.append(a.add_line(Line2D([0, 0], [0, 1], transform=a.get_xaxis_transform(),
                                                    color="white", lw=1.2, animated=True)))

    def swap(self):
        a, b = self.box_a.currentIndex(), self.box_b.currentIndex()
        for box, i in ((self.box_a, b), (self.box_b, a)):
            box.blockSignals(True)
            box.setCurrentIndex(i)
            box.blockSignals(False)
        self.refresh()

    # Drawing the loupe and the marks by blitting.

    def on_draw(self, event):
        self.background = self.canvas.copy_from_bbox(self.fig.bbox)
        self.blit()

    def blit(self):
        if self.background is None:
            return
        self.canvas.restore_region(self.background)
        if self.pointer is not None:
            self.place()
            for p in self.loupe_parts:
                self.lax.draw_artist(p)
            for m in self.marks:
                m.axes.draw_artist(m)
        self.canvas.blit(self.fig.bbox)

    def place(self):
        (px, py), (x, y) = self.pointer
        n = max(8, int(round(self.size / self.zoom)))     # image pixels across
        half = n // 2
        xi, yi = int(round(x)), int(round(y))
        x0, y0 = xi - half, yi - half
        A = crop(self.rgb[0], y0, x0, n, half)
        B = crop(self.rgb[1], y0, x0 + half, n, n - half)
        self.loupe.set_data(np.concatenate([A, B], axis=1))
        self.loupe.set_interpolation("nearest" if self.zoom >= 1 else "antialiased")
        a, b = self.chosen()
        self.text_a.set_text(f"A  {a}")
        self.text_b.set_text(f"B  {b}")
        ratio = f"{self.zoom:.3g}:1" if self.zoom >= 1 else f"1:{1 / self.zoom:.3g}"
        H0, W0 = self.rgb[0].shape[:2]
        inside = 0 <= yi < H0 and 0 <= xi < W0
        vals = [float(t[yi, xi]) for t in self.t] if inside else [np.nan, np.nan]
        self.text_z.set_text(f"{ratio}   x {xi}  y {yi}   value A {vals[0]:.3f}, B {vals[1]:.3f}")
        for m, v in zip(self.marks, [vals[0], vals[0], vals[1], vals[1]]):
            m.set_xdata([v, v])
        W, H = self.fig.bbox.width, self.fig.bbox.height
        s, gap = self.size, 24
        left = px + gap if px + gap + s <= W else px - gap - s
        bottom = py - gap - s if py - gap - s >= 0 else py + gap
        left, bottom = min(max(left, 0), W - s), min(max(bottom, 0), H - s)
        self.lax.set_position([left / W, bottom / H, s / W, s / H])

    # Events.

    def on_move(self, event):
        if event.inaxes is self.ax and event.xdata is not None:
            self.pointer = ((event.x, event.y), (event.xdata, event.ydata))
        else:
            self.pointer = None
        self.blit()

    def on_leave(self, event):
        self.pointer = None
        self.blit()

    def on_scroll(self, event):
        # Steps of sqrt(2) in magnification, so that 1:1, 2:1, 4:1 ... recur.
        step = 0.5 if event.button == "up" else -0.5
        self.zoom = float(2.0 ** np.clip(round(np.log2(self.zoom) + step, 1), -3, 4))
        self.blit()

    def on_key(self, event):
        if event.key == "w":
            self.swap()
        elif event.key == "m":
            self.main_is_a = not self.main_is_a
            self.refresh()
        elif event.key in ("+", "="):
            self.size = min(self.size + 80, 1600)
            self.blit()
        elif event.key == "-":
            self.size = max(self.size - 80, 160)
            self.blit()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split("\n\n", 2)[2])
    parser.add_argument("image", help="raw image (16-bit TIFF or grey image)")
    parser.add_argument("--maps", action="append", default=[],
                        help="directory of lookup tables (.npy, n x 3); may be repeated")
    parser.add_argument("--height", type=int, default=None,
                        help="use only the first ROWS rows (to leave out a data bar)")
    parser.add_argument("--size", type=int, default=440, help="loupe size in screen pixels")
    args = parser.parse_args(argv)

    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.qt_compat import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    raw = load_raw(args.image, args.height)
    viewer = Viewer(raw, load_maps(args.maps), title=Path(args.image).name, size=args.size)
    viewer.win.show()
    app.exec()


if __name__ == "__main__":
    main()
