import "./styles.css";

import { AucFigure } from "./auc-figure";
import { CallSamples } from "./call-samples";
import { Carousel } from "./carousel";
import { CawPlayers } from "./caw-player";
import { ChipTips } from "./chip-tip";
import { ExplainerFilm } from "./explainer-film";
import { Flock } from "./flock";
import { HeadingAnchors } from "./heading-anchors";
import { Lightbox } from "./lightbox";
import { MailLink } from "./mail-link";
import { MovedAnchors } from "./moved-anchors";
import { NavMenu } from "./nav-menu";
import { PeanutDrop } from "./peanut-drop";
import { SpeciesTip } from "./species-tip";

new MovedAnchors().follow();

new AucFigure({
  chart: document.querySelector("#auc-chart"),
  legend: document.querySelector("#auc-legend"),
  table: document.querySelector("#auc-table"),
  toggle: document.querySelector("#auc-table-toggle"),
}).render();

// Held rather than discarded: the crows in the hero point at the clips they are
// in, and a video figure has no click of its own to borrow.
const lightbox = new Lightbox(".hero-photo, .photo, .shot, .video");
lightbox.mount();

new MailLink(".mail").mount();

Carousel.mountAll(".carousel");

new ExplainerFilm(".film-poster").mount();

const nav = document.querySelector<HTMLElement>(".hero .nav, .subpage > .nav");
const navLinks = nav?.querySelector<HTMLElement>(".nav-links");
if (nav && navLinks) new NavMenu(nav, navLinks).mount();

new Flock("#flock", lightbox).mount();

new CawPlayers(".caw-player").mount();

new CallSamples(".call").mount();

new PeanutDrop().mount();

new ChipTips(".chips").mount();

const speciesCount = document.querySelector<HTMLElement>("#species-heads");
if (speciesCount) new SpeciesTip(speciesCount).mount();

new HeadingAnchors("main h2, main h3, main h4").mount();
