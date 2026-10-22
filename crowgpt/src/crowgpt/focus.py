"""Which species the current push is about.

AMERICAN CROW ONLY, FOR NOW, AND THIS IS THE ONE PLACE THAT SAYS SO. Widening
back out is a one-line edit here or `--species all` on any command that takes it;
nothing else hardcodes a species anywhere.

The reason to narrow is power, not preference. A sitting of sixty trials spread
over six species is ten trials a species, and ten trials cannot distinguish
anything from anything — the interval is wider than the effect being chased.
Spending all sixty on one species buys an interval that can actually close, and
the honest cost is that the answer is then about that species alone.

American Crow is the right one to spend them on for four separate reasons, which
is unusual enough to be worth listing:

  - It is 70.6% of the corpus (57,479 of 81,389 bouts), so it is what the model
    mostly is.
  - It is the species that works: 0018 measured it at 99.1% of its codec
    ceiling, against hooded crow's 47.8%. A remaining flaw here is the model's
    own, not a data shortage, which is what makes it diagnostic.
  - It is the only head good enough to pseudo-label with, so the call-type work
    is landing on it too.
  - It is the Poe Family, and it is what Ben is actually listening to when he
    says the output sounds like a cyborg.

The risk of narrowing, stated so it is not forgotten: a change tuned on American
Crow may not transfer, and the five other species have weaker grouping keys
(0018) as well as far less audio. Any claim made from a focused run says
"American Crow" in it or it is overstated.
"""

SPECIES = ("american-crow",)


class Focus:
    """The species under study, and the filtering that follows from it."""

    def __init__(self, species=SPECIES):
        self.species = tuple(species) if species else ()

    @classmethod
    def parse(cls, text):
        """`all` widens to everything; anything else is a comma-separated list."""
        if text is None:
            return cls()
        if text.strip().lower() == "all":
            return cls(())
        return cls(tuple(s.strip() for s in text.split(",") if s.strip()))

    @property
    def everything(self):
        return not self.species

    def keeps(self, slug):
        return self.everything or slug in self.species

    def filter(self, rows, key="species"):
        if self.everything:
            return list(rows)
        return [row for row in rows if self.keeps(row[key])]

    def label(self):
        if self.everything:
            return "all species"
        return ", ".join(s.replace("-", " ").title() for s in self.species)

    def slug(self):
        return "all" if self.everything else "-".join(self.species)

    def __repr__(self):
        return f"Focus({self.label()})"
