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
    """The 76-second explainer, one chapter per cut."""

    END = 1824

    MURDER = 1
    GOAL = 169
    LISTEN = 337
    REAL_CALL = 345
    CAWDEX = 385
    MEANING = 625
    APP = 865
    SCOUT = 1105
    CROWGPT = 1297
    GENERATED_CALL = 1420
    REPLY = 1464
    FINALE = 1585
    TITLE = 1690

    CUES = {"real": REAL_CALL, "generated": GENERATED_CALL}


FILMS = {"short": Timeline, "explainer": ExplainerTimeline}
