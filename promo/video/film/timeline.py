"""Each film's clock, shared by the Blender scene and the soundtrack mix."""


class Clock:
    FPS = 24
    END = 0
    CUES = {}

    @classmethod
    def seconds(cls, frame):
        return (frame - 1) / cls.FPS

    @classmethod
    def duration(cls):
        return cls.END / cls.FPS


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
    """The 92-second explainer, one chapter per cut."""

    END = 2208

    MURDER = 1
    GOAL = 157
    LISTEN = 313
    REAL_CALL = 321
    CAWDEX = 361
    MEANING = 553
    HYPOTHESIS = 673
    APP = 1105
    SCOUT = 1297
    CROWGPT = 1441
    GENERATED_CALL = 1556
    REPLY = 1600
    WEBSITE = 1681
    FINALE = 1969
    TITLE = 2009

    CUES = {"real": REAL_CALL, "generated": GENERATED_CALL}


FILMS = {"short": Timeline, "explainer": ExplainerTimeline}
