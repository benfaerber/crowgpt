"""Each film's clock, shared by the Blender scene and the soundtrack mix."""

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


class FeatureTimeline(Clock):
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

    @classmethod
    def cues(cls):
        return [(name, cls.seconds(frame), gain) for name, frame, gain in cls.PLAY.cues()]


FILMS = {"short": Timeline, "explainer": ExplainerTimeline, "feature": FeatureTimeline}
