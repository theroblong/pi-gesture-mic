"""Camera-plane calibration math and stable sampling, without GUI dependencies."""
import math
import statistics

TARGETS = ((.1, .1), (.9, .1), (.9, .9), (.1, .9))


def solve(matrix, values):
    rows = [list(row) + [value] for row, value in zip(matrix, values)]
    for col in range(len(rows)):
        pivot = max(range(col, len(rows)), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-10:
            raise ValueError("Calibration points are too close or aligned; spread your reach")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        scale = rows[col][col]
        rows[col] = [v / scale for v in rows[col]]
        for r in range(len(rows)):
            if r != col:
                scale = rows[r][col]
                rows[r] = [a - scale*b for a, b in zip(rows[r], rows[col])]
    return [row[-1] for row in rows]


def transform(matrix, point, clip=True):
    x, y = point
    denominator = matrix[6]*x + matrix[7]*y + matrix[8]
    if abs(denominator) < 1e-8:
        raise ValueError("Point lies outside a usable calibration plane")
    result = ((matrix[0]*x + matrix[1]*y + matrix[2])/denominator,
              (matrix[3]*x + matrix[4]*y + matrix[5])/denominator)
    return tuple(max(0., min(1., v)) for v in result) if clip else result


def homography(corners):
    if len(corners) != 4:
        raise ValueError("Four corners are required")
    if any(len(p) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in p) for p in corners):
        raise ValueError("Corners must be finite camera coordinates in 0..1")
    cross = []
    for i in range(4):
        a, b, c = corners[i], corners[(i+1)%4], corners[(i+2)%4]
        cross.append((b[0]-a[0])*(c[1]-b[1]) - (b[1]-a[1])*(c[0]-b[0]))
    area = abs(sum(corners[i][0]*corners[(i+1)%4][1] - corners[(i+1)%4][0]*corners[i][1] for i in range(4)))/2
    if min(cross) <= .002 or area < .025:
        raise ValueError("Reach must form a clockwise rectangle: top-left, top-right, bottom-right, bottom-left")
    rows, values = [], []
    for (x, y), (u, v) in zip(corners, TARGETS):
        rows.extend(([x,y,1,0,0,0,-u*x,-u*y], [0,0,0,x,y,1,-v*x,-v*y]))
        values.extend((u, v))
    matrix = solve(rows, values) + [1.]
    # Reject a projective horizon anywhere in the camera frame.
    denominators = [matrix[6]*x+matrix[7]*y+1 for x,y in ((0,0),(1,0),(1,1),(0,1))]
    if min(denominators) <= .05:
        raise ValueError("Camera angle is too steep; face the camera more directly")
    return matrix


def validate_calibration(cal):
    if not isinstance(cal, dict) or cal.get("version") != 1:
        raise ValueError("Unsupported calibration version")
    try:
        matrix = cal["matrix"]
        expected = homography(cal["corners"])
        if len(matrix) != 9 or any(type(v) not in (int,float) or not math.isfinite(v) for v in matrix):
            raise ValueError("Invalid mapping matrix")
        if any(abs(a-b) > 1e-6 for a,b in zip(matrix, expected)):
            raise ValueError("Calibration matrix does not match its corners")
        if type(cal["mirror_camera"]) is not bool:
            raise ValueError("Invalid calibration camera orientation")
        if cal["handedness"] not in ("Left", "Right"):
            raise ValueError("Calibration needs a recognized hand")
        cal["camera_device"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete calibration") from exc


def pinch_thresholds(open_ratios, closed_ratios):
    if min(len(open_ratios), len(closed_ratios)) < 12:
        raise ValueError("More pinch samples are needed")
    if not all(math.isfinite(v) and v >= 0 for v in open_ratios + closed_ratios):
        raise ValueError("Invalid pinch samples")
    opened = sorted(open_ratios)[len(open_ratios)//10]
    closed = sorted(closed_ratios)[int((len(closed_ratios)-1)*.9)]
    if opened - closed < .25:
        raise ValueError("Open and pinched fingers look too similar; open wider and try again")
    start = max(.05, min(1.5, closed + .30*(opened-closed)))
    end = min(2.5, closed + .65*(opened-closed))
    if end <= start + .05:
        raise ValueError("Pinch range is too narrow; try again")
    return {"pinch_start_ratio": start, "pinch_end_ratio": end,
            "pinch_prelock_ratio": min(3., max(end, start+.1))}


class StableSamples:
    def __init__(self, duration=.7, jitter=.025):
        self.duration, self.jitter = duration, jitter
        self.samples = []
        self.identity = None

    def clear(self):
        self.samples = []
        self.identity = None

    def add(self, identity, point, ratio, now):
        if identity != self.identity or (self.samples and now-self.samples[-1][0] > .2):
            self.clear()
        self.identity = identity
        self.samples.append((now, point, ratio))
        self.samples = [s for s in self.samples if now-s[0] <= self.duration+.15]

    def capture(self):
        if len(self.samples) < 8 or self.samples[-1][0]-self.samples[0][0] < self.duration:
            raise ValueError("Hold steady for a moment")
        point = tuple(statistics.median(s[1][i] for s in self.samples) for i in (0,1))
        if max(math.dist(s[1], point) for s in self.samples) > self.jitter:
            raise ValueError("Keep your wrist still")
        return point, [s[2] for s in self.samples]


class GestureHold:
    """A continuous, identity-bound hold; gaps and movement reset progress."""
    def __init__(self, jitter=.025):
        self.jitter = jitter
        self.clear()

    def clear(self):
        self.token = None
        self.anchor = None
        self.started = self.last_seen = None
        self.frames = 0
        self.progress = 0.

    def update(self, token, point, now, duration=2.):
        if token is None:
            self.clear()
            return False
        if (token != self.token or self.last_seen is None or
                now-self.last_seen > .25 or now < self.last_seen or
                math.dist(point, self.anchor) > self.jitter):
            self.clear()
            self.token, self.anchor, self.started = token, point, now
        self.last_seen = now
        self.frames += 1
        self.progress = min(1., max(0., (now-self.started)/duration))
        return self.progress >= 1. and self.frames >= 8
