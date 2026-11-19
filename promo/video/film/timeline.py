"""Each film's clock, shared by the Blender scene and the soundtrack mix."""


class Clock:
    """Chapters are written in the film's own frames; PACE stretches them for the screen."""

    FPS = 24
    PACE = 1.0
    END = 0
    CUES = {}

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
    END = 2376

    MURDER = 1
    GOAL = 157
    LISTEN = 313
    REAL_CALL = 321
    CAWDEX = 361
    MEANING = 553
    HYPOTHESIS = 673
    MORE = 1105
    APP = 1273
    SCOUT = 1465
    CROWGPT = 1609
    GENERATED_CALL = 1724
    REPLY = 1768
    WEBSITE = 1849
    FINALE = 2137
    TITLE = 2177

    CUES = {"real": REAL_CALL, "generated": GENERATED_CALL}


FILMS = {"short": Timeline, "explainer": ExplainerTimeline}
