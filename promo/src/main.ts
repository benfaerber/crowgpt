import "./styles.css";

import { AucFigure } from "./auc-figure";
import { CawPlayers } from "./caw-player";
import { ChipTips } from "./chip-tip";
import { Flock } from "./flock";
import { Lightbox } from "./lightbox";
import { MailLink } from "./mail-link";

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

new Flock("#flock", lightbox).mount();

new CawPlayers(".caw-player").mount();

new ChipTips(".chips").mount();
