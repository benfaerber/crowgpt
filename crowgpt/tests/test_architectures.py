"""Tests for Frame-RoPE+SwiGLU CrowGPT, per-stage loss breakdown, Dual-AR, and min_p sampling."""

import numpy as np
import pytest
import torch

from crowgpt.codec import CODEBOOK_SIZE
from crowgpt.dualar import DualARConfig, DualARCrowGPT
from crowgpt.model import Config, CrowGPT, LegalMask
from crowgpt.sample import draw_from_logits
from crowgpt.sliced import LegalSlices, summarise_stage_sums
from crowgpt.tokens import Vocabulary


def _make_sequences(vocabulary, lengths, seed=0):
    rng = np.random.default_rng(seed)
    slots = vocabulary.prefix_slots()
    k = vocabulary.n_codebooks
    seqs = []
    for n_frames in lengths:
        seq = [int(rng.integers(lo, hi)) for lo, hi in slots]
        for _ in range(n_frames):
            for s in range(k):
                seq.append(int(rng.integers(s * CODEBOOK_SIZE, (s + 1) * CODEBOOK_SIZE)))
        seq.append(vocabulary.eos)
        seqs.append(seq)
    longest = max(map(len, seqs))
    inputs = torch.zeros(len(seqs), longest - 1, dtype=torch.long)
    targets = torch.full((len(seqs), longest - 1), -1, dtype=torch.long)
    for row, seq in enumerate(seqs):
        inputs[row, : len(seq) - 1] = torch.tensor(seq[:-1])
        targets[row, : len(seq) - 1] = torch.tensor(seq[1:])
    return inputs, targets


def test_frame_rope_swiglu_kv_cache_matches_uncached():
    torch.manual_seed(0)
    vocab = Vocabulary(8, ["american-crow", "common-raven"], n_unit_buckets=5)
    cfg = Config(
        vocab_size=vocab.size, n_codebooks=8, block_size=128,
        n_layer=3, n_head=4, n_embd=32, dropout=0.0, prefix_len=vocab.prefix_len,
        pos_encoding="frame_rope", norm="rmsnorm", mlp="swiglu",
    )
    model = CrowGPT(cfg).eval()
    inputs, _ = _make_sequences(vocab, [4], seed=1)
    seq = inputs[:, :30]
    with torch.no_grad():
        full, _ = model(seq)
        cache = model.empty_cache()
        model(seq[:, :5], cache=cache, offset=0)
        for pos in range(5, seq.size(1)):
            step, _ = model(seq[:, pos : pos + 1], cache=cache, offset=pos)
            assert torch.allclose(step[:, -1, :], full[:, pos, :], atol=1e-5), (
                f"frame_rope KV cache diverged at position {pos}"
            )


def test_per_stage_sums_reconstruct_exact_masked_loss():
    torch.manual_seed(0)
    vocab = Vocabulary(8, ["american-crow", "common-raven"], n_unit_buckets=5)
    cfg = Config(
        vocab_size=vocab.size, n_codebooks=8, block_size=128,
        n_layer=2, n_head=4, n_embd=32, dropout=0.0, prefix_len=vocab.prefix_len,
        pos_encoding="frame_rope", norm="rmsnorm", mlp="swiglu",
    )
    model = CrowGPT(cfg).double().eval()
    legal = LegalMask(vocab, cfg.block_size + 1)
    slices = LegalSlices(legal)
    inputs, targets = _make_sequences(vocab, [6, 3, 1], seed=2)

    _, masked = model(inputs, targets, legal.for_batch(inputs.size(1)))
    sums, counts = slices.per_stage_sums(model, inputs, targets, vocab)
    summary = summarise_stage_sums(sums, counts, vocab.n_codebooks)

    assert summary["total_tokens"] == int((targets >= 0).sum().item())
    assert counts["eos"] == 3
    assert counts["prefix"] == 3 * (vocab.prefix_len - 1)
    assert counts["stage_0"] == 6 + 3 + 1
    assert np.isclose(summary["overall"], float(masked.item()), rtol=1e-6)


def test_stage_weights_uniform_equals_unweighted_loss():
    torch.manual_seed(0)
    vocab = Vocabulary(8, ["american-crow"], n_unit_buckets=5)
    cfg = Config(
        vocab_size=vocab.size, n_codebooks=8, block_size=128,
        n_layer=2, n_head=4, n_embd=32, dropout=0.0, prefix_len=vocab.prefix_len,
    )
    model = CrowGPT(cfg).double().eval()
    legal = LegalMask(vocab, cfg.block_size + 1)
    slices = LegalSlices(legal)
    inputs, targets = _make_sequences(vocab, [5, 2], seed=3)

    unweighted = slices.loss(model, inputs, targets)
    ones = slices.loss(model, inputs, targets, stage_weights=[1.0] * 8)
    assert torch.isclose(unweighted, ones, rtol=1e-6)


def test_dualar_exact_token_accounting_and_causality():
    torch.manual_seed(0)
    vocab = Vocabulary(8, ["american-crow", "common-raven"], n_unit_buckets=5)
    cfg = DualARConfig(
        vocab_size=vocab.size, n_codebooks=8, block_size=128,
        n_layer=2, depth_layer=2, n_head=4, depth_head=4, n_embd=32,
        dropout=0.0, prefix_len=vocab.prefix_len,
    )
    model = DualARCrowGPT(cfg).double().eval()
    inputs, targets = _make_sequences(vocab, [5, 2, 1], seed=4)

    loss = model.loss(inputs, targets, vocab)
    sums, counts = model.per_stage_sums(inputs, targets, vocab)
    summary = summarise_stage_sums(sums, counts, vocab.n_codebooks)

    assert summary["total_tokens"] == int((targets >= 0).sum().item())
    assert counts["eos"] == 3
    assert counts["prefix"] == 3 * (vocab.prefix_len - 1)
    assert counts["stage_0"] == 5 + 2 + 1
    assert np.isclose(summary["overall"], float(loss.item()), rtol=1e-6)

    # Uniform stage weights must match unweighted loss.
    loss_ones = model.loss(inputs, targets, vocab, stage_weights=[1.0] * 8)
    assert torch.isclose(loss, loss_ones, rtol=1e-6)

    # Strict causality: mutating frame 3 must not alter prefix or frames 0..2 losses.
    seq_in, seq_tgt = _make_sequences(vocab, [4], seed=5)
    mut_in, mut_tgt = seq_in.clone(), seq_tgt.clone()
    frame3_start = vocab.prefix_len + 3 * 8
    mut_in[0, frame3_start] = (mut_in[0, frame3_start] + 17) % CODEBOOK_SIZE
    mut_tgt[0, frame3_start - 1] = mut_in[0, frame3_start]

    p1, s1, _ = model._forward_per_token(seq_in, seq_tgt, vocab)
    p2, s2, _ = model._forward_per_token(mut_in, mut_tgt, vocab)
    for a, b in zip(p1, p2):
        assert torch.allclose(a, b, atol=1e-7)
    for stage in range(8):
        # Frames 0, 1, 2 (indices 0..2) must be completely unaffected by mutating frame 3.
        assert torch.allclose(s1[stage][:3], s2[stage][:3], atol=1e-7), (
            f"causality leak on stage {stage}"
        )


def test_dualar_cached_step_matches_uncached_forward():
    """Verify Dual-AR's incremental temporal+depth cache agrees with full forward."""
    torch.manual_seed(0)
    vocab = Vocabulary(8, ["american-crow", "common-raven"], n_unit_buckets=5)
    cfg = DualARConfig(
        vocab_size=vocab.size, n_codebooks=8, block_size=128,
        n_layer=2, depth_layer=2, n_head=4, depth_head=4, n_embd=32,
        dropout=0.0, prefix_len=vocab.prefix_len,
    )
    model = DualARCrowGPT(cfg).double().eval()
    inputs, targets = _make_sequences(vocab, [3], seed=6)
    _, full_stage_losses, _ = model._forward_per_token(inputs, targets, vocab)

    # Replay frame-by-frame with temporal + depth KV-caches and check exact NLL per stage.
    p = vocab.prefix_len
    k = vocab.n_codebooks
    t_cache = model.empty_temporal_cache()
    with torch.no_grad():
        h = model.temporal_hidden(
            model.token_embedding(inputs[:, :p]), cache=t_cache, offset=0
        )
        t_pos = p
        for f in range(3):
            frame_toks = inputs[0, p + f * k : p + (f + 1) * k]
            d_cache = model.empty_depth_cache()
            dh = model.depth_hidden(h[:, -1:, :], cache=d_cache, offset=0)
            logits0 = (dh[:, -1, :] @ model.head.weight[model.stage0_ids].T).float()
            nll0 = torch.nn.functional.cross_entropy(logits0, frame_toks[0:1])
            assert torch.isclose(nll0, full_stage_losses[0][f], atol=1e-6)
            for s in range(1, k):
                tok_emb = model.token_embedding(frame_toks[s - 1 : s].view(1, 1))
                dh = model.depth_hidden(tok_emb, cache=d_cache, offset=s)
                lo, hi = s * CODEBOOK_SIZE, (s + 1) * CODEBOOK_SIZE
                logits_s = (dh[:, -1, :] @ model.head.weight[lo:hi].T).float()
                nll_s = torch.nn.functional.cross_entropy(logits_s, frame_toks[s : s + 1] - lo)
                assert torch.isclose(nll_s, full_stage_losses[s][f], atol=1e-6)
            f_emb = model.embed_frames(frame_toks.view(1, 1, k))
            h = model.temporal_hidden(f_emb, cache=t_cache, offset=t_pos)
            t_pos += 1


def test_min_p_and_repeat_penalty_behave_cleanly():
    logits = torch.tensor([[5.0, 4.9, -10.0, -20.0]])
    for _ in range(20):
        tok = int(draw_from_logits(logits, top_k=0, min_p=0.1).item())
        assert tok in (0, 1)
    # Strong repeat penalty suppresses token 0 in favor of token 1.
    torch.manual_seed(0)
    picks = [
        int(draw_from_logits(logits, temperature=0.5, top_k=0, repeat_token=0, repeat_penalty=2.0).item())
        for _ in range(30)
    ]
    assert picks.count(1) > 25
