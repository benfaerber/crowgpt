"""The film's clock, shared by the Blender scene and the soundtrack mix."""


class Timeline:
    FPS = 24
    END = 504

    REAL_CALL = 20
    DECODE_CUT = 78
    TOKENS_LAND = 227
    GENERATED_CALL = 229
    REPLY_CUT = 272
    FINALE_CUT = 333
    TITLE = 372

    @classmethod
    def seconds(cls, frame):
        return (frame - 1) / cls.FPS

    @classmethod
    def duration(cls):
        return cls.END / cls.FPS
