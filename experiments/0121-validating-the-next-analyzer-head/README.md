# 0121 — Pre-ship validation of the upgraded American Crow `analyzer/` head and Tier-1 readouts

**2026-11-23** · CPU · **status: pre-registered, awaiting run**

> **Pre-registration (written and committed before fitting candidate heads, scoring strict recording-grouped garbage folds, or replaying the 29 kept field captures).**

## The question

Before modifying `analyzer/`, four empirically motivated changes from `0025`, `0036`, `0107`, `0109`, `0113`, and `0119` need one unified, leak-free validation across **recording-grouped archive CV**, **crow-free garbage rejection**, and **all current human labels on Ben's field captures (`field.db`)**:

1. **Fix the 1-window (`3 s`) `std = 0` pooling defect (`1024-d` region mean vs. `3072-d` `[mean, std, max]`):**
   - In the shipped `3072-d` training set (`INGEST_POOLED + ARCHIVE_POOLED`), 100% of `crow-tools` rows are single 3 s windows (`std = 0`, `max = mean`), whereas all 129 archive rows (including all 40 `flight call` rows) are whole-clip pools (`std > 0`).
   - That mismatch created two documented bugs: `flight call`'s `0.975` AUC relied on `std > 0` as a corpus-ID shortcut (`metrics.json` caveat), and 3 s single-window spans on field audio (`X_win`, `std = 0`) collapsed heavily toward `alarm call` (`0036` Arm D).
   - Replacing `pool(M) = [mean, std, max]` (`3072-d`) with **`M.mean(0)` (`1024-d`)** puts 1-window (`3 s`) and multi-window (`6 s+`) regions in the exact same coordinate space with zero `std = 0` cliff. Does `1024-d` region-mean match or beat `3072-d` on grouped CV **and** eliminate the `X_win` single-window collapse on field captures?
2. **Add non-crow rejection (`none` / abstain) without hurting real calls (`0036` E2, strictly recording-grouped):**
   - Shipped `MultiLabelHead` has no abstain and assigns a call type at `p > 0.5` to `> 95%` of `crowCount == 0` BirdNET-triggered noise (`garbage.npz`, `n = 578`).
   - `0036` noted a remaining caveat: some `garbage.npz` files also contributed call segments, so a naive fit could overlap recordings. Here we evaluate **strictly recording-grouped 5-fold CV** over `crowtools_keyed + archive + garbage` together.
3. **Validate fine `rattle` and `soft_song` sub-types (`song` split):**
   - Verify whether `rattle` and `soft_song` clear `analyzer/`'s `"reliable"` badge (`AUC >= 0.80`, plus `AP >= 0.80`) when trained alongside `garbage` negatives so `analyzer/` can report `sub_type` on `song` regions.
4. **End-to-end replay on all `29` `★kept` field captures (`68` trainable human labels + `2` `not_a_crow` labels in `field.db`):**
   - Measure exact head-to-head field transfer (`X_span` whole-label pooling and `X_win` single-3s-window pooling) and audit the four zero-extra-model Tier-1 readouts (`crowd`, `co_detected_raptors`, `rattle`/`soft_song`, `calling_density`) across all 29 kept captures before touching `analyzer/`.

---

## Pre-declared protocol

### Datasets

1. **Keyed `crow-tools` call segments (`n = 2,338`, `1,097` recordings):** `0036/results/crowtools_keyed.npz` + `crowtools_flags.json` (carrying multi-label CORE sets `alarm call`, `begging`, `call`, `song` AND raw flags `rattle`, `softSong`, `alert`, `mob`).
2. **Archive clip pool (`n = 129`):** `pipelines/training/results/pooled_embeddings.npz` (the source of `flight call`, `n = 40`; first `1024` dims = exact clip window mean `M.mean(0)`).
3. **Reviewed `crowCount == 0` garbage segments (`n = 578`, `352` recordings):** `0036/results/garbage.npz` (BirdNET-triggered windows explicitly verified by a human labeller to hold zero crows, grouped by the **exact same `file_id` namespace** as `crowtools_keyed.npz` so shared files stay in the same fold).
4. **Human field labels in `fieldserver/instance/field.db` (freshly embedded, never trained on):** All human labels with audio on disk (`58` trainable CORE labels + `2` `not_a_crow` labels on `★kept` captures; `68` trainable across all captures), scored on both `X_span` (all covered 3 s windows) and `X_win` (single nearest 3 s window).

### Candidate head designs compared head-to-head

- **`H0_shipped_3072`:** Exact currently shipped `pipelines/training/models/american-crow/calltype_clf.joblib` (`3072-d` `MultiLabelHead`, no `garbage` negatives, no abstain).
- **`H1_3072_abstain`:** `3072-d` `MultiLabelHead` trained with `garbage.npz` included as all-zero negative rows (`Y = []`) **plus** an explicit `none` binary head (`y = 1` on `garbage`, `y = 0` on `crowCount >= 1` + archive); abstains (`abstain = True`, suppressing `call_type` or demoting to `candidate`) when **`P(none) >= 0.50` OR `max(P_call) < 0.35`**.
- **`H2_1024_mean_abstain` (Primary candidate):** Same training rows and abstain rule as `H1`, but on **`1024-d` window-mean features (`M.mean(0)`)** — eliminating `std = 0` single-window degeneracy and the `std > 0` corpus-boundary leak on `flight call`, plus fitting auxiliary `rattle` and `soft_song` one-vs-rest heads on the `crow-tools` + `garbage` rows where those flags are defined.
- *(Sensitivity check reported alongside: `C = 1.0` default vs. `C = 0.1` regularized logistic regression.)*

### Binding pass gates for shipping into `analyzer/` (all four must hold)

1. **Garbage Rejection Gate (5-fold recording-grouped CV):** Candidate rejects **`>= 70.0%`** of held-out `garbage.npz` (`crowCount == 0`) segments (down from `H0`'s `~0–3%` rejection / `97%` false call assignment).
2. **CORE Retention Gate (5-fold recording-grouped CV on call rows):** Per-class one-vs-rest AUC and AP on `alarm call`, `begging`, `call`, `song` stay within **`<= 0.015`** of un-abstained `3072-d` CV, and Conditional CORE macro-F1 on non-abstained call segments drops by **`<= 0.020`**.
3. **Field Transfer & Single-Window Fix Gate (`field.db` `★kept` human labels, untouched in training):**
   - On `X_span` (`★kept`), top-1 accuracy among non-abstained predictions **`>= H0_shipped_3072 - 0.02`**, with false-abstain rate on `★kept` real calls **`<= 10.0%`**.
   - On `X_win` (`3 s` single-window test), `H2_1024_mean_abstain` reduces `H0`'s `alarm call` over-prediction bias and improves or matches `X_win` top-1 accuracy.
4. **`rattle` / `soft_song` Sub-Type Gate (5-fold recording-grouped CV with `garbage` negatives included):** Both `rattle` and `soft_song` achieve **`AUC >= 0.85` and `AP >= 0.75`** (`rattle` expected `>= 0.85` AP).
