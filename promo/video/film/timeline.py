"""Each film's clock, shared by the Blender scene and the soundtrack mix."""

from .owl_screenplay import OWL
from .screenplay import FEATURE


class Clock:
    """Chapters are written in the film's own frames; PACE stretches them for the screen."""

    FPS = 24
    PACE = 1.0
    END = 0
    CUES = {}
    #: The sounds a film plays, by the name its scenes use: the promo asset and
    #: how many seconds of it are heard (None for all of it).
    SOUNDS = {"real": ("real-alarm-call.wav", None), "generated": ("crowgpt2-preview.wav", None)}
    PHOTOS = {}

    @classmethod
    def cues(cls):
        """Each sound the soundtrack lays in: its name, when in seconds, how loud."""
        return [(name, cls.seconds(frame), 1.0) for name, frame in cls.CUES.items()]

    @classmethod
    def screen(cls, frame):
        return round(1 + (frame - 1) * cls.PACE)

    @classmethod
    def seconds(cls, frame):
        return (cls.screen(frame) - 1) / cls.FPS

    @classmethod
    def length(cls):
        return cls.screen(cls.END)

    @classmethod
    def duration(cls):
        return cls.length() / cls.FPS


class Timeline(Clock):
    """The 21-second film."""

    END = 504

    REAL_CALL = 20
    DECODE_CUT = 78
    TOKENS_LAND = 227
    GENERATED_CALL = 229
    REPLY_CUT = 272
    FINALE_CUT = 333
    TITLE = 372

    CUES = {"real": REAL_CALL, "generated": GENERATED_CALL}


class ExplainerTimeline(Clock):
    """The explainer, one chapter per cut, slowed to leave room for a narrator."""

    PACE = 1.25
    END = 2232

    MURDER = 1
    GOAL = 157
    LISTEN = 313
    REAL_CALL = 321
    CAWDEX = 361
    MEANING = 553
    HYPOTHESIS = 673
    MORE = 1105
    APP = 1273
    CROWGPT = 1465
    GENERATED_CALL = 1580
    REPLY = 1624
    WEBSITE = 1705
    FINALE = 1993
    TITLE = 2033

    CUES = {"real": REAL_CALL, "generated": GENERATED_CALL}


class Narrated(Clock):
    """A film timed from its screenplay: its length and every sound cue follow from the lines."""

    @classmethod
    def cues(cls):
        return [(name, cls.seconds(frame), gain) for name, frame, gain in cls.PLAY.cues()]


class FeatureTimeline(Narrated):
    """The feature: its length and every sound cue follow from the screenplay."""

    PLAY = FEATURE
    END = FEATURE.end
    SOUNDS = {
        "real": ("real-alarm-call.wav", None),
        "generated": ("crowgpt2-preview.wav", None),
        "crowbot": ("crowgpt-alarm-preview.wav", None),
        "edgar": ("caws/edgar-alarm.mp3", None),
        "alarm": ("calls/alarm-call.mp3", 3.6),
        "flight": ("calls/flight-call.mp3", 3.6),
        "call": ("calls/call.mp3", 3.6),
        "begging": ("calls/begging.mp3", 3.6),
        "song": ("calls/song.mp3", 3.6),
    }

    #: Real photographs of the family, from the promo page: the asset and the
    #: square of it the film shows, as (left, top, right, bottom) fractions.
    PHOTOS = {
        "thrasher": ("hero-crow.jpg", (0.05, 0.31, 0.65, 0.76)),
        "ripjaw": ("crow-street.jpg", (0.2, 0.18, 0.8, 0.63)),
        "killer": ("killer-roof.jpg", (0.25, 0.32, 0.8, 0.73)),
        "streetlight": ("pair-streetlight.jpg", (0.05, 0.14, 0.72, 0.645)),
        "edgar": ("edgar-looks.jpg", (0.2, 0.33, 0.76, 0.75)),
        "edgar-wire": ("edgar-wire.jpg", (0.17, 0.3, 0.72, 0.72)),
        "kit": ("field-kit.jpg", (0.05, 0.14, 0.95, 0.82)),
    }


class OwlTimeline(Narrated):
    """The owl film. Its crows are the family's own alarm calls, not an owl or hawk mob."""

    PLAY = OWL
    END = OWL.end
    SOUNDS = {
        "real": ("real-alarm-call.wav", None),
        "generated": ("crowgpt2-preview.wav", None),
        "mob": ("caws/adult-alarm-c.mp3", None),
        "single": ("caws/edgar-alarm.mp3", None),
    }


FILMS = {"short": Timeline, "explainer": ExplainerTimeline, "feature": FeatureTimeline,
         "owl": OwlTimeline}
